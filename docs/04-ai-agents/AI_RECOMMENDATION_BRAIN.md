# AI Recommendation Brain

## Role
The AI Recommendation Brain receives deterministic metrics, grouped evidence, safety boundaries, and safe agent configuration. It may decide recommendation type, priority, confidence, evidence, proposed action, and explanation.

## Inputs
The prompt includes:
- `report_context`
- `agent_config`
- `grouped_metrics`
- row-level snapshots for the current analysis scope
- deterministic rollups
- data-quality warnings
- safety boundaries

Frontend never sends provider secrets. Provider, model, strictness, risk controls, output controls, and chunking limits are safe configuration fields only.

## Required Safety Flags
Every AI prompt includes:

```json
{
  "requires_human_approval": true,
  "executes_live_amazon_change": false,
  "amazon_ads_api_mutation_allowed": false
}
```

Every accepted recommendation must also include evidence, require human approval, and state that it does not execute live Amazon Ads changes.

## Validation
Backend validation rejects recommendations that:
- reference an entity not present in uploaded evidence
- use a disallowed recommendation type
- miss required evidence
- set approval-required false
- claim or imply live Amazon Ads mutation
- propose unsafe bid multipliers
- provide negative keyword actions without the required match type

Invalid recommendations are rejected individually where possible; full imports should fail only when no valid recommendation path remains.
