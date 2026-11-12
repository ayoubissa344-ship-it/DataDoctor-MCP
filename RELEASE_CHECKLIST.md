# Release checklist

Use this checklist before tagging a public release. A GitHub Actions run is the authoritative reproducible build for the published source revision.

## Required gates

- [ ] `npm install --no-audit --no-fund` completes from a clean checkout.
- [ ] `npm run typecheck` passes using the pinned MCP SDK and TypeScript dependencies.
- [ ] `npm run test:python` passes on the supported Python matrix.
- [ ] `npm test` builds the TypeScript server and passes the MCP stdio integration tests.
- [ ] A manual smoke test passes with Claude Desktop on one supported desktop OS.
- [ ] A manual smoke test passes with Claude Code.
- [ ] Test a directory containing at least 1,000 files and confirm scan coverage/truncation is reported accurately.
- [ ] Test a directory exceeding the configured file/byte/depth budgets and confirm no incomplete scan is reported as complete.
- [ ] Test a read-only audit and confirm source-file hashes/metadata are unchanged.
- [ ] Test a JSON and CSV normalization on disposable copies; confirm exclusive backup creation and post-write validation.
- [ ] Review `SECURITY.md`, `docs/THREAT_MODEL.md`, `docs/ARCHITECTURE.md`, and the release notes.
- [ ] Confirm the repository URL, issue URL, author attribution, license, and version metadata are correct.

## Release discipline

Do not describe a release as production-verified until all required gates above have passed. Record any skipped platform or host tests in the release notes. Never test repair operations on the only copy of valuable data.
