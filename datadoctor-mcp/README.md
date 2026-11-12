<div align="center">

<img src="datadoctor-logo.svg" alt="DataDoctor" width="420">

# DataDoctor MCP

### Evidence before edits. Verification after every write.

**A local-first data integrity and diagnostics toolkit for Claude, exposed through the Model Context Protocol.**

[![CI](https://github.com/ayoubissa344-ship-it/datadoctor-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ayoubissa344-ship-it/datadoctor-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D20-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/Protocol-MCP-6f42c1)](https://modelcontextprotocol.io/)

**Created and maintained by [Ayoub Issa](https://github.com/ayoubissa344-ship-it).**

[Features](#what-datadoctor-does) · [Tools](#mcp-tools) · [Install](#installation) · [Claude setup](#connect-to-claude-desktop) · [Safety model](#safety-and-integrity-model) · [Architecture](docs/ARCHITECTURE.md) · [Roadmap](#roadmap)

</div>

---

## What DataDoctor is

DataDoctor MCP gives Claude a carefully scoped set of local tools for inspecting files, validating supported formats, profiling CSV datasets, finding byte-identical duplicates, comparing versions, diagnosing structural problems, and performing a small number of explicitly authorized normalizations.

It is designed around one operational rule:

> **A diagnosis must show its evidence. A write must have a precondition and backup. A successful repair must pass a post-write check.**

A file being readable is not proof that it is structurally valid. A parser accepting a file is not proof that its business meaning is correct. A newly computed hash is not proof of authenticity. DataDoctor keeps those distinctions visible in the tool results so Claude can explain what was checked, what was not checked, and how complete the scan was.

## What DataDoctor does

| Capability | What it provides |
|---|---|
| Bounded directory audit | Recursive scan with per-file status, SHA-256, explicit skips, errors, and truncation reasons |
| Format-aware checks | Structural checks for JSON, CSV, XML, ZIP, SQLite, and selected UTF-8 text files |
| Dataset profiling | CSV row/column counts, null counts, inferred types, bounded distinct-count estimates, and numeric ranges |
| Duplicate discovery | Groups byte-identical files by SHA-256; never deletes them |
| Version comparison | Hash/size comparison and a bounded text diff for small UTF-8 files |
| Diagnosis | Structured explanation of observed validation failures and cautious next steps |
| Controlled normalization | Reformat already-valid JSON or structurally consistent CSV after explicit authorization |
| Integrity verification | Compare current bytes against a caller-supplied trusted digest when available |
| Evidence report | Machine-readable report returned to Claude, including coverage limitations |

## Why it is useful with AI assistants

AI assistants can reason over file contents, but reasoning alone cannot establish whether a directory was completely scanned, whether a file changed during inspection, whether a proposed write still targets the bytes that were reviewed, or whether a replacement passed validation afterward.

DataDoctor supplies those operations as deterministic local tools. Claude can coordinate them and explain the results without pretending that an unchecked file is healthy or that a guessed repair is recovery.

### Intended users

- **Developers:** inspect project data, configuration artifacts, logs, archives, and SQLite files.
- **Researchers:** check datasets before analysis and record file digests and validation coverage.
- **Data analysts:** profile CSV structure, missingness, type distributions, and numeric ranges.
- **Students and educators:** diagnose malformed structured files without manually writing one-off scripts.
- **Small teams:** produce repeatable local audit results before moving or processing files.

## MCP tools

DataDoctor exposes ten tools. Read-only tools are marked as such in their MCP annotations. `repair_data` is marked as a write/destructive operation.

| Tool | Purpose | Writes files? |
|---|---|---:|
| `scan_data` | Bounded recursive scan of an allowed directory | No |
| `inspect_file` | Inspect one file and calculate SHA-256 | No |
| `detect_corruption` | Run the available structural validator | No |
| `find_duplicates` | Find byte-identical files by digest | No |
| `profile_dataset` | Profile one CSV without returning raw rows | No |
| `compare_versions` | Compare hashes, sizes, and optionally small text diffs | No |
| `diagnose_errors` | Combine inspection with an evidence-led diagnosis | No |
| `verify_integrity` | Validate and optionally compare a trusted expected SHA-256 | No |
| `generate_report` | Return a structured directory audit report | No |
| `repair_data` | Normalize already-valid JSON or consistent CSV | **Yes** |

### `scan_data`

Scans recursively within a configured root and returns a status for each recorded file. The summary separates `valid`, `invalid`, `unchecked`, `skipped`, and `errors`. If a file-count, depth, or aggregate byte budget is reached, the result includes `truncated: true` and a list of `truncation_reasons`.

Defaults: 1,000 files, depth 8, maximum 25 MiB per file, and 512 MiB of aggregate bytes hashed. The hard aggregate scan cap is 2 GiB. Hidden entries and symlinks are skipped. A truncated scan must never be described as a complete clean bill of health.

### `inspect_file` and `detect_corruption`

`inspect_file` returns the canonical path, file name, extension, size, modification timestamp, SHA-256, detected format, and validator result. `detect_corruption` returns the format-specific validator result without modifying the file.

Supported checks:

| Format | Check | What a pass means |
|---|---|---|
| JSON | Strict JSON parsing; rejects non-standard `NaN`/`Infinity` constants | The document parses as JSON |
| CSV | Strict CSV parsing and consistent non-empty row widths | Rows have a consistent structural width |
| XML | Well-formedness parsing; DTD/entity declarations are rejected | The XML parser accepted the document under this policy |
| ZIP | Archive parsing and CRC scan under entry/uncompressed-size limits | Checked archive members passed CRC verification |
| SQLite | Read-only `PRAGMA quick_check` | SQLite quick-check returned `ok` |
| Selected text | UTF-8 decoding | The bytes decode as UTF-8 |
| Unknown/binary | Metadata and SHA-256 only | No structural validation was performed |

A skipped or unknown validator returns `valid: null`/`checked: false`, not `valid: true`. Structural validation is not semantic validation, malware detection, authenticity verification, or proof that a dataset meets a research or business specification.

### `profile_dataset`

Profiles CSV files up to the per-file read limit. It returns row and column counts, null/non-null counts, heuristic type distributions, a bounded distinct-count lower bound, numeric minimum/maximum values, duplicate header names, and whether the row limit truncated the profile.

Raw rows and distinct sample values are not returned. Column names, aggregate counts/type distributions, and numeric bounds are disclosed; column names may themselves contain sensitive information. The output is a statistical profile, not a declared schema or a business-rule certification.

Defaults: 100,000 data rows; maximum 1,000,000 rows and 500 columns. Distinct-value tracking is capped at 10,000 unique strings per column and 100,000 tracked values across the profile. The profile is labelled `partial` when the row cap stops processing before end-of-file.

### `find_duplicates`

Groups files with matching SHA-256 digests. A matching digest is used as a practical byte-identity signal. The result includes scan coverage, so a partial scan is visible. DataDoctor does not delete, move, or merge duplicates, and a byte-identical file is not automatically safe to remove.

### `compare_versions`

Compares two allowed files by size and SHA-256; each input is subject to the 25 MiB per-file operation limit. A unified text diff is generated only when both files are at most 1 MiB, decode as UTF-8, and fit within the combined line limit. The diff is capped at 20,000 characters. Because diffs can contain snippets of file content, only compare files you are comfortable including in the Claude conversation.

### `diagnose_errors`

Returns validator output together with a structured status and a recommended next step. It separates structural observations from semantic conclusions and does not invent a way to reconstruct missing content.

### `verify_integrity`

Calculates SHA-256 and performs the available format check. To receive `integrity_verified: true`, provide an `expected_sha256` obtained from a trusted source. A hash calculated only from the current file identifies its current bytes; it does not establish provenance or authenticity.

### `repair_data`

Only two normalization strategies are implemented:

| Strategy | Preconditions | Operation |
|---|---|---|
| `json_format` | The source already parses as strict JSON | Writes stable UTF-8 JSON with two-space indentation and a final newline |
| `csv_normalize` | The source parses strictly and has consistent non-empty row widths | Rewrites CSV quoting and line endings using the standard CSV writer |

Every repair requires both `confirm: true` and an exact `expected_sha256` copied from an immediately preceding inspection. The operation aborts if the source digest differs. It creates `<filename>.datadoctor.bak` exclusively and refuses to overwrite an existing backup. The replacement is prepared in a same-directory temporary file, rechecks the source digest before replacement, atomically replaces the file, and validates the result. The backup is retained after success.

These are normalization operations, not corruption recovery. DataDoctor does **not** reconstruct malformed JSON, fill missing CSV cells, delete duplicates, or repair SQLite pages. Concurrent writers running under the same OS account can still create narrow race conditions; see the [threat model](docs/THREAT_MODEL.md). Keep independent backups for important data.

### `generate_report`

Returns a machine-readable `datadoctor-scan-report` to Claude. It includes a generation timestamp, SHA-256 values, format-validation states, skipped/error counts, byte coverage, truncation reasons, and a note explaining the limits of hash-based claims. The report is returned in the MCP response; it is not automatically written to disk.

## MCP prompts

The server also exposes three prompts that guide Claude towards evidence-led workflows:

- `audit-data-directory`: read-only folder audit with explicit coverage reporting.
- `explain-file-integrity`: explain the validator, evidence, limitations, and safe next step.
- `prepare-safe-repair`: prepare a repair plan and require separate user approval before a write.

Prompts guide model behavior; they are not a security boundary. The Python engine independently enforces path checks, repair preconditions, and write safeguards.

## Architecture

```text
Claude Desktop / Claude Code
          |
          | MCP over stdio
          v
+--------------------------------------+
| TypeScript MCP server                |
| Official MCP SDK / Zod input schemas  |
| Tool annotations / prompts / limits  |
+--------------------------------------+
          |
          | one bounded JSON request; no shell
          v
+--------------------------------------+
| Python analysis worker               |
| Standard-library-only engine         |
| Validation / hashing / profiling     |
| Narrow normalization / verification  |
+--------------------------------------+
          |
          v
 Explicitly configured local directories
```

TypeScript owns MCP transport, argument schemas, process lifecycle, subprocess timeout, and response-size limits. Python owns deterministic file operations using the standard library. The worker is started separately for each tool call and receives one JSON request over stdin; stdout is reserved for one JSON response. No third-party Python packages are required.

The server is local and uses stdio. It does not make network requests during file analysis. However, tool results are sent to the connected AI host: file paths, names, hashes, diagnostics, metadata, and (for small text comparisons) diff snippets can appear in the model conversation. Review outputs and root permissions accordingly.

See [Architecture](docs/ARCHITECTURE.md), [Threat Model](docs/THREAT_MODEL.md), [Product Positioning](docs/PRODUCT_POSITIONING.md), and the [Release Checklist](RELEASE_CHECKLIST.md).

## Requirements

- Node.js **20 or newer**.
- Python **3.10 or newer**.
- Claude Desktop with local MCP support, or Claude Code.
- One or more directories that you explicitly authorize DataDoctor to inspect.

The Python engine uses only Python's standard library. No `pip install` is required.

## Installation

```bash
git clone https://github.com/ayoubissa344-ship-it/datadoctor-mcp.git
cd datadoctor-mcp
npm install
npm run build
npm run test:all
```

If you downloaded a ZIP archive, extract it and run the same commands from the extracted project directory.

## Connect to Claude Desktop

Build the project first. Add a `datadoctor` entry to Claude Desktop's `claude_desktop_config.json` and replace the sample paths with absolute paths on your machine.

Common configuration locations:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

### macOS / Linux

```json
{
  "mcpServers": {
    "datadoctor": {
      "command": "node",
      "args": [
        "/absolute/path/to/datadoctor-mcp/dist/index.js",
        "--root",
        "/absolute/path/to/folder-you-want-claude-to-inspect"
      ]
    }
  }
}
```

### Windows

```json
{
  "mcpServers": {
    "datadoctor": {
      "command": "node",
      "args": [
        "C:\\absolute\\path\\to\\datadoctor-mcp\\dist\\index.js",
        "--root",
        "C:\\Users\\YourUser\\Documents\\DataToInspect"
      ]
    }
  }
}
```

Use the narrowest directories Claude needs. Multiple roots are supported by repeating `--root` and its path. Restart Claude Desktop after saving the configuration. For exact UI details, consult Anthropic's [local MCP server setup guide](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).

## Connect to Claude Code

From the repository directory, add a project-scoped stdio server:

```bash
claude mcp add --transport stdio datadoctor -- node "$PWD/dist/index.js" --root "$HOME/Documents/DataToInspect"
```

Check `claude mcp list` to confirm it is configured. CLI syntax may differ between Claude Code releases; refer to the installed version's documentation if the command parser changes.

## Run and inspect locally

```bash
npm run dev -- --root ./examples/sample-data
```

Or run the compiled entry point:

```bash
node dist/index.js --root ./examples/sample-data
```

The server uses stdio. Standard output is reserved for MCP protocol messages; diagnostics go to standard error. Do not add `console.log` statements to the server transport path.

For interactive protocol inspection, use the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector node dist/index.js --root ./examples/sample-data
```

### Runtime options

| Option | Meaning |
|---|---|
| `--root <directory>` | Grant access to a directory; repeat to add roots. Required unless `DATADOCTOR_ROOTS` is set. |
| `--python <executable>` | Python executable; defaults to `python3` (POSIX) or `python` (Windows). |
| `--timeout-ms <milliseconds>` | Python worker timeout from 1,000 to 300,000 ms; default 45,000 ms. |
| `--help` | Print usage to stderr and exit. |

Environment alternatives: `DATADOCTOR_PYTHON` selects the Python executable. `DATADOCTOR_ROOTS` supplies roots separated by `:` on POSIX or `;` on Windows. Explicit `--root` arguments are easier to audit and are recommended.

## Safety and integrity model

1. **Least privilege:** the operator explicitly chooses allowed roots.
2. **Canonical containment:** requested paths must resolve inside one of those roots.
3. **Symlink policy:** symlink paths are rejected; hidden entries and symlinks are skipped during scanning.
4. **No shell:** the Node process launches Python with an argument array and JSON stdin.
5. **Resource limits:** scan count/depth/bytes, per-file size, ZIP limits, worker timeout, and response size are bounded.
6. **Read-only default:** only `repair_data` writes.
7. **Write preconditions:** repair requires explicit confirmation and the expected source digest.
8. **Backup and post-check:** a non-overwriting backup is retained; the replacement is validated before success is returned.
9. **Honest scope:** structural checks, hashes, and heuristics are labelled as such. They do not prove business correctness, authenticity, or malware-free status.

No portable application-level path check can eliminate every race with another process running under the same OS identity. Do not allow concurrent applications to write a file while DataDoctor is repairing it. Use OS-level sandboxing and independent backups for high-value data.

## Testing

```bash
npm run test:python
npm test
npm run test:all
```

- Python unit tests run with the standard library only.
- `npm test` compiles TypeScript and runs a stdio MCP integration test against the built server. It verifies initialization, tool discovery, prompt discovery, and a file inspection call.
- CI runs the Node and Python version matrix defined in `.github/workflows/ci.yml`.

## Project structure

```text
datadoctor-mcp/
├── src/                       # TypeScript MCP server and prompts
├── python/datadoctor/         # Python analysis engine
├── tests/                     # Python unit + MCP stdio integration tests
├── scripts/                   # Cross-platform test helpers
├── docs/                      # Architecture, threat model, product positioning
├── examples/sample-data/      # Synthetic examples
├── .github/                   # CI, issue templates, Dependabot
├── README.md
├── README.ar.md
├── AUTHORS.md
├── NOTICE.md
├── LICENSE
├── SECURITY.md
└── CONTRIBUTING.md
```

## Roadmap

- [x] TypeScript MCP server using the official SDK.
- [x] Python standard-library analysis engine.
- [x] Root-scoped path access and bounded directory traversal.
- [x] JSON, CSV, XML, ZIP, SQLite, and selected UTF-8 checks.
- [x] SHA-256 inspection, duplicate grouping, and version comparison.
- [x] CSV dataset profiling with aggregate-only output.
- [x] Structured diagnosis and machine-readable audit reports.
- [x] Explicit, hash-preconditioned JSON/CSV normalization with backup and post-check.
- [x] Claude-oriented MCP prompts.
- [ ] Optional user-supplied JSON Schema and CSV schema validation.
- [ ] More format validators behind explicit resource budgets.
- [ ] JSONL and Parquet dataset profiling.
- [ ] Optional signed manifests and reproducible release artifacts.
- [ ] Claude Desktop Extension (`.mcpb`) packaging after dependency bundling and host validation.

Roadmap items are proposals, not features in the current release.

## Competitive landscape and positioning

DataDoctor does not claim to be the first file-integrity tool, data-quality validator, profiler, or MCP filesystem server. Existing projects already cover important parts of this space. The intended niche is the **local-first, AI-oriented evidence workflow** that connects scoped file inspection, explicit scan coverage, structural diagnosis, guarded normalization, retained backups, and post-write verification in one MCP interface.

See [Product Positioning and Landscape](docs/PRODUCT_POSITIONING.md) for the comparison and source links.

## Authorship, project identity, and license

DataDoctor MCP was originated and initially designed and implemented by **Ayoub Issa**. The copyright notice covers the original project code and documentation authored for this repository. See [AUTHORS.md](AUTHORS.md) and [NOTICE.md](NOTICE.md) for attribution and scope.

The project is distributed under the **MIT License**. MIT permits use, modification, redistribution, sublicensing, and sale subject to its notice condition. It does not reserve exclusive control over abstract ideas, general methods, or functionality. See [LICENSE](LICENSE).

## Contributing

Contributions and independent review are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request. Security reports should follow [SECURITY.md](SECURITY.md).

---

<div align="center">

**DataDoctor MCP — inspect with evidence. Change with safeguards. Verify the result.**

</div>
