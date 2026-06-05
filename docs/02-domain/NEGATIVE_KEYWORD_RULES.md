# Negative Keyword Rules

## Purpose
Negative keyword structure prevents match-type overlap and waste while preserving campaign control.

## MVP Rules
| Campaign type | Negative structure |
| --- | --- |
| Hero | No automatic negatives unless duplicate prevention requires it. |
| Exact | No match-type negatives required in MVP. |
| Phrase | Add Exact keywords as Negative Exact. |
| Broad | Add Phrase keywords as Negative Phrase. |

## Monitoring Recommendation Rules
Sponsored Products Search Term report monitoring can recommend negative keyword actions, but only as approval-controlled output:

| Recommendation | Condition | Boundary |
| --- | --- | --- |
| add_negative_exact | Search term has no orders, is not ASIN-like, and has either at least 15 clicks with at least $10 spend or at least $20 spend. | Creates a pending recommendation only. |
| add_negative_phrase | Broad/phrase/auto source has at least 15 clicks, no orders, and spend at or above `max(default_budget, 10)`. | Creates a pending recommendation only. |
| watch_lock | Search term has no orders and at least 10 clicks, but does not meet negative exact or phrase thresholds. | Creates a non-action watch insight only. |

## Constraints
- Never add negative keywords from rejected terms automatically.
- Never publish negative keywords live in MVP.
- Every negative keyword row in a bulk sheet must trace to a campaign plan rule.
- Monitoring recommendations do not create Amazon negatives or mutate live campaigns.

## Acceptance Criteria
- Phrase campaign exports contain matching Negative Exact rows.
- Broad campaign exports contain matching Negative Phrase rows.
- Negative rows are visible during campaign plan review.
- Customer approval is required before export use.
