# Campaign Creation Rules

## Inputs
| Input | Source |
| --- | --- |
| Approved keywords | `approved_keyword_sets` locked snapshot created after keyword review. |
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
| Campaign naming | Use `{ProductName} / SP / Manual / {MatchType} / {KeywordOrRelevantGroup} / {Mon DD}`. |
| Competitor-direct generation | Use only rows with `scoring_status=approved` and `verification_status=verified`. |
| Safety summary | Every generated plan includes total daily budget exposure, risk labels, human approval boundary, and a required existing-campaign duplicate check before export. |

## Acceptance Criteria
- Hero keyword is unique.
- No rejected keyword appears in any campaign.
- Every non-Hero approved keyword belongs to exactly one group.
- Each group creates Exact, Phrase, and Broad campaign structures.
- Phrase campaigns include Negative Exact rows for group keywords.
- Broad campaigns include Negative Phrase rows for group keywords.
- Campaign plan review shows aggregate daily budget exposure before export.
- ASIN-like approved terms, duplicate approved terms, low-data terms, and high budget exposure are flagged in `safety_summary`.

## Implementation Boundary
Campaign generation consumes locked `approved_keyword_sets` and their snapshot items, not live scoring candidates. Generated plans remain internal until a user explicitly approves the campaign plan. Bulk sheet export is a separate approval step and no Amazon Ads API execution occurs in MVP.
