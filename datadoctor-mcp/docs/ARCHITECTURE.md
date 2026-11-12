# DataDoctor MCP Architecture

**Version:** 0.2.0  
**Primary author:** Ayoub Issa  
**Last updated:** 2026-11-12

## 1. Design goals

DataDoctor is built around five engineering goals:

1. **Evidence-first outputs:** return the exact validator result, digest, scope, and limitations instead of a vague healthy/unhealthy label.
2. **Local-first processing:** perform analysis in a local Python worker; do not upload user files to a DataDoctor service.
3. **Least-privilege access:** only canonical directories supplied by the operator are eligible roots.
4. **Bounded execution:** limit file size, traversal, archive expansion, subprocess lifetime, and response size.
5. **Guarded mutation:** keep inspection read-only and make the small supported write operations conditional, backed up, and post-verified.

## 2. Component model

```text
MCP Host (Claude Desktop / Claude Code)
            |
            | stdio transport
            v
TypeScript MCP Server (src/index.ts)
  - MCP SDK server and protocol lifecycle
  - Zod input schemas
  - Tool annotations and prompt templates
  - Root canonicalization at startup
  - Python subprocess timeout/output cap
            |
            | one JSON request over stdin; shell=false
            v
Python worker (python/datadoctor/engine.py)
  - Request dispatch
  - Independent root and path validation
  - File inspection and SHA-256
  - Validators and CSV profiling
  - Diagnostic result construction
  - Guarded normalization and post-check
            |
            v
Configured local filesystem roots
```

The server starts a fresh Python process per tool call. This avoids a persistent cross-request worker state and makes the request/response boundary explicit. It adds process startup overhead; that trade-off is accepted in this version in exchange for simplicity and isolation of operation state.

## 3. Request lifecycle

1. The MCP host sends a tool call.
2. The TypeScript SDK validates it against the registered Zod schema.
3. The server builds a JSON object containing the operation, arguments, and startup-configured allowed roots.
4. Node starts the configured Python executable with `spawn(..., { shell: false })`.
5. The JSON request is written to stdin. Python resolves roots and paths independently before operating.
6. Python returns one JSON response on stdout. Standard output contains no diagnostic logging.
7. Node enforces timeout and byte limits, parses the response, and returns structured text content to the MCP host.

The server forwards a small, explicit environment allowlist to Python. It does not interpolate paths into a shell command.

## 4. Filesystem boundary

At startup, TypeScript resolves each configured root to a canonical absolute path and checks that it is a directory. The Python worker independently resolves the same roots. Every user path is canonicalized and checked against at least one root. Supplied symlink components are rejected, and recursive traversal skips hidden entries and symlinks.

The checks are defense in depth, not an OS sandbox. An adversarial local process running as the same user may race path operations. Operators should use a dedicated data directory, avoid concurrent writers during repair, and apply OS-level isolation where the files are high value.

## 5. File analysis pipeline

### 5.1 Inspection

For a regular file, the engine obtains file metadata, invokes the selected validator where available, calculates SHA-256, and compares file identity/timestamps before and after inspection. If the file changes during inspection, the combined inspection is rejected rather than mixing observations from different file states.

For ordinary text formats and ZIP, bytes are read through a no-follow file descriptor where supported, with regular-file and metadata checks. SQLite uses a read-only connection and `PRAGMA quick_check`.

### 5.2 Validators

| Format | Implementation | Bounds / limitation |
|---|---|---|
| JSON | Python strict JSON parser | Rejects non-standard numeric constants |
| CSV | Strict standard-library CSV reader | Requires consistent non-empty row widths |
| XML | ElementTree | DTD and entity declarations rejected; no external XSD validation |
| ZIP | `zipfile` parser and `testzip()` | Up to 10,000 entries and 250 MiB declared uncompressed bytes |
| SQLite | Read-only SQLite URI and `PRAGMA quick_check` | No writes, page repair, or full semantic inspection |
| Text | UTF-8 decoder | Applied only to known text extensions |
| Unknown/binary | Metadata and digest | Returns unchecked status, not a valid status |

### 5.3 Directory traversal and coverage

The scanner records inspected files separately from skipped files and errors. It exposes:

- `files_seen`: file records represented in the response;
- `files_scanned`: files inspected successfully enough to return a validator state;
- `valid`, `invalid`, and `unchecked`: mutually exclusive states among inspected records;
- `skipped` and `errors`;
- `bytes_hashed` and `bytes_observed` for returned file records;
- `truncated` and `truncation_reasons`.

If a budget is reached, downstream summaries must state that coverage is partial. A zero-error truncated scan is not a clean complete audit.

## 6. Dataset profiling

`profile_dataset` is a bounded CSV profiler. It returns column labels and aggregate statistics only: null/non-null counts, heuristic cell-type distributions, numeric bounds, and capped distinct-value lower bounds. It does not return rows or distinct sample values. Aggregate min/max values may equal values present in the source, and column labels may be sensitive; the output is not anonymous data.

Type inference is heuristic. It is not a schema declaration or a substitute for domain-specific checks, Great Expectations, Pandera, or another rule engine.

## 7. Mutation protocol

Only `repair_data` writes. Current strategies are normalization-only:

- `json_format`: the source must already parse as strict JSON;
- `csv_normalize`: the source must already parse and pass the row-width check.

The operation requires `confirm: true` and an `expected_sha256` previously obtained from inspection. It then:

1. Reads a stable byte snapshot within the per-file limit.
2. Computes the current digest and compares it with the supplied precondition.
3. Builds the normalized bytes without changing the source.
4. Creates `<name>.datadoctor.bak` using exclusive file creation.
5. Flushes the backup and verifies its digest.
6. Rechecks the source digest before replacement.
7. Writes a same-directory temporary file and flushes it.
8. Rechecks the source digest again.
9. Replaces the source using same-directory `os.replace`.
10. Re-inspects the replacement and returns success only if the expected format validator passes.

If post-replacement validation fails, the engine attempts rollback from its in-memory source snapshot; the backup is retained. Portable file APIs do not provide a universal atomic compare-and-swap tied to content hash, and another local process can race the final check/replace window. This is documented as a residual risk.

## 8. Resource budgets

| Budget | Default | Maximum |
|---|---:|---:|
| Files per directory scan | 1,000 | 10,000 |
| Directory depth | 8 | 32 |
| File size for format validation | 25 MiB | Fixed in this version |
| Total bytes hashed in scan | 512 MiB | 2 GiB |
| ZIP entry count | 10,000 | Fixed |
| ZIP declared uncompressed size | 250 MiB | Fixed |
| CSV rows profiled | 100,000 | 1,000,000 |
| CSV columns profiled | 500 | Fixed |
| Distinct tracking per column | 10,000 | Fixed |
| Distinct tracking across profile | 100,000 | Fixed |
| Python operation timeout | 45 seconds | 300 seconds |
| Python worker stdout | 7 MiB | Fixed |
| Text diff file size | 1 MiB per file | Fixed |
| Text diff combined lines | 10,000 | Fixed |
| Text diff output | 20,000 characters | Fixed |

These budgets reduce accidental resource exhaustion but are not a replacement for OS-level CPU, memory, and disk quotas.

## 9. MCP tools and prompts

Ten tools are registered: `scan_data`, `inspect_file`, `detect_corruption`, `find_duplicates`, `profile_dataset`, `compare_versions`, `diagnose_errors`, `verify_integrity`, `generate_report`, and `repair_data`.

Three prompts are registered: `audit-data-directory`, `explain-file-integrity`, and `prepare-safe-repair`. Prompts are workflow guidance and are not relied on as the security enforcement layer. Preconditions are independently checked by Python.

## 10. Testing strategy

- Python unit tests cover parsing, path boundaries, symlink policy, depth/byte limits, duplicate hashes, profiles, repair preconditions, backups, and integrity checks.
- The Node stdio integration test checks protocol initialization, tool discovery, prompt discovery, and one inspection call against synthetic fixtures.
- CI runs the TypeScript build and integration test alongside Python tests across a Node/Python matrix.

A CI result is required before a tagged release. The source package should not be described as verified against a real Claude Desktop installation until a manual host integration test has been completed on that release.
