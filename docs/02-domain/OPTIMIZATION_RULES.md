# Optimization Rules

## Monitoring Window
The MVP monitors each campaign for 14 days after launch/import. Recommendations are generated from deterministic metrics and presented in the approval queue.

## Rules
| Timing | Condition | Recommendation |
| --- | --- | --- |
| Days 1-7 | Campaign is not spending enough and traffic is low | Increase bid by 10%. |
| Day 7 | ACOS under 50% | Lock campaign for another 7 days. |
| Any day | Search term spend exists with poor relevance | Recommend negative keyword review. |
| Any day | High spend with no sales | Recommend pause review, never automatic pause. |

## MVP Thresholds To Configure
| Setting | Default |
| --- | --- |
| Bid increase | 10% |
| Lock ACOS threshold | Under 50% |
| Low spend | Configured per tenant or product in later implementation. |
| Low traffic | Configured per tenant or product in later implementation. |

## Acceptance Criteria
- Recommendations include rule name, input metrics, proposed action, and explanation.
- No recommendation changes ads without explicit approval.

