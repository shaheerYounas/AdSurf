# Column Mapping Agent

## Responsibility
Suggest mappings from uploaded file headers to canonical columns such as search_term, search_volume, suggested_bid, and competitor_rank_1 through competitor_rank_10.

## Decision Rules
| Confidence | Behavior |
| --- | --- |
| High | Preselect mapping for user review. |
| Medium | Show recommendation and reason. |
| Low | Require manual selection before scoring. |

## Prohibited
- Do not score keywords before required mappings are confirmed.
- Do not treat AI confidence as user approval.

## Acceptance Criteria
Every mapping has source header, canonical column, confidence, reason, and review status.

