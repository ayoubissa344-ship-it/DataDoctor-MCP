# Security Policy

## Supported versions

The latest tagged release is the supported version. DataDoctor is pre-1.0; pin versions and review changes before upgrading.

## Reporting a vulnerability

Please do not publish details of an undisclosed vulnerability in a public issue. Use GitHub's **Report a vulnerability** feature for this repository when private vulnerability reporting is enabled. If it is unavailable, contact the maintainer through the contact method published on the repository profile.

Include:

- Affected DataDoctor version or commit and operating system.
- Required configuration and preconditions.
- A minimal, harmless reproduction using files and directories you own.
- The security boundary crossed and demonstrated impact.
- Suggested mitigation, if known.

Do not include private data, credentials, or destructive proof-of-concept actions. Do not test against systems or files you do not own or have permission to assess.

## Security design

DataDoctor uses explicitly configured roots, independent path checks in the Python engine, symlink rejection, no-shell process invocation, bounded file and scan operations, a worker timeout/output cap, read-only defaults, expected-digest repair preconditions, exclusive backups, temporary replacement files, and post-write validation.

These controls reduce risk but do not replace OS sandboxing and cannot eliminate every race with another process running under the same OS account. Operators remain responsible for root selection and independent backups.
