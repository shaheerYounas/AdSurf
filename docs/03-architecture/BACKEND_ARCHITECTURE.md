# Backend Architecture

## Responsibilities
| Area | Backend owns |
| --- | --- |
| Auth enforcement | Validate auth through an adapter, load workspace membership, and enforce role permissions. |
| API contracts | Stable REST endpoints and response schemas. |
| Rule orchestration | Invoke deterministic scoring, campaign, negative, and optimization rules. |
| Job creation | Create worker jobs for long-running file, export, and monitoring tasks. |
| Audit logging | Persist immutable decision and approval events. |
| AI gateway | Call provider-agnostic AI services with structured schemas and logs. |
| Persistence | Use config-driven database repositories for workspace-owned records. |

## Batch 2 Persistence And Auth Boundary
| Area | Decision |
| --- | --- |
| Database connection | `DATABASE_URL` drives the SQLAlchemy connection layer. Missing `DATABASE_URL` is allowed only in local/test where an explicit local repository adapter is used. |
| Product profiles | Product profile CRUD is repository-backed and always scoped by `workspace_id`. |
| Auth adapter | Local/test uses explicit headers for user and per-workspace role mapping. Preview/staging/production must use the Supabase JWT adapter path and fail closed if it is not configured. |
| Deferred auth work | Full Supabase JWT verification and database-backed membership lookup are structured but not fully wired until the next hardening pass. |
| Role enforcement | Product profile reads allow `owner`, `admin`, `analyst`, `approver`, `viewer`; writes allow `owner`, `admin`, `analyst`. |

## Non-Responsibilities
- The backend does not run unrestricted AI decision-making.
- The backend does not execute live Amazon Ads changes in MVP.
- The backend does not trust frontend workspace or role claims without verification.
- The backend does not use local/test header auth in staging or production.
- The backend treats missing or unknown `APP_ENV` as an auth configuration failure.

## Acceptance Criteria
- All workspace-scoped endpoints reject cross-workspace access.
- Every state-changing endpoint writes an audit log where customer-impacting.
