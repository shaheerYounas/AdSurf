# Backend Architecture

## Responsibilities
| Area | Backend owns |
| --- | --- |
| Auth enforcement | Validate Supabase JWT and tenant membership. |
| API contracts | Stable REST endpoints and response schemas. |
| Rule orchestration | Invoke deterministic scoring, campaign, negative, and optimization rules. |
| Job creation | Create worker jobs for long-running file, export, and monitoring tasks. |
| Audit logging | Persist immutable decision and approval events. |
| AI gateway | Call provider-agnostic AI services with structured schemas and logs. |

## Non-Responsibilities
- The backend does not run unrestricted AI decision-making.
- The backend does not execute live Amazon Ads changes in MVP.
- The backend does not trust frontend tenant or role claims without verification.

## Acceptance Criteria
- All tenant-scoped endpoints reject cross-tenant access.
- Every state-changing endpoint writes an audit log where customer-impacting.

