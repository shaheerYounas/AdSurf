# CI/CD Plan

## CI Checks
| Check | Purpose |
| --- | --- |
| Markdown lint | Documentation quality. |
| TypeScript checks | Frontend correctness when scaffolded. |
| Python lint/type checks | Backend and worker quality. |
| pytest | Rule and integration tests. |
| Vitest | Frontend unit tests. |
| Playwright | E2E workflow tests. |
| Secret scan | Prevent credential leaks. |

## CD Gates
Deploy only after tests, migrations, environment validation, and approval-flow smoke checks pass.

