# Campaign Creation Rules

## Inputs
| Input | Source |
| --- | --- |
| Approved keywords | Customer-approved keyword list after scoring. |
| Search volume | Mapped research column when available. |
| Suggested bid | Mapped research column when available. |
| Product defaults | Product profile budget and bid settings. |

## Rules
| Rule | Decision |
| --- | --- |
| Hero campaign | Select keyword with highest relevance score; break ties by highest search volume. |
| Remaining keywords | Exclude Hero keyword, then sort by relevance score desc and search volume desc. |
| Group size | Create batches of 5 to 7 remaining approved keywords. |
| Campaign types | Create Exact, Phrase, and Broad campaigns for each group. |
| Daily budget | Use product default or $10 if unset. |
| Bid | Use suggested bid, then product default, then $1.00. |

## Acceptance Criteria
- Hero keyword is unique.
- No rejected keyword appears in any campaign.
- Every non-Hero approved keyword belongs to exactly one group.
- Each group creates Exact, Phrase, and Broad campaign structures.

