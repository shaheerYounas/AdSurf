# Performance Requirements

| Area | MVP target |
| --- | --- |
| Dashboard pages | Render primary content within 2 seconds on normal broadband. |
| Upload acknowledgement | Create upload record within 3 seconds after file transfer completes. |
| File processing | Process typical seller research files asynchronously with status updates. |
| Campaign generation | Complete within worker job and expose progress/status. |
| Keyword tables | Support filtering and pagination for large uploaded files. |
| Export generation | Validate and store export asynchronously for larger plans. |

## Reliability Requirements
Jobs are retry-safe, APIs are idempotent where practical, and failed processing leaves recoverable status plus user-safe errors.

