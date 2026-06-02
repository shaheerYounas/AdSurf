# MVP Scope

## In MVP
| Capability | Included behavior |
| --- | --- |
| Product profiles | ASIN, marketplace, currency, product name, default budget, default bid, notes. |
| File upload | CSV/XLSX competitor keyword research upload to private storage. |
| Cleaning | Normalize text, remove blank rows, dedupe terms, flag missing required values. |
| Column mapping | System-suggested mappings with user review when confidence is low. |
| Relevance scoring | Deterministic competitor-rank scoring and rejection. |
| Keyword approval | Customer reviews approved and rejected search terms. |
| Campaign plan | Hero campaign plus grouped Exact, Phrase, Broad campaigns. |
| Negatives | Negative Exact and Negative Phrase structure generated from rules. |
| Bulk export | Amazon bulk sheet export after customer approval. |
| Monitoring | Manual report upload, stored snapshots, or deterministic 14-day simulation for approval-gated analysis. |
| Recommendations | Bid increase, pause, negative keyword, and lock recommendations. |
| Audit logs | All decisions, approvals, exports, and AI runs are logged. |

## MVP Ad Scope
| Area | Decision |
| --- | --- |
| Ad product | Sponsored Products only. |
| Execution mode | Campaign planning and Amazon bulk-sheet export only. |
| Targeting mode | Manual targeting for generated plans. |
| Later scope | Sponsored Brands, Sponsored Display, and direct Amazon Ads API execution. |

## Marketplace And Currency
| Setting | MVP decision |
| --- | --- |
| Default marketplace | Amazon US. |
| Default currency | USD. |
| Product profile fields | Store marketplace and currency on every product profile. |
| Later scope | Multi-marketplace defaults, currency conversion, and marketplace-specific bulk sheet variations. |

## Competitor Verification
- Competitor presence verification uses manual Amazon top-result evidence in MVP.
- Evidence is accepted per search term as positions 1-15 with explicit matched competitor name or ASIN.
- A keyword is verified when at least 3 distinct original competitors are present in the top 15 evidence rows.
- Campaign generation from the competitor-direct workflow requires both `scoring_status=approved` and `verification_status=verified`.
- Verification does not execute live Amazon Ads changes and remains auditable evidence for approval-controlled campaign export.

## Customer Override Policy
| Override | MVP policy |
| --- | --- |
| Keyword approval/rejection | Allowed with required reason and audit log. |
| Bids and budgets | Allowed with required reason and audit log. |
| Hero keyword | Later scope unless explicitly implemented as manual admin override with reason and audit log. |
| Grouping | Later scope. |
| Negative keyword structure | Later scope except generated rule output may be rejected before export approval. |

## Campaign Generation Edge Cases
| Approved keyword count | Behavior |
| --- | --- |
| 0 | Block campaign generation and show recovery guidance: review rejected terms, upload better research, or adjust mappings. |
| 1 | Generate Hero-only plan. |
| 2-7 | Generate Hero plus one group from remaining terms. |
| 8+ | Generate Hero plus grouped campaigns of 5-7 remaining terms. |

## Later
| Capability | Reason deferred |
| --- | --- |
| Amazon Ads API execution | Requires stricter credential storage, approval enforcement, and rollback design. |
| Fully autonomous optimization | Conflicts with MVP trust and approval principle. |
| Sponsored Brands and Sponsored Display | MVP validates Sponsored Products workflow first. |
| Multi-marketplace support | Requires marketplace-specific exports, currencies, defaults, and validation. |
| Cross-channel ads | MVP focuses only on Amazon Ads Sponsored Products style workflows. |
| Advanced forecasting | Requires historical account data beyond first version. |
| Billing and subscription | Can be added after workflow value is validated. |

## MVP Exit Criteria
- A customer can move from upload to approved bulk sheet without developer help.
- Deterministic tests cover all documented business rules.
- Approval queue prevents every customer-impacting action from executing silently.
