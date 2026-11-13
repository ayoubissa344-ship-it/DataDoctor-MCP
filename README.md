DataDoctor MCP Evidence before edits. Verification after every write. 

A local-first data integrity and diagnostics toolkit for Claude, powered by the Model Context Protocol.

Inspect, validate, profile, compare, diagnose, and normalize supported data through ten focused tools backed by deterministic local processing.

Created and maintained by Ayoub Issa.

Features · MCP Tools · Installation · Claude Setup · Safety · Architecture · Roadmap

Overview 

DataDoctor MCP brings data inspection, structural validation, integrity analysis, dataset profiling, and controlled normalization into one interface for AI-assisted workflows.

Powered by a TypeScript MCP server and a deterministic Python analysis engine, it gives Claude access to ten specialized tools for working with local files and datasets.

Whether auditing a project directory, checking research data, comparing file versions, or preparing a controlled normalization, DataDoctor provides structured results that help make each operation traceable and verifiable.

Its design follows three principles:

Evidence before decisions: inspections return structured findings and validation results. Controlled modifications: write operations require explicit authorization and source verification. Verification after changes: successful normalization includes a post-write validation. 

DataDoctor distinguishes structural validity, data integrity, and semantic correctness rather than treating them as interchangeable.

Features Capability Description Directory auditing Recursive, bounded inspection with file statuses, hashes, and scan coverage Format validation Structural checks for JSON, CSV, XML, ZIP, SQLite, and selected UTF-8 text Dataset profiling CSV dimensions, missing values, inferred types, distinct-count estimates, and numeric ranges Duplicate detection Identify byte-identical files using SHA-256 Version comparison Compare file sizes, hashes, and supported text differences Error diagnosis Produce structured findings and evidence-based next steps Data normalization Normalize supported JSON and CSV files with explicit authorization Integrity verification Calculate SHA-256 and compare against a trusted expected digest Audit reporting Generate structured reports containing validation and coverage information AI-assisted workflows Expose specialized tools and prompts through MCP Supported formats Format Validation JSON Strict parsing CSV Strict parsing and consistent non-empty row widths XML Well-formedness and DTD/entity declaration restrictions ZIP Archive parsing and CRC verification SQLite Read-only PRAGMA quick_check UTF-8 text Character encoding validation Unknown/binary Metadata and SHA-256 inspection 

Structural validation does not certify business correctness, authenticity, or malware-free status.

MCP Tools 

DataDoctor exposes ten specialized tools through the Model Context Protocol.

Tool Capability Operation scan_data Directory auditing Read inspect_file File inspection and SHA-256 Read detect_corruption Structural validation Read find_duplicates Duplicate discovery Read profile_dataset CSV profiling Read compare_versions File comparison Read diagnose_errors Evidence-based diagnosis Read verify_integrity Integrity verification Read generate_report Structured audit reporting Read repair_data Controlled JSON/CSV normalization Write Tool capabilities 

scan_data

Performs recursive directory auditing and reports file-level validation states, SHA-256 digests, skipped entries, errors, and scan coverage.

inspect_file and detect_corruption

Inspect individual files, identify supported formats, calculate hashes, and execute the corresponding structural validators.

profile_dataset

Analyzes CSV datasets and returns row and column counts, null distributions, inferred types, distinct-count estimates, and numeric ranges without returning raw dataset rows.

find_duplicates

Groups byte-identical files using SHA-256. Results include scan coverage. Files are identified, not deleted or modified.

compare_versions

Compares two files using size and SHA-256, with optional unified text diffs for supported small UTF-8 files.

diagnose_errors

Combines validation findings with structured explanations and recommended next steps.

verify_integrity

Calculates SHA-256 and optionally compares the result against a caller-supplied trusted digest.

generate_report

Produces a machine-readable datadoctor-scan-report containing timestamps, file hashes, validation states, coverage, skipped entries, errors, and truncation information.

repair_data

Provides two controlled normalization strategies:

Strategy Operation json_format Formats already-valid JSON using stable UTF-8 output, two-space indentation, and a final newline csv_normalize Normalizes quoting and line endings in structurally consistent CSV files 

Both strategies require explicit confirmation, an expected SHA-256 from a preceding inspection, a retained backup, and post-write validation.

These operations normalize supported data; they do not reconstruct corrupted content or recover missing information.

MCP Prompts 

DataDoctor also provides three prompts for structured AI-assisted workflows:

audit-data-directory — guides Claude through a read-only directory audit. explain-file-integrity — explains validation evidence and integrity findings. prepare-safe-repair — prepares a repair plan requiring separate user approval before modification. 

Prompts guide the assistant. Actual file access and write safeguards are independently enforced by the analysis engine.

Why DataDoctor? 

AI assistants can analyze information, but reliable data operations also require deterministic inspection, reproducible checks, explicit authorization, and verification.

DataDoctor provides these operations through a dedicated local MCP interface.

Its intended applications include:

Software development: inspect project files, configurations, archives, and databases. Scientific research: evaluate dataset structure and record integrity evidence. Data analysis: understand missingness, inferred types, and numerical distributions. Education: investigate malformed structured data through guided diagnostics. Team workflows: perform repeatable local audits before processing or transferring data. Architecture Claude Desktop / Claude Code | | MCP over stdio v +---------------------------+ | TypeScript MCP Server | | | | Official MCP SDK | | Zod Input Schemas | | Tools and Prompts | | Process and Response Limits +---------------------------+ | | Bounded JSON request v +---------------------------+ | Python Analysis Engine | | | | File Validation | | Hashing and Profiling | | Diagnosis and Reporting | | Controlled Normalization | +---------------------------+ | v Authorized Local Directories 

The TypeScript server manages MCP communication, input validation, subprocess execution, timeouts, and response limits.

The Python engine performs deterministic file operations using the Python standard library.

Each tool call starts a separate Python worker. Communication uses JSON over stdin and stdout, with stdout reserved for the worker response.

DataDoctor uses local stdio communication and does not make network requests during file analysis.

Tool results are returned to the connected AI host and may contain file paths, metadata, hashes, diagnostics, and supported text-diff snippets.

See the technical documentation:

Architecture Threat Model Product Positioning Requirements Node.js 20+ Python 3.10+ Claude Desktop with local MCP support, or Claude Code. Explicitly authorized local directories. 

The Python engine requires no third-party Python packages.

Installation 

Clone the repository:

git clone https://github.com/ayoubissa344-ship-it/datadoctor-mcp.git cd datadoctor-mcp 

Install dependencies and build:

npm install npm run build 

Run the test suite:

npm run test:all 

Alternatively, download and extract the repository ZIP archive before executing these commands.

Connect to Claude Claude Desktop 

Build the project first, then add a datadoctor server entry to claude_desktop_config.json.

Configuration locations:

macOS: ~/Library/Application Support/Claude/claude_desktop_config.json Windows: %APPDATA%\Claude\claude_desktop_config.json Linux: ~/.config/Claude/claude_desktop_config.json 

macOS / Linux

{ "mcpServers": { "datadoctor": { "command": "node", "args": [ "/absolute/path/to/datadoctor-mcp/dist/index.js", "--root", "/absolute/path/to/folder-you-want-claude-to-inspect" ] } } } 

Windows

{ "mcpServers": { "datadoctor": { "command": "node", "args": [ "C:\\absolute\\path\\to\\datadoctor-mcp\\dist\\index.js", "--root", "C:\\Users\\YourUser\\Documents\\DataToInspect" ] } } } 

Replace the example paths with actual absolute paths. Multiple authorized roots can be configured by repeating --root and its path.

Restart Claude Desktop after saving the configuration.

For additional setup instructions, see Anthropic's local MCP server setup guide.

Claude Code 

Register a project-scoped server:

claude mcp add --transport stdio datadoctor -- node "$PWD/dist/index.js" --root "$HOME/Documents/DataToInspect" 

Verify the configuration:

claude mcp list Local Execution 

Development mode:

npm run dev -- --root ./examples/sample-data 

Compiled execution:

node dist/index.js --root ./examples/sample-data Runtime options Option Description --root <directory> Authorized directory; repeatable --python <executable> Python executable --timeout-ms <milliseconds> Worker timeout; 1,000–300,000 ms, default 45,000 --help Display usage information 

Environment variables:

DATADOCTOR_PYTHON selects the Python executable. DATADOCTOR_ROOTS supplies authorized roots, separated by : on POSIX or ; on Windows. Protocol inspection 

DataDoctor can also be inspected through the MCP Inspector:

npx @modelcontextprotocol/inspector node dist/index.js --root ./examples/sample-data 

Standard output is reserved for MCP protocol communication. Server diagnostics are written to standard error.

Safety and Integrity 

DataDoctor uses a read-only-by-default model with explicit safeguards for file modifications.

Protection Implementation Access control Explicitly configured directory roots Path containment Canonical path checks Symlink handling Symlink paths rejected; hidden entries and symlinks skipped during scans Process execution Python launched without a shell Resource management Bounded scanning, file sizes, ZIP limits, timeouts, and response sizes Default operation Read-only Write authorization Explicit confirmation and expected SHA-256 Backup protection Exclusive creation of a non-overwriting backup Post-write verification Validation after atomic replacement Repair safeguards 

Every repair_data operation requires:

confirm: true. An exact expected_sha256 obtained from a preceding inspection. A source digest matching the expected value. Successful exclusive creation of <filename>.datadoctor.bak. Preparation of the replacement in a same-directory temporary file. A final source-digest check before replacement. Atomic replacement and post-write validation. 

Existing backups are never overwritten, and backups are retained after successful normalization.

For important data, maintain independent backups as well. Concurrent processes operating under the same OS identity can still create narrow race conditions; consult the Threat Model before using DataDoctor in sensitive environments.

Testing 

Run individual or combined test suites:

npm run test:python npm test npm run test:all Python unit tests use the standard library. npm test compiles TypeScript and runs an MCP stdio integration test. The integration test checks initialization, tool discovery, prompt discovery, and file inspection. CI executes the configured Node.js and Python version matrix. Project Structure datadoctor-mcp/ ├── src/ # TypeScript MCP server and prompts ├── python/datadoctor/ # Python analysis engine ├── tests/ # Unit and integration tests ├── scripts/ # Test helpers ├── docs/ # Technical and product documentation ├── examples/sample-data/ # Synthetic test data ├── .github/ # CI, issue templates, Dependabot ├── README.md ├── README.ar.md ├── AUTHORS.md ├── NOTICE.md ├── LICENSE ├── SECURITY.md ├── CONTRIBUTING.md └── RELEASE_CHECKLIST.md Roadmap Implemented [x] Official TypeScript MCP server. [x] Python standard-library analysis engine. [x] Root-scoped directory access. [x] Bounded recursive scanning. [x] JSON, CSV, XML, ZIP, SQLite, and UTF-8 validation. [x] SHA-256 inspection and integrity comparison. [x] Duplicate discovery and version comparison. [x] CSV dataset profiling. [x] Structured diagnosis and audit reporting. [x] Guarded JSON and CSV normalization. [x] Retained backups and post-write validation. [x] Claude-oriented MCP prompts. Planned [ ] Optional JSON Schema and CSV schema validation. [ ] Additional format validators. [ ] JSONL and Parquet dataset profiling. [ ] Optional signed manifests and reproducible release artifacts. [ ] Claude Desktop Extension (.mcpb) packaging after dependency bundling and host validation. 

Planned items are not part of the current implementation.

Product Positioning 

DataDoctor focuses on combining local file inspection, data integrity checks, structured diagnostics, and guarded normalization in an AI-accessible workflow.

Its product positioning and comparisons with related tools are documented separately.

See Product Positioning and Landscape.

Authorship and License 

DataDoctor MCP was originated and initially designed and implemented by Ayoub Issa.

Project attribution and copyright scope are documented in:

AUTHORS.md NOTICE.md 

DataDoctor MCP is distributed under the MIT License, permitting use, modification, redistribution, sublicensing, and commercial distribution subject to its license conditions.

See LICENSE for the complete terms.

Contributing 

Contributions and independent technical reviews are welcome.

Before contributing, consult:

CONTRIBUTING.md SECURITY.md 

DataDoctor MCP

Inspect with evidence. Change with safeguards. Verify the result.