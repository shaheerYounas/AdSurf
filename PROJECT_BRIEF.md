# Project Brief

## Product
Amazon Ads AI Automation Control Center is a SaaS dashboard for Amazon sellers and agencies that turns competitor keyword research into approved campaign plans, Amazon bulk sheet exports, and monitored optimization recommendations.

## Problem
Amazon Ads campaign creation and optimization is repetitive, spreadsheet-heavy, and risky. Sellers often launch broad, unstructured campaigns without clear relevance scoring, negative keyword protection, or disciplined monitoring. Agencies need repeatable workflows that preserve customer approval and auditability.

## Target Customers
| Customer | Primary need |
| --- | --- |
| Solo Amazon seller | Turn research files into safe campaigns without becoming an ads expert. |
| Amazon agency operator | Process many products consistently with client approval. |
| Account strategist | Explain why keywords and optimizations are recommended. |
| Admin/owner | Control roles, exports, audit logs, and tenant settings. |

## MVP Promise
Upload competitor keyword research, let the system clean and score it, approve the keyword list, generate campaign structure and bulk sheet export, then monitor and approve optimization recommendations.

## Business Rules Snapshot
| Rule | MVP decision |
| --- | --- |
| Relevance Score | Count top 10 competitors with organic rank under 15. |
| Rejection | Scores 0, 1, and 2 are rejected. |
| Hero keyword | Highest relevance score, search volume as tie-breaker. |
| Keyword grouping | Remaining approved keywords grouped into batches of 5 to 7. |
| Campaign types | Exact, Phrase, and Broad campaigns per group. |
| Negatives | Phrase gets Exact as Negative Exact; Broad gets Phrase as Negative Phrase. |
| Defaults | Daily budget $10; bid $1.00 unless user override or suggested bid exists. |
| Optimization | Low spend and low traffic in first 7 days recommends 10% bid increase. |
| Lock | Day 7 ACOS under 50% recommends another 7-day lock. |

## Safety Position
The MVP never makes live Amazon Ads changes. It produces explanations, recommendations, approvals, exports, and logs. Amazon Ads API execution is a later version and must preserve approval controls.

