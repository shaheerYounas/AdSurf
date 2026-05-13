# Observability

## What To Log
| Signal | Purpose |
| --- | --- |
| API request id | Trace user actions across services. |
| Tenant id | Debug within tenant scope without exposing data. |
| Job lifecycle | Track processing, retries, failures, duration. |
| Rule version | Explain why decisions were made. |
| AI run metadata | Provider, model, schema, status, latency. |
| Approval event | Actor, role, object, decision, timestamp. |

## Metrics
- Upload processing duration.
- Column mapping confidence distribution.
- Campaign generation duration.
- Export validation failure rate.
- Recommendation creation count by type.
- Approval queue aging.
- Safety incident count.

## Acceptance Criteria
Every customer-impacting decision can be reconstructed from logs, database records, rule inputs, and approval history.

