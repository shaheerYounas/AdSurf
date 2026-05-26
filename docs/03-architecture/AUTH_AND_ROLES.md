# Auth And Roles

## Auth Provider
Supabase Auth is the identity provider. FastAPI validates JWTs and loads workspace membership before serving workspace-owned data.

## Batch 2 Auth Adapter Design
| Adapter | Environment | Behavior |
| --- | --- | --- |
| Local header adapter | local/test only | Uses explicit test headers for `x-user-id` and `x-test-workspaces`. Missing user returns 401; missing workspace membership returns 403. |
| Supabase JWT adapter | preview/staging/production | Skeleton is present. Deployed environments fail closed unless Supabase JWT verification is configured. |

Local/test header auth is not production auth. It exists only to keep tests and local scaffolding usable without secrets.

`APP_ENV` must be set to one of `local`, `test`, `preview`, `staging`, or `production`. Missing or unknown values fail closed for workspace-scoped authentication.

## Local/Test Workspace Header
Use `x-test-workspaces` as a comma-separated role map:

```text
x-test-workspaces: {workspace_id}:analyst,{workspace_id}:viewer
```

Each requested workspace receives only its mapped role. A role in one workspace does not apply to any other workspace.

## Roles
| Role | Permissions |
| --- | --- |
| owner | Manage workspace, users, profiles, uploads, approvals, exports, audit logs. |
| admin | Manage profiles, uploads, approvals, exports, recommendations. |
| analyst | Upload files, review keywords, generate plans, and prepare approval evidence. |
| approver | Approve keyword sets, campaign plans, exports, and recommendations where policy allows. |
| viewer | Read profiles, plans, reports, and audit logs without changing state. |

## Product Profile Permissions
| Action | Allowed roles |
| --- | --- |
| Create product profile | owner, admin, analyst |
| Update product profile | owner, admin, analyst |
| List product profiles | owner, admin, analyst, approver, viewer |
| Get product profile | owner, admin, analyst, approver, viewer |

## Approval Permissions
| Action | Minimum role |
| --- | --- |
| Approve keyword list | approver |
| Approve campaign plan | approver |
| Approve bulk export | approver |
| Approve optimization recommendation | approver |
| Manage users | owner |

## Acceptance Criteria
- Backend rejects all workspace access without active membership.
- `viewer` role cannot mutate state.
- Approval records store actor, role, timestamp, object, and decision.
