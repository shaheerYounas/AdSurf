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

## Constraints
- Never add negative keywords from rejected terms automatically.
- Never publish negative keywords live in MVP.
- Every negative keyword row in a bulk sheet must trace to a campaign plan rule.

## Acceptance Criteria
- Phrase campaign exports contain matching Negative Exact rows.
- Broad campaign exports contain matching Negative Phrase rows.
- Negative rows are visible during campaign plan review.
- Customer approval is required before export use.

