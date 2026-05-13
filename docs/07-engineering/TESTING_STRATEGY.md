# Testing Strategy

## Required Unit Tests
| Business rule | Required tests |
| --- | --- |
| Relevance score | Counts ranks under 15; excludes rank 15; handles missing ranks. |
| Rejection | Scores 0, 1, and 2 reject; scores 3-10 eligible. |
| Hero keyword | Highest relevance wins; search volume tie-breaks. |
| Grouping | Remaining keywords batch into 5 to 7. |
| Campaign generation | Exact, Phrase, Broad created for each group. |
| Negatives | Phrase gets Negative Exact; Broad gets Negative Phrase. |
| Defaults | Budget $10 and bid $1.00 when not overridden. |
| Bid recommendation | Low spend plus low traffic recommends 10% increase. |
| Lock recommendation | Day 7 ACOS under 50% recommends lock. |
| Approval safety | No customer-impacting state change without approval. |

## Integration Tests
Upload parsing, column mapping, scoring, keyword approval, campaign plan generation, bulk export validation, monitoring ingestion, recommendation creation, and approval queue decisions.

## E2E Tests
Customer journey from product profile through upload, keyword approval, campaign review, bulk export approval, monitoring, recommendation approval, and audit log verification.

