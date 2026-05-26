# Bulk Sheet Specification

## MVP Export Purpose
Generate an Amazon Ads bulk sheet from an approved campaign plan. The export is the first execution mode; direct Amazon Ads API execution is later.

## Row Types
| Row type | Source |
| --- | --- |
| Campaign | Hero and generated Exact/Phrase/Broad campaigns. |
| Ad group | One ad group per campaign in MVP. |
| Keyword | Approved keyword with match type. |
| Negative keyword | Rule-generated Negative Exact or Negative Phrase. |

## Required Fields
| Field | Rule |
| --- | --- |
| Campaign name | Deterministic name from product, plan, group, and match type. |
| Campaign daily budget | Product default or $10. |
| Campaign status | Enabled in sheet only after customer approval. |
| Ad group name | Matches campaign grouping. |
| Keyword text | Approved keyword only. |
| Match type | Exact, Phrase, Broad, Negative Exact, or Negative Phrase. |
| Bid | Suggested bid, product default, or $1.00. |

## Validation
- No rejected keyword rows.
- No blank campaign, ad group, keyword, match type, budget, or bid fields.
- Export references approved plan version.
- Export requires approval and audit log entry.

## Implementation Boundary
MVP exports are generated as CSV files from approved campaign plans. Export generation requires a separate non-empty approval note and stores the CSV through the configured storage adapter. The export does not make live Amazon Ads API changes.
