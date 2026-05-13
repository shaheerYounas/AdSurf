# Amazon Ads Domain Model

## Core Entities
| Entity | Description | Key relationships |
| --- | --- | --- |
| Tenant | Seller or agency workspace | Has users, product profiles, files, plans. |
| Product profile | Advertised product context | Owns uploads, keywords, campaign plans. |
| Research upload | Original competitor keyword file | Produces parsed rows and keyword candidates. |
| Keyword candidate | Search term extracted from upload | Has score, status, and approval outcome. |
| Approved keyword | Candidate approved for campaign planning | Used in Hero or grouped campaigns. |
| Campaign plan | Draft plan before export | Contains campaign groups and negatives. |
| Bulk export | Amazon bulk sheet output | Requires approval and validation. |
| Monitoring snapshot | Performance metrics by campaign/day | Feeds recommendations. |
| Recommendation | Rule-generated optimization proposal | Requires approval before action. |
| Audit log | Immutable decision/event record | Links actor, tenant, object, inputs, outputs. |

## Domain Boundaries
Rules calculate relevance, rejection, grouping, negatives, defaults, and optimization triggers. AI may assist with cleaning, mapping, explanation, and summaries but must not be source of truth for calculations.

