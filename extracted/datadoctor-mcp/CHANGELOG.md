# Changelog

All notable project changes are documented here. The format follows Keep a Changelog; versioning follows Semantic Versioning.

## [0.2.0] - 2026-11-12

### Added
- Added the `profile_dataset` MCP tool for bounded CSV profiling with aggregate-only results.
- Added three Claude-oriented prompts: directory audit, file-integrity explanation, and approval-gated repair planning.
- Added explicit scan byte budgets and truncation reasons for file-count, depth, and aggregate-byte limits.
- Added project authorship and attribution documents, Arabic README, citation metadata, product positioning review, and expanded engineering documentation.
- Added cross-platform Python test runner and `npm run test:all`.

### Changed
- Strengthened stable file reads and SHA-256 identity checks around inspection and small-file comparison.
- Tightened repair preconditions: `confirm: true` and a required expected SHA-256 are both mandatory.
- Updated project version and copyright attribution to Ayoub Issa.
- Expanded tests for profiles, scan coverage, stale repair hashes, XML DTD rejection, and trusted-digest verification.

### Security
- Refused to replace an existing backup.
- Kept unknown and skipped formats explicitly unchecked rather than treating them as valid.
- Documented that scan truncation, hash provenance, semantic validation, and concurrent filesystem mutation have distinct limitations.

## [0.1.0] - 2026-11-12

### Added
- Initial TypeScript MCP server and Python standard-library engine.
- File inspection, directory scanning, format checks, duplicate detection, comparison, diagnosis, integrity verification, report generation, and narrow JSON/CSV normalization.
- Initial Claude configuration examples, tests, CI workflow, and security documentation.
