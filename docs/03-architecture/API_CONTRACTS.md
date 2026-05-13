# API Contracts

## Contract Style
REST endpoints return JSON, use Supabase Auth bearer tokens, enforce tenant scope server-side, and write audit logs for customer-impacting state changes.

## Routes
| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/v1/me` | Current user, tenants, roles. |
| GET | `/v1/product-profiles` | List tenant product profiles. |
| POST | `/v1/product-profiles` | Create product profile. |
| PATCH | `/v1/product-profiles/{id}` | Update product profile defaults. |
| POST | `/v1/uploads` | Create upload record and storage target. |
| GET | `/v1/uploads/{id}` | Upload status, mappings, parse summary. |
| POST | `/v1/uploads/{id}/column-mappings` | Save reviewed column mapping. |
| POST | `/v1/uploads/{id}/process` | Enqueue cleaning and scoring job. |
| GET | `/v1/product-profiles/{id}/keywords` | List candidates, scores, statuses. |
| POST | `/v1/keywords/approvals` | Approve or reject keyword candidates. |
| POST | `/v1/campaign-plans` | Generate plan from approved keywords. |
| GET | `/v1/campaign-plans/{id}` | Review plan, groups, negatives, validation. |
| POST | `/v1/campaign-plans/{id}/approve` | Approve campaign plan for export. |
| POST | `/v1/bulk-exports` | Generate bulk sheet from approved plan. |
| GET | `/v1/bulk-exports/{id}` | Export status and signed download URL if allowed. |
| POST | `/v1/monitoring-uploads` | Upload performance report. |
| GET | `/v1/product-profiles/{id}/monitoring` | 14-day metrics and health timeline. |
| GET | `/v1/recommendations` | Approval queue. |
| POST | `/v1/recommendations/{id}/decision` | Approve or reject recommendation. |
| GET | `/v1/audit-logs` | Tenant audit log. |
| GET | `/v1/admin/health` | Health check. |

## State-Changing Acceptance
State-changing routes must validate role, tenant, object status, idempotency, and approval requirements before writing changes.

