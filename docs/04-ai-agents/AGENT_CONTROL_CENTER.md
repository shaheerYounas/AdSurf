# Agent Control Center

## Purpose
The Agent Control Center gives workspace users visibility and control over AdSurf's multi-agent recommendation workflow. The primary entry point is now account-level report upload before agent analysis. Users can inspect agent responsibilities, inputs, outputs, event timelines, workflow edges, related recommendations, and safety boundaries.

The page is designed for sellers and agency operators, not as a developer-only node builder. It combines an Agent Team Dashboard, a non-drag Visual Workflow Canvas, a Trace Timeline, Human Approval Checkpoints, and a right-side Agent Inspector.

## Safety Boundary
Agents may analyze uploaded Amazon Ads report data and create recommendation outputs. Agents must not execute live Amazon Ads changes, approve or reject recommendations, bypass human approval, disable audit logging, hide evidence, or delete source uploads.

Approval only updates app state and audit logs or prepares manual/export instructions. No Agent Control Center action calls Amazon Ads mutation APIs.

## Agents
| Agent | Responsibility |
| --- | --- |
| Report Upload Node | Receives account reports or bulk sheets and starts the workflow. |
| Report Detection Agent | Detects report type, confidence, required columns, entity levels, and readiness. |
| Product Resolution Agent | Maps ASINs, SKUs, product names, and unknown product groups to profiles or suggestions. |
| Metrics Analysis Agent | Summarizes spend, sales, clicks, orders, ACOS, ROAS, CTR, CVR, winners, wasters, and risks. |
| AI Recommendation Brain | Uses DeepSeek or configured fallback mode to create recommendation decisions from normalized evidence. |
| Bid Optimization Agent | Reviews bid-related recommendations and explains bid action risk. |
| Negative Keyword Agent | Reviews wasted search terms and explains negative exact or phrase evidence. |
| Budget Allocation Agent | Reviews campaign and product budget pressure, budget risk, and reallocation opportunities. |
| Pause Review Agent | Reviews entities that may need pause review and explains risk. |
| Stakeholder Reporting Agent | Creates dashboard summary, executive summary, next actions, and approver notes. |
| Human Approval Agent | Routes recommendations to users and prevents automatic approval or rejection. |

## UI Model
The `/agents` page uses Simple Mode by default and Advanced Mode for operators who need deeper traceability.

| Surface | What it shows |
| --- | --- |
| Top bar | Upload/run controls, pause/resume/stop/rerun controls, approvals shortcut, and deterministic/AI/hybrid selector. |
| Main sidebar | The global AdSurf sidebar switches to an Agent Ops sub-menu when users open Agents. The sub-menu contains Workspace, Reports, Agents, Workflows, Recommendations, Approvals, and Settings, plus a small Main menu control to return to the global navigation. |
| Upload / Start Analysis | A normal first-step card with report file picker, upload button, Simple/Advanced Mode toggle, import summary, and safety labels. |
| Main workflow stack | Upload / Start Analysis, Visual Workflow Canvas, Agent Team Dashboard, Human Approval Checkpoints, and Trace Timeline. |
| Agent Team Dashboard | Business-friendly cards with status, task, provider/model, mode, strictness, confidence threshold, data access, context limits, permissions, recommendation count, last run, and errors. |
| Visual Workflow Canvas | Horizontal pipeline with colored nodes, data-passing edge labels, active/failed/approval states, and node selection. |
| Right Agent Inspector | Sticky on wide desktop layouts and full-width below the main workflow on narrower screens. Tabs wrap across lines instead of forcing a horizontal scrollbar. |
| Trace Timeline | Expandable execution events with provider/model, latency, cost metadata when available, validation errors, retries, and fallback details. |
| Human Approval Checkpoints | Pending recommendation cards grouped around evidence, risk, confidence, and approve/reject actions. |
| Agent Templates | MVP presets for Conservative Profitability, Growth Scaling, Wasted Spend Cleanup, Launch Campaign Review, and Agency Account Audit. |

Simple Mode keeps the upload, workflow canvas, agent status, recommendations, trace timeline, and safety labels visible while hiding raw JSON complexity. Advanced Mode shows inspector details, prompt/configuration, raw input/output summaries, trace logs, risk controls, model/provider settings, and template presets.

## Workflow Graph
The default account workflow is:

`Report Upload -> Report Detection Agent -> Product Resolution Agent -> Metrics Analysis Agent -> AI Recommendation Brain -> Bid Optimization / Negative Keyword / Budget Allocation / Pause Review -> Stakeholder Reporting -> Human Approval Queue`

The legacy single-product monitoring graph remains supported:

`Performance Import -> Metrics Analysis -> AI Recommendation Brain -> Bid Optimization / Negative Keyword / Pause Review -> Stakeholder Reporting -> Approval Queue`

Edges show status, timestamps when available, and summaries of data passed, such as normalized metrics, rollups, recommendation candidates, risk notes, and approval notes.

## Controls
| Control | Behavior |
| --- | --- |
| Run analysis | For account imports, calls `POST /v1/workspaces/{workspace_id}/account-imports/{account_import_id}/run-analysis`, creates deterministic account-level agent runs, creates approval-only recommendations, and refreshes the workflow graph. |
| Enable/disable | Changes future workflow behavior for a workspace or product. |
| Pause/resume | Records user intent and pauses/resumes displayed run state. |
| Stop | Records user intent and prevents stopped agents from creating new outputs when checked before execution. |
| Rerun | Creates a new run record. Old runs are not overwritten. |
| Rerun from here | Queues a workflow control action from a selected agent onward. |
| Configure | Updates mode, strictness, confidence threshold, max recommendations, and recommendation-type toggles. |

The UI always labels recommendation-producing surfaces with: `Recommendation only`, `Requires human approval`, and `No live Amazon Ads change executed`.

## Configuration
Agent configs can be workspace-level, product-level, and later account-import-level:

- `enabled`
- `mode`: deterministic, ai, hybrid
- `provider`: primary, deepseek, fallback, deterministic
- `model`
- `strictness_level`: conservative, balanced, aggressive
- `confidence_threshold`: low, medium, high
- `max_recommendations`
- `max_rows_per_ai_call`, `max_groups_per_ai_call`, `max_products_per_run`, `max_keywords_per_ai_call`
- `analysis_depth`: quick, standard, deep
- account, product, campaign, keyword, and search-term scope toggles
- recommendation type toggles for keep-running, bid, pause review, negatives, move-to-exact, budget review, data quality, and product mapping
- risk controls for bid multipliers, pause/negative confidence, minimum clicks/spend, target ACOS, orders, and ROAS

### Prompt Customization (Full Control Over AI Behavior)
| Setting | Description |
|---------|-------------|
| `custom_system_instruction` | Additional instructions appended to system prompt (max 4000 chars) |
| `custom_business_goal` | Business context for the agent (max 2000 chars) |
| `custom_role_description` | Override the agent's default role description |
| `custom_output_format` | Custom expected output JSON format override |
| `custom_examples_json` | Few-shot examples as JSON string (max 10000 chars) |
| `additional_safety_notes` | Extra safety instructions appended to prompt |
| `brand_safety_notes` | Brand-specific safety requirements |
| `competitor_notes` | Competitor-specific context |
| `product_margin_notes` | Product margin/cost information |

### AI Model Parameters
| Setting | Range | Description |
|---------|-------|-------------|
| `temperature` | 0.0 - 2.0 | Controls randomness (lower = more deterministic) |
| `max_tokens` | 1 - 32000 | Maximum output tokens |
| `top_p` | 0.0 - 1.0 | Nucleus sampling parameter |
| `frequency_penalty` | -2.0 - 2.0 | Penalize token frequency |
| `presence_penalty` | -2.0 - 2.0 | Penalize token presence |

### Deterministic Rule Customization
| Setting | Range | Description |
|---------|-------|-------------|
| `deterministic_relevance_threshold` | 0 - 10 | Minimum relevance score for keyword approval |
| `deterministic_max_rank_value` | 1 - 100 | Max rank value that counts toward relevance |
| `deterministic_keyword_batch_size` | 1 - 50 | Keywords per ad group in campaign generation |
| `deterministic_default_bid` | $0.01 - $1000 | Default bid for new keywords |
| `deterministic_default_budget` | $0.01 - $100,000 | Default daily budget for campaigns |

### Data Limits
| Setting | Range | Description |
|---------|-------|-------------|
| `max_rows_per_ai_call` | 1 - 50000 | Max rows sent to AI per call |
| `max_groups_per_ai_call` | 1 - 5000 | Max groups sent to AI per call |
| `max_keywords_per_ai_call` | 1 - 10000 | Max keywords sent to AI per call |
| `include_deterministic_baseline` | true/false | Whether AI sees deterministic results for comparison |
| `explanation_detail` | simple / normal / expert | Level of detail in AI explanations |
| `show_raw_ai_reasoning_summary` | true/false | Show raw AI reasoning in UI |
| `show_metric_evidence` | true/false | Show metric evidence in explanations |
| `require_action_risk_note` | true/false | Require risk notes on all actions |
| `recommendation_language` | language code | Output language (default: "en") |
| `chunk_strategy` | by_product / by_campaign / by_entity_priority | How to chunk data for AI calls |

### Dual-Path Default System Prompts
Every agent has a default system prompt that can be customized. The prompt template system supports `{custom_instruction}`, `{business_goal}`, and `{safety_notes}` variable substitution. Users override these through the configuration settings above.

Owner/admin roles can configure agents. Analysts can run/rerun/control agents. Approvers and viewers can inspect outputs according to workspace read access.
<task_progress>
- [x] Create prompt_template.py system for customizable AI prompts
- [x] Update dual_path_decision.py base class for config-driven prompts and deterministic rules
- [x] Update AgentConfig schema with deterministic rule customization fields
- [x] Update each dual-path service to use custom prompts and deterministic thresholds
- [x] Update web UI API types for prompt and rule customization
- [x] Update docs for prompt and rule customization
- [ ] Verify implementation completeness
</task_progress>

No API keys or arbitrary provider secrets are exposed through agent configuration.

## Audit And Events
Every control action writes an audit log and an agent event. Events include queued, started, input prepared, model called, output received, output validated, recommendations created, paused, resumed, stopped, failed, succeeded, and skipped.

Events store agent ID, run ID when available, monitoring import ID when available, message, event type, metadata JSON, and timestamp.

## Recommendation Traceability
Agent runs store Agent Control Center metadata in run output, including agent ID, monitoring import ID, mode, strictness, confidence threshold, safety boundary, and related recommendation IDs. Recommendation evidence also stores the AI run ID/provider/model when applicable.

The Agent Control Center reads recent agent runs through `GET /agent-runs?limit=250` by default and treats slow run history or recommendation history as non-blocking so configuration controls remain usable even when historical storage is large.

Inspector configuration saves update the visible agent config from the `PATCH /agent-configs/{agent_id}` response instead of reloading the full control center after every field change.
