# Amazon Ads Domain Model

## Core Entities
| Entity | Description | Key relationships |
| --- | --- | --- |
| Workspace | Seller or agency workspace | Has users, product profiles, files, plans. |
| Product profile | Advertised product context | Owns uploads, keywords, campaign plans. |
| Research upload | Original competitor keyword file | Produces parsed rows and keyword candidates. |
| Keyword candidate | Search term extracted from upload | Has score, status, and approval outcome. |
| Approved keyword | Candidate approved for campaign planning | Used in Hero or grouped campaigns. |
| Campaign plan | Draft plan before export | Contains campaign groups and negatives. |
| Bulk export | Amazon bulk sheet output | Requires approval and validation. |
| Monitoring import | One processed Sponsored Products Search Term report selected for analysis | Owns snapshots, recommendations, and agent runs. |
| Monitoring snapshot | Performance metrics by campaign/ad group/target/search term/date range | Feeds rollups and recommendations. |
| Recommendation | Rule-generated optimization proposal with entity type, priority, confidence, metrics, evidence JSON, and proposed action | Requires approval before action. |
| Agent run | Structured explanation or dashboard summary derived from rule output | Cannot approve, reject, or mutate live Amazon Ads. |
| Audit log | Immutable decision/event record | Links actor, workspace, object, inputs, outputs. |

## Domain Boundaries
Rules calculate relevance, rejection, grouping, negatives, defaults, and optimization triggers. AI may assist with cleaning, mapping, explanation, and summaries but must not be source of truth for calculations.

## Monitoring Recommendation Entity Types
| Entity type | Meaning |
| --- | --- |
| campaign | Recommendation applies to campaign-level review, such as budget pressure. |
| ad_group | Recommendation applies to an ad group rollup. |
| target | Recommendation applies to the targeting keyword/product target. |
| search_term | Recommendation applies to a customer search term. |

## Monitoring Signals
The deterministic metrics layer calculates CTR, CPC, CVR, ACOS, ROAS, CPA, spend per order, sales per click, click/spend/sales share, zero-order spend, wasted spend, high-click zero-order, high-spend low-sales, low-impression high-conversion, strong/weak converter, under-tested, over-tested, budget pressure, search-term relevance, match-type risk, and duplicate/overlap signals.
