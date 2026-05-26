# AI Safety Guardrails

## Batch 4 Spreadsheet Boundary
Uploaded spreadsheet and CSV content is untrusted data. Parser output stores cell text as JSON only; it does not execute formulas, follow spreadsheet instructions, or pass content to AI agents in Batch 4.

## Guardrails
| Guardrail | Requirement |
| --- | --- |
| Structured outputs | AI outputs must match schemas for mappings, explanations, or summaries. |
| Deterministic decisions | Scores, statuses, recommendations, budgets, and bids come from rules. |
| Human approval | AI cannot approve, execute, or publish customer-impacting changes. |
| Minimum data | Send only necessary workspace data to providers. |
| Logging | Log provider, model, schema version, input hash, output, and status. |
| Redaction | Never send secrets, tokens, or unrelated customer data. |

## Refusal Conditions
AI workflows must refuse or defer when data is insufficient, mappings are unconfirmed, workspace scope is unclear, or requested action would bypass approval.

## Acceptance Criteria
Safety tests prove that AI output cannot directly transition recommendations, exports, or campaigns into executed states.
