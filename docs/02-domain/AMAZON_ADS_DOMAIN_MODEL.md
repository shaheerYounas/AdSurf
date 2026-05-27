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
## Account-Level Imports

AdSurf supports account-level imports for bulk Amazon Ads reports and bulk sheets. A single import can contain many advertised products, ASINs, SKUs, campaigns, ad groups, targets, search terms, and metric rows.

### Account Import Entities
Rows are grouped into these deterministic entity levels:

| Level | Key examples |
| --- | --- |
| account | workspace import |
| product | product ID, ASIN, SKU, product name, unknown product |
| campaign | campaign name or ID |
| ad group | campaign + ad group |
| target | campaign + ad group + targeting/keyword |
| search term | campaign + ad group + targeting + customer search term |

### Product Resolution
Product matching uses deterministic ASIN, SKU, and exact normalized product-name matches. Conflicts or missing identifiers create mapping suggestions instead of silently attaching the row to a product.

Resolution statuses are `matched_existing_product`, `suggested_new_product`, `unknown_product`, and `needs_user_mapping`.
