# Keyword Relevance Rules

## Definition
Relevance Score equals `count(top_10_competitors where organic_rank < 15)`.

## Required Input Shape
| Field | Required | Notes |
| --- | --- | --- |
| search_term | Yes | Normalized lowercase search term used for dedupe. |
| competitor_rank_1..10 | Yes for scoring | Organic rank values for top 10 competitors. |
| search_volume | Preferred | Used for tie-breaking and prioritization. |
| suggested_bid | Optional | Used for campaign bid defaulting. |

## Score Outcome
| Score | Status | Reason |
| --- | --- | --- |
| 0 | Rejected | No top competitors rank organically under 15. |
| 1 | Rejected | Weak competitor presence. |
| 2 | Rejected | Below launch relevance threshold. |
| 3-10 | Approved candidate | Eligible for customer review and campaign planning. |

## Tests Required
- Score counts only organic ranks under 15.
- Rank 15 does not count.
- Missing competitor rank values are treated as not counted and flagged.
- Scores 0, 1, and 2 are rejected.
- Scores 3 through 10 are eligible for approval.

