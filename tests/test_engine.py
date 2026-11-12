import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from datadoctor import engine  # noqa: E402


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.roots = [self.root]

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def test_inspect_valid_json(self):
        path = self.write("sample.json", '{"ok": true}')
        result = engine.OPERATIONS["inspect_file"]({"path": str(path)}, self.roots)
        self.assertEqual(result["validation"]["valid"], True)
        self.assertEqual(result["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_corruption_detection_invalid_json(self):
        path = self.write("broken.json", '{"ok": ')
        result = engine.OPERATIONS["detect_corruption"]({"path": str(path)}, self.roots)
        self.assertFalse(result["valid"])
        self.assertIn("line", result)

    def test_diagnose_errors_includes_actionable_structured_diagnosis(self):
        path = self.write("diagnose.json", '{"broken": ')
        result = engine.OPERATIONS["diagnose_errors"]({"path": str(path)}, self.roots)
        self.assertEqual(result["diagnosis"]["status"], "structural_validation_failed")
        self.assertIn("line", result["validation"])
        self.assertIn("trusted source", result["diagnosis"]["recommended_next_step"])

    def test_nonstandard_json_nan_is_rejected(self):
        path = self.write("nonstandard.json", '{"value": NaN}')
        result = engine.OPERATIONS["detect_corruption"]({"path": str(path)}, self.roots)
        self.assertFalse(result["valid"])
        self.assertIn("Non-standard JSON", result["error"])

    def test_csv_column_count_mismatch_is_invalid(self):
        path = self.write("bad.csv", "a,b\n1,2\n3\n")
        result = engine.OPERATIONS["detect_corruption"]({"path": str(path)}, self.roots)
        self.assertFalse(result["valid"])
        self.assertEqual(result["inconsistent_row_numbers"], [3])

    def test_scan_skips_hidden_files(self):
        self.write("visible.json", '{"x":1}')
        self.write(".secret.json", '{"secret":true}')
        result = engine.OPERATIONS["scan_data"]({"path": str(self.root)}, self.roots)
        self.assertEqual(result["summary"]["files_scanned"], 1)
        self.assertEqual(Path(result["files"][0]["path"]).name, "visible.json")

    def test_rejects_path_escape(self):
        outside = self.root.parent / (self.root.name + "-outside.txt")
        outside.write_text("outside", encoding="utf-8")
        try:
            with self.assertRaises(engine.DoctorError):
                engine._resolve_user_path(str(outside), self.roots)
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_symlink(self):
        target = self.write("target.txt", "safe")
        link = self.root / "link.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable on this platform")
        with self.assertRaises(engine.DoctorError):
            engine._resolve_user_path(str(link), self.roots)

    def test_scan_exact_limit_is_not_marked_truncated(self):
        self.write("one.json", '{"one":1}')
        result = engine.OPERATIONS["scan_data"]({"path": str(self.root), "max_files": 1}, self.roots)
        self.assertEqual(result["summary"]["files_scanned"], 1)
        self.assertFalse(result["summary"]["truncated"])

    def test_scan_over_limit_is_marked_truncated(self):
        self.write("one.json", '{"one":1}')
        self.write("two.json", '{"two":2}')
        result = engine.OPERATIONS["scan_data"]({"path": str(self.root), "max_files": 1}, self.roots)
        self.assertEqual(result["summary"]["files_scanned"], 1)
        self.assertTrue(result["summary"]["truncated"])

    def test_find_duplicates_uses_content_hash(self):
        self.write("a.bin", b"same")
        self.write("b.bin", b"same")
        self.write("c.bin", b"different")
        result = engine.OPERATIONS["find_duplicates"]({"path": str(self.root)}, self.roots)
        self.assertEqual(result["duplicate_groups"], 1)
        self.assertEqual(result["duplicate_files"], 2)

    def test_json_repair_requires_confirmation_and_keeps_backup(self):
        path = self.write("format.json", '{ "x" : 1 }')
        original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(engine.DoctorError):
            engine.OPERATIONS["repair_data"]({"path": str(path), "strategy": "json_format", "confirm": False}, self.roots)
        result = engine.OPERATIONS["repair_data"]({
            "path": str(path), "strategy": "json_format", "confirm": True, "expected_sha256": original_hash
        }, self.roots)
        self.assertTrue(result["verified"])
        self.assertTrue(Path(result["backup_path"]).exists())
        self.assertEqual(json.loads(path.read_text()), {"x": 1})
        self.assertEqual(Path(result["backup_path"]).read_bytes(), b'{ "x" : 1 }')

    def test_json_repair_refuses_corrupt_json(self):
        path = self.write("broken.json", '{ "x": ')
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(engine.DoctorError, "JSON is invalid"):
            engine.OPERATIONS["repair_data"]({"path": str(path), "strategy": "json_format", "confirm": True, "expected_sha256": expected}, self.roots)
        self.assertEqual(path.read_text(), '{ "x": ')

    def test_csv_repair_refuses_inconsistent_rows(self):
        path = self.write("bad.csv", "a,b\n1,2\n3\n")
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(engine.DoctorError, "structurally inconsistent"):
            engine.OPERATIONS["repair_data"]({"path": str(path), "strategy": "csv_normalize", "confirm": True, "expected_sha256": expected}, self.roots)
        self.assertEqual(path.read_text(), "a,b\n1,2\n3\n")

    def test_backup_collision_prevents_overwrite(self):
        path = self.write("format.json", '{ "x" : 1 }')
        backup = path.with_name(path.name + ".datadoctor.bak")
        backup.write_text("prior backup")
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(engine.DoctorError, "Backup already exists"):
            engine.OPERATIONS["repair_data"]({"path": str(path), "strategy": "json_format", "confirm": True, "expected_sha256": expected}, self.roots)
        self.assertEqual(backup.read_text(), "prior backup")


    def test_repair_refuses_stale_hash(self):
        path = self.write("stale.json", '{ "x": 1 }')
        stale = hashlib.sha256(b'{"x":1}').hexdigest()
        with self.assertRaisesRegex(engine.DoctorError, "changed since inspection"):
            engine.OPERATIONS["repair_data"]({"path": str(path), "strategy": "json_format", "confirm": True, "expected_sha256": stale}, self.roots)
        self.assertEqual(path.read_text(), '{ "x": 1 }')

    def test_profile_dataset_returns_aggregates_not_raw_values(self):
        path = self.write("dataset.csv", "id,score,active\n1,10.5,true\n2,,false\n3,7,true\n")
        result = engine.OPERATIONS["profile_dataset"]({"path": str(path)}, self.roots)
        self.assertEqual(result["profile_status"], "complete")
        self.assertEqual(result["summary"]["rows_profiled"], 3)
        self.assertEqual(result["column_profiles"][0]["inferred_type"], "integer")
        self.assertEqual(result["column_profiles"][1]["null_count"], 1)
        self.assertEqual(result["column_profiles"][1]["numeric_min"], "7")
        self.assertNotIn("distinct_values", json.dumps(result))
        self.assertIn("Raw rows and distinct sample values are not returned", result["privacy_note"])

    def test_profile_dataset_marks_row_limit_as_partial(self):
        path = self.write("large.csv", "value\n1\n2\n3\n")
        result = engine.OPERATIONS["profile_dataset"]({"path": str(path), "max_rows": 2}, self.roots)
        self.assertEqual(result["profile_status"], "partial")
        self.assertTrue(result["summary"]["truncated"])
        self.assertEqual(result["summary"]["rows_profiled"], 2)

    def test_profile_dataset_rejects_non_csv(self):
        path = self.write("data.json", '{"x":1}')
        with self.assertRaisesRegex(engine.DoctorError, "CSV files only"):
            engine.OPERATIONS["profile_dataset"]({"path": str(path)}, self.roots)

    def test_scan_byte_budget_is_reported(self):
        self.write("a.bin", b"a" * (600 * 1024))
        self.write("b.bin", b"b" * (600 * 1024))
        result = engine.OPERATIONS["scan_data"]({"path": str(self.root), "max_total_bytes": 1024 * 1024}, self.roots)
        self.assertEqual(result["summary"]["files_scanned"], 1)
        self.assertTrue(result["summary"]["truncated"])
        self.assertIn("max_total_bytes", result["summary"]["truncation_reasons"])
        self.assertEqual(result["summary"]["bytes_hashed"], 600 * 1024)

    def test_scan_depth_limit_is_reported(self):
        self.write("level1/level2/nested.json", '{"ok":true}')
        result = engine.OPERATIONS["scan_data"]({"path": str(self.root), "max_depth": 1}, self.roots)
        self.assertTrue(result["summary"]["truncated"])
        self.assertIn("max_depth", result["summary"]["truncation_reasons"])
        self.assertEqual(result["summary"]["files_scanned"], 0)

    def test_xml_dtd_is_rejected(self):
        path = self.write("unsafe.xml", '<!DOCTYPE x [<!ENTITY e "x">]><x>&e;</x>')
        result = engine.OPERATIONS["detect_corruption"]({"path": str(path)}, self.roots)
        self.assertFalse(result["valid"])
        self.assertIn("DTD and entity declarations", result["error"])

    def test_verify_integrity_requires_trusted_hash_for_verified_true(self):
        path = self.write("trusted.json", '{"ok":true}')
        no_expected = engine.OPERATIONS["verify_integrity"]({"path": str(path)}, self.roots)
        self.assertFalse(no_expected["integrity_verified"])
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        matched = engine.OPERATIONS["verify_integrity"]({"path": str(path), "expected_sha256": expected}, self.roots)
        self.assertTrue(matched["integrity_verified"])
        self.assertTrue(matched["hash_matches_expected"])


    def test_scan_handles_more_than_one_thousand_small_files(self):
        for index in range(1100):
            self.write(f"bulk/file-{index:04d}.txt", "ok")
        result = engine.OPERATIONS["scan_data"]({"path": str(self.root), "max_files": 1200}, self.roots)
        self.assertEqual(result["summary"]["files_scanned"], 1100)
        self.assertFalse(result["summary"]["truncated"])


    def test_csv_normalization_requires_digest_and_retains_original(self):
        path = self.write("normalize.csv", b'a,b\r\n1,"two, parts"\r\n')
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        result = engine.OPERATIONS["repair_data"]({
            "path": str(path), "strategy": "csv_normalize", "confirm": True, "expected_sha256": expected
        }, self.roots)
        self.assertTrue(result["verified"])
        self.assertEqual(path.read_bytes(), b'a,b\n1,"two, parts"\n')
        self.assertEqual(Path(result["backup_path"]).read_bytes(), b'a,b\r\n1,"two, parts"\r\n')


if __name__ == "__main__":
    unittest.main()
