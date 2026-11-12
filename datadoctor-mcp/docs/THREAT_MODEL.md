# DataDoctor MCP Threat Model

**Version:** 0.2.0  
**Last reviewed:** 2026-11-12

## Security objectives

- Keep file operations within directories explicitly granted by the operator.
- Avoid unintended source modification during inspection.
- Make limited write operations explicit, preconditioned, backed up, and post-verified.
- Avoid false-positive claims when a scan or validator did not cover the data.
- Bound work performed on untrusted or malformed files.

## Assets

1. Confidentiality of files in configured roots.
2. Integrity of source files and repair backups.
3. Availability of the MCP host and local worker.
4. Accuracy and completeness of the diagnostic result.
5. User trust in the distinction between observed facts and inferred explanations.

## Trust boundaries

| Boundary | Untrusted input | Controls |
|---|---|---|
| MCP host → TypeScript | Tool arguments, paths, numeric limits | Zod schemas, path length and numeric ranges |
| TypeScript → Python | JSON request | No shell, fixed script path, one request per worker, environment allowlist |
| Python → filesystem | User-selected paths and file bytes | Independent canonical-root check, regular-file checks, symlink rejection, bounded reads |
| File contents → model | Names, diagnostics, diffs, aggregates | No execution of content; raw content is not returned by profiling; text diff is bounded |
| Repair tool → filesystem | Explicit write request | Confirmation, expected digest, exclusive backup, temp file, replacement, post-check |

## Threat analysis

| Threat | Controls | Residual risk |
|---|---|---|
| Path traversal outside an approved root | Canonical path resolution and root containment in Python | Filesystem races cannot be eliminated completely with portable application-level checks |
| Symlink path escapes root | User-supplied symlink components rejected; traversal uses `followlinks=False` and skips symlinks; no-follow open flags where supported | Another process with the same account may race path replacement |
| Special-file/FIFO blocking | Regular-file checks, `O_NONBLOCK` where available, `O_NOFOLLOW` where available | Platform-specific semantics vary |
| Malformed structured content | Standard-library parsers, strict parsing, XML DTD/entity rejection | Parser bugs and unexpected parser resource use remain possible |
| ZIP decompression/resource abuse | Entry and declared-uncompressed-size limits, worker timeout, archive file-size limit | Declared sizes and runtime cost may not perfectly predict every workload |
| Excessive file count/depth/size | Bounded traversal and aggregate byte budget | Metadata operations and directory enumeration still consume resources |
| Python worker hangs or emits huge output | Timeout, stdout byte cap, stderr cap | OS process scheduling and platform behavior may vary |
| Accidental repair | `repair_data` separate from inspection; required `confirm=true` and expected digest | MCP prompt text is not user authorization; operators must approve writes in the host workflow |
| Stale repair plan | Expected SHA-256 comparison | A concurrent writer can race after the final digest check |
| Existing backup overwritten | Exclusive backup creation (`xb`) | Backup storage can still fail due disk or permission errors |
| False integrity claim | Expected digest required for `integrity_verified: true`; scope language in results | The trustworthiness of the external expected digest remains the caller's responsibility |
| Data exposed through AI host | Local processing; bounded metadata results; no profiling raw rows | Tool outputs, paths, names, and small text diffs are visible to the connected AI host |
| Instruction injection inside files | File content is treated as data; worker does not execute it | The model may still misinterpret text returned to it; host prompt-injection defenses remain relevant |

## Security limitations

- DataDoctor is not a malware scanner, antivirus engine, sandbox, DLP system, or provenance verifier.
- It does not protect against a malicious process running with the same OS user privileges.
- It does not guarantee protection against all symlink/time-of-check-time-of-use races.
- It does not validate business semantics unless a future, explicit schema/rule layer is added.
- It does not reconstruct corrupted or missing information.
- It is local stdio software; a network-facing deployment is out of scope for this release.
- The model host receives tool output. DataDoctor cannot control host-side logging or retention.

## Deployment guidance

1. Grant a dedicated working directory, not the entire home folder or filesystem.
2. Keep important source data backed up independently of DataDoctor's per-repair backup.
3. Avoid repairing files while another process is modifying them.
4. Review diffs and data paths before sharing tool results with an AI host.
5. Pin the project version and review changes before upgrading.
6. Run Claude and DataDoctor under an OS account with only the permissions it needs.

## Responsible disclosure

Please follow [SECURITY.md](../SECURITY.md). Use harmless, owned test data and do not publish details before a fix is coordinated.
