# Auth And Roles

## Auth Provider
Supabase Auth is the identity provider. FastAPI validates JWTs and loads tenant membership before serving tenant-owned data.

## Roles
| Role | Permissions |
| --- | --- |
| Owner | Manage tenant, users, profiles, uploads, approvals, exports, audit logs. |
| Admin | Manage profiles, uploads, approvals, exports, recommendations. |
| Strategist | Upload files, review keywords, generate plans, propose approvals. |
| Viewer | Read profiles, plans, reports, and audit logs without changing state. |

## Approval Permissions
| Action | Minimum role |
| --- | --- |
| Approve keyword list | Strategist |
| Approve campaign plan | Admin |
| Approve bulk export | Admin |
| Approve optimization recommendation | Admin |
| Manage users | Owner |

## Acceptance Criteria
- Backend rejects all tenant access without active membership.
- Viewer role cannot mutate state.
- Approval records store actor, role, timestamp, object, and decision.

