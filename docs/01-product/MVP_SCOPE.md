# MVP Scope

## In MVP
| Capability | Included behavior |
| --- | --- |
| Product profiles | ASIN, marketplace, product name, default budget, default bid, notes. |
| File upload | CSV/XLSX competitor keyword research upload to private storage. |
| Cleaning | Normalize text, remove blank rows, dedupe terms, flag missing required values. |
| Column mapping | System-suggested mappings with user review when confidence is low. |
| Relevance scoring | Deterministic competitor-rank scoring and rejection. |
| Keyword approval | Customer reviews approved and rejected search terms. |
| Campaign plan | Hero campaign plus grouped Exact, Phrase, Broad campaigns. |
| Negatives | Negative Exact and Negative Phrase structure generated from rules. |
| Bulk export | Amazon bulk sheet export after customer approval. |
| Monitoring | Manual report upload or stored snapshots for 14-day analysis. |
| Recommendations | Bid increase, pause, negative keyword, and lock recommendations. |
| Audit logs | All decisions, approvals, exports, and AI runs are logged. |

## Later
| Capability | Reason deferred |
| --- | --- |
| Amazon Ads API execution | Requires stricter credential storage, approval enforcement, and rollback design. |
| Fully autonomous optimization | Conflicts with MVP trust and approval principle. |
| Cross-channel ads | MVP focuses only on Amazon Ads Sponsored Products style workflows. |
| Advanced forecasting | Requires historical account data beyond first version. |
| Billing and subscription | Can be added after workflow value is validated. |

## MVP Exit Criteria
- A customer can move from upload to approved bulk sheet without developer help.
- Deterministic tests cover all documented business rules.
- Approval queue prevents every customer-impacting action from executing silently.

