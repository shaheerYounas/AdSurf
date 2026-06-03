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

## Background Data Warmup
The web app warms common workspace data in the background after the first render. Prefetching must stay polite: sections are queued by route priority, fetchers run one at a time, and the service waits for browser idle time plus short cooldowns between requests. Do not introduce route warmups that fetch every product/import detail in parallel.

Primary warm sections are dashboard summary, product list, report library headers, agent metadata/runs, and recommendations. Page components should read from the shared prefetch cache before issuing their own request, then refresh only missing or expired data.
