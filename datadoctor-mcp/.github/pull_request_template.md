## Summary

Describe the change and the user problem it addresses.

## Validation

- [ ] `npm run typecheck`
- [ ] `npm run test:python`
- [ ] `npm test`
- [ ] Documentation updated

## Safety review

- [ ] Read-only behavior is preserved unless a write is explicitly requested.
- [ ] Path containment and symlink policy are preserved.
- [ ] Resource limits and error paths are covered.
- [ ] New repair behavior has precondition, backup, rollback, and post-write tests.
