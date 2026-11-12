#!/usr/bin/env python3
"""DataDoctor's deterministic, stdlib-only file analysis engine."""
from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import time
import zipfile
import zlib
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ENGINE_VERSION = "0.2.0"
DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_FILES = 1000
DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_SCAN_BYTES = 512 * 1024 * 1024
HARD_MAX_SCAN_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_PROFILE_ROWS = 100_000
MAX_PROFILE_COLUMNS = 500
MAX_PROFILE_DISTINCT_VALUES = 10_000
MAX_PROFILE_DISTINCT_TOTAL = 100_000
TEXT_EXTENSIONS = {".txt", ".md", ".log", ".yaml", ".yml", ".ini", ".toml", ".html", ".css", ".js", ".ts", ".py", ".rs", ".c", ".h", ".cpp", ".java", ".sh"}


class DoctorError(Exception):
    """Expected, user-actionable engine error."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        common = os.path.commonpath((str(path), str(root)))
        return os.path.normcase(common) == os.path.normcase(str(root))
    except ValueError:
        return False


def _roots(raw_roots: list[str]) -> list[Path]:
    if not raw_roots:
        raise DoctorError("No allowed roots are configured. Start the server with --root /absolute/path.")
    resolved: list[Path] = []
    for item in raw_roots:
        root = Path(item).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise DoctorError(f"Allowed root is not a directory: {root}")
        if root not in resolved:
            resolved.append(root)
    return resolved


def _resolve_user_path(raw: str, roots: list[Path], must_exist: bool = True) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise DoctorError("A non-empty path is required.")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    # Reject symlinks in the user-supplied path before resolve() erases that fact.
    absolute_candidate = candidate.absolute()
    cursor = Path(absolute_candidate.anchor)
    for component in absolute_candidate.parts[1:]:
        cursor = cursor / component
        try:
            if cursor.is_symlink():
                raise DoctorError("Symbolic links are not followed by DataDoctor.")
        except OSError as exc:
            raise DoctorError(f"Cannot inspect path component: {exc}") from exc
    try:
        resolved = candidate.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise DoctorError(f"Path does not exist: {raw}") from exc
    if not any(_is_within(resolved, root) for root in roots):
        raise DoctorError("Path is outside the configured DataDoctor roots.")
    if must_exist and not resolved.exists():
        raise DoctorError(f"Path does not exist: {raw}")
    return resolved


def _require_regular_file(path: Path, max_bytes: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise DoctorError(f"Cannot stat file: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise DoctorError("Only regular, non-symlink files are supported for this operation.")
    if max_bytes is not None and info.st_size > max_bytes:
        raise DoctorError(f"File is {info.st_size} bytes; configured operation limit is {max_bytes} bytes.")
    return info


def _fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Capture identity and timestamps to detect concurrent mutation."""
    return (
        int(info.st_dev), int(info.st_ino), int(info.st_mode), int(info.st_size),
        int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))),
        int(getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))),
    )


def _sha256(path: Path, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    # O_NOFOLLOW prevents a final-component symlink swap where supported.
    # O_NONBLOCK prevents a regular-file-to-FIFO race from hanging the worker.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if max_bytes is not None:
        _require_regular_file(path, max_bytes)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DoctorError(f"Cannot safely open file for hashing: {exc}") from exc
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise DoctorError("Only regular files can be hashed.")
        try:
            path_before = path.lstat()
        except OSError as exc:
            raise DoctorError(f"File changed before hashing: {exc}") from exc
        if _fingerprint(before) != _fingerprint(path_before):
            raise DoctorError("File identity changed before hashing; retry the inspection.")
        total_read = 0
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total_read += len(chunk)
            if max_bytes is not None and total_read > max_bytes:
                raise DoctorError(f"File grew beyond the {max_bytes}-byte hashing limit.")
            digest.update(chunk)
        after = os.fstat(handle.fileno())
        if _fingerprint(before) != _fingerprint(after):
            raise DoctorError("File changed while its SHA-256 digest was being calculated.")
    try:
        path_after = path.lstat()
    except OSError as exc:
        raise DoctorError(f"File changed during hashing: {exc}") from exc
    if _fingerprint(after) != _fingerprint(path_after):
        raise DoctorError("File path changed while its SHA-256 digest was being calculated.")
    return digest.hexdigest()


def _read_stable_bytes(path: Path, max_bytes: int) -> tuple[bytes, os.stat_result]:
    info = _require_regular_file(path, max_bytes)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DoctorError(f"Cannot safely open file: {exc}") from exc
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or _fingerprint(info) != _fingerprint(opened):
            raise DoctorError("File identity changed before it could be read safely.")
        data = handle.read(max_bytes + 1)
        after = os.fstat(handle.fileno())
        if len(data) > max_bytes:
            raise DoctorError(f"File exceeds the {max_bytes}-byte read limit.")
        if _fingerprint(opened) != _fingerprint(after):
            raise DoctorError("File changed while it was being read; retry when it is idle.")
    try:
        path_after = path.lstat()
    except OSError as exc:
        raise DoctorError(f"File changed while it was being read: {exc}") from exc
    if _fingerprint(after) != _fingerprint(path_after):
        raise DoctorError("File path changed while it was being read; retry the operation.")
    return data, info


def _format_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".json": "json", ".csv": "csv", ".xml": "xml", ".zip": "zip",
        ".sqlite": "sqlite", ".sqlite3": "sqlite", ".db": "sqlite",
    }.get(ext, "text" if ext in TEXT_EXTENSIONS else "unknown")


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric constant is not allowed: {token}")


def _loads_json_strict(data: str) -> Any:
    return json.loads(data, parse_constant=_reject_json_constant)


def _check_csv(data: str) -> dict[str, Any]:
    try:
        reader = csv.reader(io.StringIO(data, newline=""), strict=True)
        row_count = 0
        expected_width: int | None = None
        inconsistent: list[int] = []
        for row in reader:
            row_count += 1
            if not row:
                continue
            if expected_width is None:
                expected_width = len(row)
            elif len(row) != expected_width and len(inconsistent) < 100:
                inconsistent.append(row_count)
    except csv.Error as exc:
        return {"format": "csv", "valid": False, "error": str(exc)}
    return {
        "format": "csv", "valid": not inconsistent,
        "rows": row_count, "columns": expected_width or 0,
        "inconsistent_row_numbers": inconsistent,
        "error": "Rows have inconsistent column counts." if inconsistent else None,
    }


def _validate(path: Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, Any]:
    fmt = _format_for(path)
    result: dict[str, Any] = {"format": fmt, "checked": True, "valid": None}
    info = _require_regular_file(path, max_bytes)
    if fmt in {"json", "csv", "xml", "text"}:
        try:
            raw, _ = _read_stable_bytes(path, max_bytes)
            data = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return {**result, "valid": False, "error": f"Not valid UTF-8 text: {exc}"}
        if fmt == "json":
            try:
                value = _loads_json_strict(data)
                result.update(valid=True, top_level_type=type(value).__name__)
            except json.JSONDecodeError as exc:
                result.update(valid=False, error=exc.msg, line=exc.lineno, column=exc.colno, position=exc.pos)
            except ValueError as exc:
                result.update(valid=False, error=str(exc))
        elif fmt == "csv":
            result.update(_check_csv(data))
        elif fmt == "xml":
            try:
                if "<!DOCTYPE" in data.upper() or "<!ENTITY" in data.upper():
                    return {**result, "valid": False, "error": "DTD and entity declarations are not accepted by the safe XML validator."}
                root = ET.fromstring(data)
                result.update(valid=True, root_tag=root.tag)
            except ET.ParseError as exc:
                result.update(valid=False, error=str(exc))
        else:
            result.update(valid=True, encoding="utf-8", characters=len(data))
    elif fmt == "zip":
        try:
            raw, _ = _read_stable_bytes(path, max_bytes)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                total_uncompressed = sum(item.file_size for item in entries)
                if len(entries) > 10000 or total_uncompressed > 250 * 1024 * 1024:
                    result.update(valid=None, checked=False, error="Archive exceeds safe inspection limits; CRC scan skipped.")
                else:
                    bad_member = archive.testzip()
                    result.update(valid=bad_member is None, entries=len(entries), uncompressed_bytes=total_uncompressed)
                    if bad_member is not None:
                        result["error"] = f"CRC failure in archive member: {bad_member}"
        except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error) as exc:
            result.update(valid=False, error=str(exc))
    elif fmt == "sqlite":
        try:
            uri = path.as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2.0) as connection:
                connection.execute("PRAGMA query_only=ON")
                rows = connection.execute("PRAGMA quick_check").fetchall()
                messages = [str(row[0]) for row in rows]
                ok = messages == ["ok"]
                result.update(valid=ok, integrity_messages=messages[:50])
                if not ok:
                    result["error"] = "SQLite quick_check reported integrity problems."
        except sqlite3.Error as exc:
            result.update(valid=False, error=str(exc))
    else:
        result.update(checked=False, valid=None, note="Unknown file type; byte-level metadata and SHA-256 only.")
    return result


def _inspect(path: Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, Any]:
    info = _require_regular_file(path, max_bytes)
    before = _fingerprint(info)
    validation = _validate(path, max_bytes)
    digest = _sha256(path, max_bytes)
    after_info = _require_regular_file(path)
    if before != _fingerprint(after_info):
        raise DoctorError("File changed during inspection; no combined result was produced. Retry when the file is idle.")
    return {
        "path": str(path), "name": path.name, "extension": path.suffix.lower(),
        "format": validation.get("format"), "size_bytes": info.st_size,
        "modified_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(info.st_mtime)),
        "sha256": digest, "validation": validation,
    }


def scan_data(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    base = _resolve_user_path(args["path"], roots)
    if not base.is_dir():
        raise DoctorError("scan_data requires a directory path.")
    max_files = max(1, min(int(args.get("max_files", DEFAULT_MAX_FILES)), 10000))
    max_depth = max(0, min(int(args.get("max_depth", DEFAULT_MAX_DEPTH)), 32))
    max_total_bytes = max(1 * 1024 * 1024, min(int(args.get("max_total_bytes", DEFAULT_MAX_SCAN_BYTES)), HARD_MAX_SCAN_BYTES))
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    skipped = 0
    bytes_hashed = 0
    truncation_reasons: set[str] = set()

    def walk_error(exc: OSError) -> None:
        nonlocal skipped
        errors.append({"path": str(getattr(exc, "filename", "") or base), "error": str(exc)})
        skipped += 1
        truncation_reasons.add("unreadable_directory")

    for current, dirs, names in os.walk(base, topdown=True, followlinks=False, onerror=walk_error):
        current_path = Path(current)
        depth = len(current_path.relative_to(base).parts)
        retained_dirs: list[str] = []
        for dirname in sorted(dirs):
            directory = current_path / dirname
            if dirname.startswith(".") or directory.is_symlink():
                skipped += 1
                continue
            retained_dirs.append(dirname)
        if depth >= max_depth and retained_dirs:
            skipped += len(retained_dirs)
            truncation_reasons.add("max_depth")
            retained_dirs = []
        dirs[:] = retained_dirs

        for name in sorted(names):
            target = current_path / name
            if name.startswith(".") or target.is_symlink():
                skipped += 1
                continue
            if not target.is_file():
                skipped += 1
                continue
            if len(files) + len(errors) >= max_files:
                truncation_reasons.add("max_files")
                return _scan_summary(base, files, errors, skipped, truncation_reasons, bytes_hashed)
            try:
                info = _require_regular_file(target)
                if info.st_size > DEFAULT_MAX_FILE_BYTES:
                    files.append({"path": str(target), "size_bytes": info.st_size, "scan_status": "skipped", "status": "skipped_size_limit"})
                    skipped += 1
                    continue
                if bytes_hashed + info.st_size > max_total_bytes:
                    files.append({"path": str(target), "size_bytes": info.st_size, "scan_status": "skipped", "status": "skipped_scan_byte_budget"})
                    skipped += 1
                    truncation_reasons.add("max_total_bytes")
                    continue
                remaining_budget = max_total_bytes - bytes_hashed
                inspected = _inspect(target, min(DEFAULT_MAX_FILE_BYTES, remaining_budget))
                files.append({
                    "path": inspected["path"], "size_bytes": inspected["size_bytes"],
                    "sha256": inspected["sha256"], "format": inspected["format"],
                    "valid": inspected["validation"].get("valid"),
                    "checked": inspected["validation"].get("checked"),
                    "error": inspected["validation"].get("error"),
                    "scan_status": "inspected",
                })
                bytes_hashed += inspected["size_bytes"]
            except (OSError, DoctorError) as exc:
                errors.append({"path": str(target), "error": str(exc)})
                skipped += 1
    return _scan_summary(base, files, errors, skipped, truncation_reasons, bytes_hashed)


def _scan_summary(
    base: Path,
    files: list[dict[str, Any]],
    errors: list[dict[str, str]],
    skipped: int,
    truncation_reasons: set[str],
    bytes_hashed: int,
) -> dict[str, Any]:
    inspected = [item for item in files if item.get("scan_status") == "inspected"]
    invalid = sum(1 for item in inspected if item.get("valid") is False)
    valid = sum(1 for item in inspected if item.get("valid") is True)
    unchecked = sum(1 for item in inspected if item.get("valid") is None)
    bytes_observed = sum(int(item.get("size_bytes", 0)) for item in files)
    reasons = sorted(truncation_reasons)
    return {
        "root": str(base), "engine_version": ENGINE_VERSION,
        "summary": {
            "files_seen": len(files), "files_scanned": len(inspected), "valid": valid,
            "invalid": invalid, "unchecked": unchecked, "skipped": skipped,
            "errors": len(errors), "bytes_hashed": bytes_hashed,
            "bytes_observed": bytes_observed, "truncated": bool(reasons),
            "truncation_reasons": reasons,
        },
        "files": files, "errors": errors[:100],
    }

def find_duplicates(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    report = scan_data({"path": args["path"], "max_files": args.get("max_files", DEFAULT_MAX_FILES), "max_depth": args.get("max_depth", DEFAULT_MAX_DEPTH), "max_total_bytes": args.get("max_total_bytes", DEFAULT_MAX_SCAN_BYTES)}, roots)
    groups: dict[str, list[str]] = {}
    for item in report["files"]:
        if item.get("scan_status") != "inspected":
            continue
        digest = item.get("sha256")
        if digest:
            groups.setdefault(digest, []).append(item["path"])
    duplicates = [{"sha256": digest, "count": len(paths), "paths": paths} for digest, paths in groups.items() if len(paths) > 1]
    duplicates.sort(key=lambda item: (-item["count"], item["sha256"]))
    return {"root": report["root"], "duplicate_groups": len(duplicates), "duplicate_files": sum(x["count"] for x in duplicates), "groups": duplicates,
            "scan_truncated": report["summary"]["truncated"], "scan_summary": report["summary"]}



def _classify_cell(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "null"
    lowered = stripped.casefold()
    if lowered in {"true", "false", "yes", "no"}:
        return "boolean"
    try:
        number = Decimal(stripped)
        if number.is_finite():
            return "integer" if number == number.to_integral_value() else "number"
    except InvalidOperation:
        pass
    return "string"


def _merge_inferred_types(type_counts: dict[str, int]) -> str:
    observed = {kind for kind, count in type_counts.items() if count > 0 and kind != "null"}
    if not observed:
        return "null"
    if observed <= {"integer", "number"}:
        return "integer" if observed == {"integer"} else "number"
    if len(observed) == 1:
        return next(iter(observed))
    return "mixed"


def profile_dataset(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    """Profile a CSV without returning raw cell values to the model."""
    path = _resolve_user_path(args["path"], roots)
    if _format_for(path) != "csv":
        raise DoctorError("profile_dataset currently supports CSV files only.")
    max_rows = max(1, min(int(args.get("max_rows", DEFAULT_MAX_PROFILE_ROWS)), 1_000_000))
    has_header = args.get("has_header", True) is not False
    inspection = _inspect(path)
    if inspection["validation"].get("valid") is not True:
        return {
            "path": str(path), "sha256": inspection["sha256"],
            "profile_status": "blocked_invalid_csv", "validation": inspection["validation"],
            "note": "Dataset profiling was not run because structural CSV validation failed.",
        }
    raw, _ = _read_stable_bytes(path, DEFAULT_MAX_FILE_BYTES)
    raw_hash = hashlib.sha256(raw).hexdigest()
    if raw_hash != inspection["sha256"]:
        raise DoctorError("CSV changed between validation and profiling; retry when the file is idle.")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DoctorError(f"CSV is not UTF-8: {exc}") from exc

    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    try:
        first_row = next(reader, None)
        if first_row is None:
            return {
                "path": str(path), "sha256": raw_hash, "profile_status": "empty_file",
                "row_count": 0, "columns": [], "has_header": has_header, "truncated": False,
            }
        if has_header:
            headers = [name.strip() for name in first_row]
            data_first = None
        else:
            headers = [f"column_{index + 1}" for index in range(len(first_row))]
            data_first = first_row
        if len(headers) > MAX_PROFILE_COLUMNS:
            raise DoctorError(f"CSV has {len(headers)} columns; the profiling limit is {MAX_PROFILE_COLUMNS}.")

        column_stats: list[dict[str, Any]] = []
        for name in headers:
            column_stats.append({
                "name": name, "null_count": 0, "non_null_count": 0,
                "type_counts": {"integer": 0, "number": 0, "boolean": 0, "string": 0, "null": 0},
                "distinct_values": set(), "distinct_count_exact": True,
                "numeric_min": None, "numeric_max": None,
            })

        row_count = 0
        empty_rows = 0
        malformed_rows = 0
        tracked_distinct_total = 0
        malformed_row_numbers: list[int] = []
        truncated = False

        def consume_row(row: list[str], row_number: int) -> None:
            nonlocal row_count, empty_rows, malformed_rows, tracked_distinct_total
            row_count += 1
            if not row:
                empty_rows += 1
            if len(row) != len(column_stats):
                malformed_rows += 1
                if len(malformed_row_numbers) < 100:
                    malformed_row_numbers.append(row_number)
            for index, stats in enumerate(column_stats):
                cell = row[index] if index < len(row) else ""
                kind = _classify_cell(cell)
                stats["type_counts"][kind] += 1
                if kind == "null":
                    stats["null_count"] += 1
                    continue
                stats["non_null_count"] += 1
                distinct = stats["distinct_values"]
                if cell not in distinct:
                    if len(distinct) < MAX_PROFILE_DISTINCT_VALUES and tracked_distinct_total < MAX_PROFILE_DISTINCT_TOTAL:
                        distinct.add(cell)
                        tracked_distinct_total += 1
                    else:
                        stats["distinct_count_exact"] = False
                if kind in {"integer", "number"}:
                    try:
                        numeric = Decimal(cell.strip())
                        if numeric.is_finite():
                            if stats["numeric_min"] is None or numeric < stats["numeric_min"]:
                                stats["numeric_min"] = numeric
                            if stats["numeric_max"] is None or numeric > stats["numeric_max"]:
                                stats["numeric_max"] = numeric
                    except InvalidOperation:
                        pass

        if data_first is not None:
            consume_row(data_first, 1)
        for row in reader:
            if row_count >= max_rows:
                truncated = True
                break
            data_line = reader.line_num + (1 if has_header else 0)
            consume_row(row, data_line)
    except csv.Error as exc:
        raise DoctorError(f"CSV parsing failed during profiling: {exc}") from exc

    duplicate_headers = sorted({name for name in headers if name and headers.count(name) > 1})
    columns: list[dict[str, Any]] = []
    for stats in column_stats:
        distinct_values = stats.pop("distinct_values")
        minimum = stats.pop("numeric_min")
        maximum = stats.pop("numeric_max")
        columns.append({
            **stats,
            "inferred_type": _merge_inferred_types(stats["type_counts"]),
            "distinct_count_lower_bound": len(distinct_values),
            "distinct_count_exact": stats["distinct_count_exact"],
            "numeric_min": str(minimum) if minimum is not None else None,
            "numeric_max": str(maximum) if maximum is not None else None,
        })
    summary = {
        "rows_profiled": row_count, "columns": len(columns), "empty_rows": empty_rows,
        "malformed_row_count": malformed_rows, "malformed_row_numbers": malformed_row_numbers,
        "duplicate_header_names": duplicate_headers, "truncated": truncated,
        "row_limit": max_rows, "distinct_tracking_cap_per_column": MAX_PROFILE_DISTINCT_VALUES,
        "distinct_tracking_cap_total": MAX_PROFILE_DISTINCT_TOTAL,
    }
    return {
        "path": str(path), "sha256": raw_hash, "profile_status": "partial" if truncated else "complete",
        "has_header": has_header, "summary": summary, "column_profiles": columns,
        "privacy_note": "Raw rows and distinct sample values are not returned. Column names, aggregate counts/type distributions, and numeric minimum/maximum values are disclosed.",
        "interpretation_note": "Inferred types are heuristic observations, not a declared schema or proof of business-rule validity.",
    }

def compare_versions(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    left = _resolve_user_path(args["left_path"], roots)
    right = _resolve_user_path(args["right_path"], roots)
    li = _require_regular_file(left, DEFAULT_MAX_FILE_BYTES)
    ri = _require_regular_file(right, DEFAULT_MAX_FILE_BYTES)
    left_bytes = _read_stable_bytes(left, 1024 * 1024)[0] if li.st_size <= 1024 * 1024 else None
    right_bytes = _read_stable_bytes(right, 1024 * 1024)[0] if ri.st_size <= 1024 * 1024 else None
    lh = hashlib.sha256(left_bytes).hexdigest() if left_bytes is not None else _sha256(left, DEFAULT_MAX_FILE_BYTES)
    rh = hashlib.sha256(right_bytes).hexdigest() if right_bytes is not None else _sha256(right, DEFAULT_MAX_FILE_BYTES)
    result: dict[str, Any] = {"left": str(left), "right": str(right), "left_sha256": lh, "right_sha256": rh,
                              "identical": lh == rh, "left_size_bytes": li.st_size, "right_size_bytes": ri.st_size}
    if left_bytes is not None and right_bytes is not None:
        try:
            a = left_bytes.decode("utf-8-sig").splitlines(keepends=True)
            b = right_bytes.decode("utf-8-sig").splitlines(keepends=True)
            if len(a) + len(b) > 10000:
                result["text_diff"] = None
                result["note"] = "Text diff skipped because the combined line count exceeds the 10,000-line safety limit."
            else:
                diff_text = "".join(difflib.unified_diff(a, b, fromfile=left.name, tofile=right.name, n=3))
                result["text_diff"] = diff_text[:20000]
                result["text_diff_truncated"] = len(diff_text) > 20000
        except UnicodeDecodeError:
            result["text_diff"] = None
            result["note"] = "At least one file is binary or not UTF-8; hashes and sizes are authoritative."
    return result


def diagnose_errors(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = _resolve_user_path(args["path"], roots)
    report = _inspect(path)
    validation = report["validation"]
    fmt = validation.get("format")
    if validation.get("valid") is True:
        report["diagnosis"] = {
            "status": "no_structural_issue_detected",
            "severity": "info",
            "explanation": "The available structural validator passed. This does not prove application-specific semantic correctness."
        }
    elif validation.get("valid") is False:
        suggestions = {
            "json": "Use the reported line and column to inspect the malformed token. Restore missing or corrupted content from a trusted source; automatic reconstruction is not available.",
            "csv": "Inspect the reported row numbers and compare their column counts with the intended schema before editing.",
            "xml": "Inspect the parser message and restore well-formed tags/attributes from a trusted source.",
            "zip": "Do not extract the archive. Compare its hash with a trusted copy and obtain a fresh archive if corruption is confirmed.",
            "sqlite": "Preserve a copy before further investigation. DataDoctor does not repair SQLite pages.",
            "text": "Check the encoding and source application. DataDoctor will not guess a replacement encoding."
        }
        report["diagnosis"] = {
            "status": "structural_validation_failed",
            "severity": "error",
            "explanation": validation.get("error", "The file did not pass its structural validator."),
            "recommended_next_step": suggestions.get(fmt, "Check the file with the application that owns this format and compare it with a trusted copy.")
        }
    else:
        report["diagnosis"] = {
            "status": "not_fully_checked",
            "severity": "warning",
            "explanation": validation.get("note", "No validator is available for this file type."),
            "recommended_next_step": "Use the file's native application or a dedicated validator; treat the hash as an identifier, not proof of correctness."
        }
    return report


def verify_integrity(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = _resolve_user_path(args["path"], roots)
    result = _inspect(path)
    expected = args.get("expected_sha256")
    result["format_validated"] = result["validation"].get("valid") is True
    if expected:
        matches = result["sha256"].lower() == expected.lower()
        result["expected_sha256"] = expected.lower()
        result["hash_matches_expected"] = matches
        result["integrity_verified"] = matches and result["validation"].get("valid") is not False
    else:
        result["integrity_verified"] = False
        result["integrity_scope"] = "No trusted expected hash was supplied; SHA-256 was calculated and format validation was performed, but authenticity was not established."
    return result


def repair_data(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    path = _resolve_user_path(args["path"], roots)
    if args.get("confirm") is not True:
        raise DoctorError("Repair is disabled until confirm=true is explicitly supplied.")
    expected = args.get("expected_sha256")
    if not isinstance(expected, str) or len(expected) != 64 or any(char not in "0123456789abcdefABCDEF" for char in expected):
        raise DoctorError("Repair requires expected_sha256 from a prior inspection. This prevents stale or unreviewed writes.")
    original, original_info = _read_stable_bytes(path, DEFAULT_MAX_FILE_BYTES)
    strategy = args.get("strategy")
    original_hash = hashlib.sha256(original).hexdigest()
    if original_hash.lower() != expected.lower():
        raise DoctorError("The file changed since inspection: expected_sha256 does not match current content.")
    try:
        text = original.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DoctorError(f"Repair supports UTF-8 text only: {exc}") from exc
    if strategy == "json_format":
        try:
            parsed = _loads_json_strict(text)
        except json.JSONDecodeError as exc:
            raise DoctorError(f"JSON is invalid and cannot be safely reformatted: {exc.msg} at line {exc.lineno}, column {exc.colno}.") from exc
        except ValueError as exc:
            raise DoctorError(f"JSON is invalid and cannot be safely reformatted: {exc}") from exc
        repaired = (json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")
        expected_format = "json"
    elif strategy == "csv_normalize":
        check = _check_csv(text)
        if not check.get("valid"):
            raise DoctorError("CSV rows are structurally inconsistent; automatic normalization is refused.")
        try:
            rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
        except csv.Error as exc:
            raise DoctorError(f"CSV parse failed: {exc}") from exc
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerows(rows)
        repaired = output.getvalue().encode("utf-8")
        expected_format = "csv"
    else:
        raise DoctorError("Unsupported strategy. Available strategies: json_format, csv_normalize.")
    if repaired == original:
        return {"path": str(path), "changed": False, "message": "The file is already normalized; no write was performed.",
                "original_sha256": original_hash, "final_sha256": original_hash, "backup_path": None, "verified": True}

    backup = path.with_name(path.name + ".datadoctor.bak")
    if backup.exists():
        raise DoctorError(f"Backup already exists; refusing to overwrite it: {backup}")
    temp_name: str | None = None
    backup_created = False
    replaced = False
    try:
        # Exclusive backup creation prevents accidental overwrite of a prior backup.
        with backup.open("xb") as backup_handle:
            backup_created = True
            backup_handle.write(original)
            backup_handle.flush()
            os.fsync(backup_handle.fileno())
        os.chmod(backup, stat.S_IMODE(original_info.st_mode))
        if _sha256(backup) != original_hash:
            raise DoctorError("The backup did not match the original bytes; repair was aborted.")
        # Re-check immediately before replacement. Portable filesystems do not
        # provide a general compare-and-swap rename, so concurrent writers remain
        # outside the guarantee and are explicitly documented in the threat model.
        if _sha256(path) != original_hash:
            raise DoctorError("The file changed during repair preparation; no replacement was made.")
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temp:
            temp_name = temp.name
            temp.write(repaired)
            temp.flush()
            os.fsync(temp.fileno())
        os.chmod(temp_name, stat.S_IMODE(original_info.st_mode))
        if _sha256(path) != original_hash:
            raise DoctorError("The source changed while the replacement was being prepared; no replacement was made.")
        os.replace(temp_name, path)
        temp_name = None
        replaced = True
        verified_inspection = _inspect(path)
        validation = verified_inspection["validation"]
        final_hash = verified_inspection["sha256"]
        verified = validation.get("format") == expected_format and validation.get("valid") is True
        if not verified:
            raise DoctorError("Post-repair validation failed; the original content will be restored.")
        return {"path": str(path), "changed": True, "strategy": strategy, "original_sha256": original_hash,
                "final_sha256": final_hash, "backup_path": str(backup), "validation": validation,
                "verified": True, "message": "Repair completed and post-write validation passed. The backup was retained."}
    except Exception as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        if replaced:
            rollback_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", suffix=".rollback", delete=False) as rollback:
                    rollback_name = rollback.name
                    rollback.write(original)
                    rollback.flush()
                    os.fsync(rollback.fileno())
                os.chmod(rollback_name, stat.S_IMODE(original_info.st_mode))
                os.replace(rollback_name, path)
            except Exception as rollback_error:
                if rollback_name:
                    try:
                        os.unlink(rollback_name)
                    except OSError:
                        pass
                raise DoctorError(f"Repair failed and automatic rollback also failed. The backup is retained at {backup}. Rollback error: {rollback_error}") from rollback_error
        elif backup_created:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass
        raise exc


def generate_report(args: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    report = scan_data({"path": args["path"], "max_files": args.get("max_files", DEFAULT_MAX_FILES), "max_depth": args.get("max_depth", DEFAULT_MAX_DEPTH), "max_total_bytes": args.get("max_total_bytes", DEFAULT_MAX_SCAN_BYTES)}, roots)
    report["report_type"] = "datadoctor-scan-report"
    report["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["integrity_note"] = "SHA-256 hashes identify the bytes observed during this scan; they do not establish provenance or authenticity without a trusted expected hash."
    return report


OPERATIONS = {
    "scan_data": scan_data,
    "inspect_file": lambda args, roots: _inspect(_resolve_user_path(args["path"], roots)),
    "detect_corruption": lambda args, roots: _validate(_resolve_user_path(args["path"], roots)),
    "find_duplicates": find_duplicates,
    "profile_dataset": profile_dataset,
    "compare_versions": compare_versions,
    "diagnose_errors": diagnose_errors,
    "repair_data": repair_data,
    "verify_integrity": verify_integrity,
    "generate_report": generate_report,
}


def main() -> int:
    # JSON-RPC payloads and file paths must remain Unicode-safe on Windows pipes too.
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        request = json.load(sys.stdin)
        operation = request.get("operation")
        args = request.get("args") or {}
        roots = _roots(request.get("roots") or [])
        if operation not in OPERATIONS:
            raise DoctorError(f"Unknown operation: {operation}")
        result = OPERATIONS[operation](args, roots)
        response = {"ok": True, "operation": operation, "engine_version": ENGINE_VERSION, "result": result}
    except DoctorError as exc:
        response = {"ok": False, "error": str(exc), "error_type": "validation_or_safety"}
    except Exception as exc:  # defensive boundary: do not leak tracebacks into MCP stdout
        response = {"ok": False, "error": f"Internal engine error: {type(exc).__name__}: {exc}", "error_type": "internal"}
    # Keep the worker's single-line JSON response below the Node bridge cap.
    # Fail explicitly instead of emitting a truncated response for very large scans.
    serialized = json.dumps(response, ensure_ascii=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > 7 * 1024 * 1024:
        response = {
            "ok": False,
            "error": "The report exceeds the 7 MiB response budget. Reduce max_files or split the directory into smaller roots.",
            "error_type": "response_budget",
        }
        serialized = json.dumps(response, ensure_ascii=True, separators=(",", ":"))
    sys.stdout.write(serialized)
    sys.stdout.write("\n")
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
