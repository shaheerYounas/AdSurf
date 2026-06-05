# Optimization Rules

## Monitoring Window
The MVP monitors imported Sponsored Products Search Term reports. Recommendations are generated from deterministic metrics and presented in the approval queue with rule explanations and evidence JSON.

MVP optimization is recommendation-only. No automatic Amazon-side changes are made in MVP.

## Rules
| Rule | Condition | Recommendation |
| --- | --- | --- |
| inconsistent_metrics_data_quality_review | Critical only for corrupt rows such as clicks exceeding impressions or orders exceeding clicks. Medium review for warning-level issues such as orders with zero sales, spend without clicks, blank ACOS when sales exist, or ACOS/ROAS mismatches beyond tolerance. | Recommend data quality review. |
| high_spend_no_orders_pause_review | `spend >= max(default_budget * 2, 20)`, `clicks >= 15`, and `orders = 0` | Recommend pause review, never automatic pause. |
| broad_waste_no_orders_add_negative_phrase | Broad/phrase/auto source, `clicks >= 15`, `spend >= max(default_budget, 10)`, and `orders = 0` | Recommend negative phrase review. |
| search_term_waste_no_orders_add_negative_exact | `orders = 0`, search term is not ASIN-like, and either `clicks >= 15 and spend >= 10` or `spend >= 20` | Recommend negative exact review. |
| weak_zero_order_signal_watch_lock | `orders = 0` and `clicks >= 10`, but negative thresholds are not met | Recommend watch lock, not a negative action. |
| acos_above_target_decrease_bid | `orders > 0`, `sales > 0`, `ACOS > target_acos * 1.25`, and either `clicks >= 8` or `spend >= 10` | Recommend bounded bid decrease review. |
| efficient_non_exact_search_term_move_to_exact | Non-exact source, `orders >= 2`, `ACOS <= target_acos`, and search term is not ASIN-like | Recommend move-to-exact review. |
| strong_performance_budget_pressure_review | Spend approaches the product default budget and ROAS is strong | Recommend budget review. |
| efficient_acos_watch_lock | `sales > 0` and `ACOS <= target_acos * 0.80` | Recommend internal watch/lock status. |
| under_tested_watch_lock | Clicks or impressions are too low for a confident action | Recommend watch lock. |
| strong_conversion_low_impressions_increase_bid | `orders >= 2`, `ACOS <= target_acos * 0.90`, CVR is at least 8%, spend is at least $3, impressions are below 100, and relevance is not low | Recommend bounded bid increase review. |
| within_thresholds_keep_running | No higher-priority rule triggers | Recommend keep running. |

## MVP Thresholds To Configure
| Setting | Default |
| --- | --- |
| Max bid increase | 30% |
| Max bid decrease | 40% |
| Minimum bid | $0.10 |
| Target ACOS | 50% unless product or workspace default is configured later. |
| Low spend | `spend <= 5` at targeting/search-term row level. |
| Low traffic | `clicks < 3` with at least 10 impressions. |
| High spend | `max(default_budget * 2, 20)`. |
| Negative exact | No orders and either at least 15 clicks with at least $10 spend, or at least $20 spend. |
| Negative phrase | `clicks >= 15`, no orders, broad/phrase/auto source, and spend above threshold. |
| Move to exact | `orders >= 2`, non-exact source, and ACOS at or below target. |
| Budget pressure | Spend at least 80% of default budget and ROAS is strong. |

All optimization thresholds must be configurable later at workspace or product level.

## ACOS Handling
| Condition | Display and calculation |
| --- | --- |
| `sales > 0` | Calculate ACOS as `spend / sales`. |
| `spend > 0` and `sales = 0` | ACOS is undefined/infinite and must display as `No sales`. Do not calculate numeric ACOS and do not flag blank source ACOS as data corruption. |
| `spend = 0` and `sales = 0` | ACOS is not applicable and should display as `No spend`. |

## Recommendation Classes
Action recommendations are `increase_bid`, `decrease_bid`, `add_negative_exact`, `add_negative_phrase`, `move_to_exact`, and `pause_review`. They require approval and may become export candidates only where the export workflow allows them.

Non-action insights are `keep_running` and `watch_lock`. `data_quality_review` and `budget_review` are review notes, not exportable ad mutations.

## Lock Campaign Semantics
In MVP, lock is an internal recommendation/status label only. It means the system recommends watching the campaign without aggressive optimization for days 8-14. It does not send any change to Amazon, change campaign state, or prevent a human from approving other recommendations.

## Evidence JSON
Each recommendation stores deterministic `evidence_json` with:

- Rule version, rule name, recommendation type, and priority.
- Product thresholds used for the decision.
- Normalized snapshot metrics.
- Search-term, target, ad-group, campaign, and report-level performance rollups.
- CTR, CPC, CVR, ACOS, ROAS, CPA, spend per order, sales per click, click/spend/sales share, zero-order spend, and wasted spend.
- Signals for high-click zero-order, high-spend low-sales, low-impression high-conversion, strong/weak converter, under-tested, over-tested, budget pressure, search-term relevance, match-type risk, and duplicate/overlap.
- Approval boundary flags showing no live Amazon Ads mutation occurs.

## Acceptance Criteria
- Recommendations include rule name, input metrics, evidence JSON, proposed action, and explanation.
- No recommendation changes ads without explicit approval.
- Bid increase recommendations are blocked when the safety rule is triggered.
- ACOS is never represented as a numeric value when sales are zero.
