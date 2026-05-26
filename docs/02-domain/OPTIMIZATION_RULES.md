# Optimization Rules

## Monitoring Window
The MVP monitors imported Sponsored Products Search Term reports. Recommendations are generated from deterministic metrics and presented in the approval queue with agent explanations.

MVP optimization is recommendation-only. No automatic Amazon-side changes are made in MVP.

## Rules
| Rule | Condition | Recommendation |
| --- | --- | --- |
| high_spend_no_sales_pause_review | `spend >= max(default_budget * 2, 20)` and `orders = 0` | Recommend pause review, never automatic pause. |
| click_waste_negative_keyword_review | `clicks >= 10` and `orders = 0` | Recommend negative keyword review. |
| acos_above_target_decrease_bid | `sales > 0` and `ACOS > target_acos * 1.25` | Recommend 10% bid decrease review. |
| efficient_acos_watch_lock | `sales > 0` and `ACOS <= target_acos * 0.80` | Recommend internal watch/lock status. |
| low_traffic_low_spend_increase_bid | `impressions >= 10`, `clicks < 3`, and `spend <= 5` | Recommend 10% bid increase review. |

## MVP Thresholds To Configure
| Setting | Default |
| --- | --- |
| Bid increase | 10% |
| Bid decrease | 10% |
| Target ACOS | 50% unless product or workspace default is configured later. |
| Low spend | `spend <= 5` at targeting/search-term row level. |
| Low traffic | `clicks < 3` with at least 10 impressions. |
| High spend | `max(default_budget * 2, 20)`. |

All optimization thresholds must be configurable later at workspace or product level.

## ACOS Handling
| Condition | Display and calculation |
| --- | --- |
| `sales > 0` | Calculate ACOS as `spend / sales`. |
| `spend > 0` and `sales = 0` | ACOS is undefined/infinite and must display as `No sales`. Do not calculate numeric ACOS. |
| `spend = 0` and `sales = 0` | ACOS is not applicable and should display as `No spend`. |

## Lock Campaign Semantics
In MVP, lock is an internal recommendation/status label only. It means the system recommends watching the campaign without aggressive optimization for days 8-14. It does not send any change to Amazon, change campaign state, or prevent a human from approving other recommendations.

## Acceptance Criteria
- Recommendations include rule name, input metrics, proposed action, and explanation.
- No recommendation changes ads without explicit approval.
- Bid increase recommendations are blocked when the safety rule is triggered.
- ACOS is never represented as a numeric value when sales are zero.
