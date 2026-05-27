# Account Bulk Report Workflow

## Purpose
Account bulk import is now the primary monitoring entry point. Users can upload one Amazon Ads report or bulk sheet that contains many products, ASINs, SKUs, campaigns, ad groups, targets, search terms, and performance metrics.

## Workflow
1. User uploads an Amazon Ads report from the Agent Control Center.
2. Backend parses the file through the existing upload parser.
3. Report Type Detector classifies the file from headers and sample rows.
4. Product Entity Resolver detects ASINs, SKUs, product names, campaigns, ad groups, targets, and search terms.
5. Existing product profiles are linked when ASIN/SKU/name matches are deterministic.
6. Unknown or unmatched products create pending mapping suggestions.
7. Account import entities are stored at account, product, campaign, ad group, target, and search-term levels.
8. User reviews mapping suggestions before deeper analysis.
9. Agents receive grouped metrics and safe config fields.
10. Recommendations remain pending until a human approves or rejects them.

## Safety Boundary
Account imports do not execute live Amazon Ads changes. Approval only updates AdSurf recommendation state and audit history. Bulk sheet export remains the MVP execution handoff; Amazon Ads API mutation is later-version work.

## Supported Report Modes
- `single_product_report`
- `account_bulk_report`
- `sponsored_products_search_term_report`
- `sponsored_products_targeting_report`
- `sponsored_products_campaign_report`
- `bulk_sheet`
- `unknown_report`

## Mapping Statuses
- `matched_existing_product`
- `suggested_new_product`
- `unknown_product`
- `needs_user_mapping`

## Acceptance Notes
Phase 1 stores account imports, grouped entities, detection output, and mapping suggestions. Phase 2+ uses these grouped entities for account-level agent runs and recommendations.
