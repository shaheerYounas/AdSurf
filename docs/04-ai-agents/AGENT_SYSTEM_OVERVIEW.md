# AI Agent System Overview (v3 - Optimization Decision Engine)

## Principle

AdSurf is an **Optimization Decision Engine** for Amazon Ads, not just an agent control center. The system follows a strict safety pipeline:

```
Reports uploaded
   ↓
Deterministic metrics engine calculates truth
   ↓
Strategy engine understands account goal
   ↓
AI agents reason over evidence
   ↓
Optimizer proposes safe actions
   ↓
Validator rejects unsafe actions
   ↓
Human approves or rejects
   ↓
Bulk sheet/export is generated
   ↓
Learning loop feeds next cycle
```

## Architecture: Three-Layer Decision System

### Layer 1: Deterministic Metrics (Code)
Code calculates all performance metrics: ACOS, ROAS, CTR, CVR, CPC, spend, orders, impressions, CPA, revenue per click, break-even ACOS, and profit estimates. **AI does not calculate metrics.**

### Layer 2: AI Strategy Reasoning (AI + Rules)
AI decides based on context: product lifecycle, campaign intent, branded vs competitor terms, search intent classification, goal-mode thresholds. Strategy-aware decisions are made by code using AI to interpret patterns.

### Layer 3: Validator (Deterministic Code)
Code checks: Is evidence sufficient? Is bid change within policy? Are there conflicting actions? Is the term converting? Is approval required? Can this be safely exported?

## Agent Groups (14 Professional Agents)

### Data Pipeline
| Agent | Role |
|-------|------|
| Import & Data Quality Agent | Validates report quality, missing columns, date ranges, sample sizes, duplicates |
| Entity Resolution Agent | Maps campaigns, ad groups, ASINs, SKUs, search terms, keywords, match types |
| Metrics Normalization Agent | Calculates all performance metrics deterministically (no AI) |

### Analysis
| Agent | Role |
|-------|------|
| Account Strategy Agent | Sets optimization mode: profit, growth, launch, rank defense, inventory clearance, brand defense, competitor conquesting, wasted spend cleanup |
| Search Term Mining Agent | Classifies terms: harvest to exact/phrase, negative candidates, brand defense, competitor terms, research/intent classification |

### Optimization
| Agent | Role |
|-------|------|
| Bid Optimization Agent | Exact bid recommendations with before/after values, evidence scoring, risk levels |
| Negative Keyword Agent | Wasted spend review with converting-term protection |
| Budget Reallocation Agent | Cross-campaign budget analysis: profit-move, discovery-cap, scaling-gate |
| Campaign Structure Agent | Structure recommendations: exact campaigns for hero terms, brand/non-brand separation |

### Safety
| Agent | Role |
|-------|------|
| Risk & Policy Validator Agent | Rejects unsafe actions: bid limits, negative on converters, insufficient evidence, conflicts, strategy violations |
| Human Approval Agent | Routes to approval queue, prevents automatic mutation, full audit trail |

### Output
| Agent | Role |
|-------|------|
| Bulk Change Compiler Agent | Amazon bulk sheet generation, before/after comparison, rollback reference |
| Learning & Feedback Agent | Compares recommendations to outcomes, builds optimization memory |
| Stakeholder Reporting Agent | Dashboard summaries, executive reports, impact metrics |

## Evidence Scoring System

Confidence depends on: clicks, spend, orders, conversion volume, days of data, and product lifecycle. Higher evidence = higher confidence. Insufficient evidence prevents harmful actions.

## Risk Validation

Before any recommendation reaches the approval queue, it passes through:
1. Evidence sufficiency check (minimum clicks, spend, orders, days)
2. Bid limit validation (bid changes within policy bounds)
3. Strategy compliance (actions match selected optimization mode)
4. Negative keyword safety (no converting terms blocked)
5. Conflict detection (duplicate/contradictory actions)
6. Budget safety (changes within allowed percentages)

## Approval Boundary

Every recommendation includes:
- `approval_required: True`
- `executes_live_amazon_change: False`
- `amazon_ads_api_mutation: False`

No AI final decision, bid change, pause, negative keyword, export, or Amazon Ads mutation is executed without explicit human approval.

## Required AI Run Metadata
agent_name, workspace_id, input_hash, provider, model, schema_version, output_json, status, latency_ms, created_at, evidence_score, risk_level.

## Agent Control Center
The Agent Control Center now shows agents grouped by category (Data Pipeline, Analysis, Optimization, Safety, Output) rather than a flat list. The primary dashboard is outcome-centered, showing optimization impact metrics first.

## Modes
- **Deterministic**: Code-only rules, no AI reasoning
- **Hybrid**: AI reasons over deterministic evidence (recommended)
- **AI**: AI generates recommendations (falls back to deterministic on failure)

Agent config is per-workspace, per-product. Owner/admin users configure; analysts run; approvers approve.