# Contributing

Thank you for helping improve DataDoctor MCP.

## Before opening an issue

- Search existing issues and discussions.
- Include the DataDoctor version, operating system, Node.js version, and Python version.
- Reproduce with synthetic or sanitized files.
- Separate observed behavior from suspected root cause.
- For security concerns, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development setup

Requirements: Node.js 20+, Python 3.10+.

```bash
npm install
npm run typecheck
npm run test:python
npm test
npm run test:all
```

The Python engine uses only the standard library. Do not add a runtime dependency without describing its security, packaging, and resource implications.

## Engineering expectations

- Keep MCP transport, schemas, process management, and prompts in `src/`.
- Keep deterministic file operations in `python/datadoctor/`.
- Add a regression test for every bug fix.
- Add negative tests for path boundaries, malformed input, size budgets, concurrent modification preconditions, and write failures where applicable.
- Preserve read-only-by-default behavior.
- Never create a repair strategy that guesses missing user data.
- Make partial coverage visible in result schemas.
- Distinguish syntax/structure validation from semantic/business-rule validation.
- Keep MCP protocol output on stdout and diagnostic logs on stderr.
- Update README, architecture, threat model, and changelog when behavior changes.

## Pull requests

A pull request should explain the problem, its impact, the chosen design, tests added/run, and any limitations that remain. Avoid bundling unrelated formatting or refactoring changes with security-sensitive fixes.

## Commit message examples

- `feat(profile): add bounded CSV column statistics`
- `fix(scan): report aggregate byte-budget truncation`
- `fix(repair): require expected digest before replacement`
- `test(security): cover symlink and path boundary cases`
- `docs(architecture): describe repair preconditions`

## Attribution

Contributions are credited through repository history and project acknowledgements. Unless otherwise agreed in writing, contributions are licensed under the repository's MIT License.
