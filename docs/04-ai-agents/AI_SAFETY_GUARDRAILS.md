# AI Safety Guardrails

## Batch 4 Spreadsheet Boundary
Uploaded spreadsheet and CSV content is untrusted data. Parser output stores cell text as JSON only; it does not execute formulas, follow spreadsheet instructions, or pass content to AI agents in Batch 4.

## Guardrails
| Guardrail | Requirement |
| --- | --- |
| Structured outputs | AI outputs must match schemas for mappings, explanations, or summaries. |
| Dual-path decisions | Every decision service supports BOTH deterministic rules AND AI reasoning, following the `DualPathDecisionService[T]` base class. Deterministic path is always available as fallback. |
| Deterministic decisions | Scores, statuses, recommendations, budgets, and bids ALWAYS have a deterministic path that produces results without AI. |
| Human approval | AI cannot approve, execute, or publish customer-impacting changes. Required regardless of decision path. |
| Minimum data | Send only necessary workspace data to providers. |
| Logging | Log provider, model, schema version, input hash, output, status, and decision_source for every AI call. |
| Redaction | Never send secrets, tokens, or unrelated customer data. |
| Safety prompt | Every AI path includes `safety_prompt_snippet()`: "SAFETY BOUNDARY: You are an assistant to a human operator..." |
| Fallback on failure | Hybrid mode automatically falls back to deterministic rules on AI failure. Pure AI mode returns empty results (safety-first). |

## Refusal Conditions
AI workflows must refuse or defer when data is insufficient, mappings are unconfirmed, workspace scope is unclear, or requested action would bypass approval.

## Phase 1 Monitoring Boundary
Sponsored Products Search Term report monitoring uses deterministic rules for final recommendation type, priority, proposed action, and evidence JSON. AI-style summaries may explain rule output only. They may not create final decisions, change recommendation status, call Amazon Ads APIs, generate exports, or mutate live accounts.

## Acceptance Criteria
Safety tests prove that AI output cannot directly transition recommendations, exports, or campaigns into executed states.
