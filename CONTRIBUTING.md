# Contributing

## Development Philosophy
Build the smallest production-quality slice that protects customer trust. Prefer deterministic rules, explicit contracts, good tests, and clear customer language over clever automation.

## Required Before Any Pull Request
| Requirement | Description |
| --- | --- |
| Docs updated | Update relevant product, domain, architecture, workflow, AI, or engineering docs when behavior changes. |
| Tests added | Add or update tests for every changed business rule and approval boundary. |
| Approval safety checked | Verify no customer-impacting action can bypass approval. |
| Tenant safety checked | Verify tenant data cannot leak across API, database, storage, logs, or exports. |
| Audit events checked | Verify important decisions and approvals are logged. |

## Branch And Commit Guidance
- Use focused branches named by area, such as `docs/foundation`, `api/product-profiles`, or `worker/bulk-export`.
- Keep commits reviewable and mention behavior changes in commit messages.
- Do not commit `.env`, customer uploads, generated exports, local reports, or secrets.

## Review Checklist
| Area | Reviewer question |
| --- | --- |
| Product | Does this support the MVP workflow and customer approval model? |
| Domain | Are ad rules deterministic and documented? |
| Architecture | Are contracts, ownership, and data flow clear? |
| AI | Is AI bounded by schema, logs, and guardrails? |
| Security | Are auth, tenant scope, storage, and secrets handled safely? |
| Testing | Are unit, integration, and E2E expectations met for the risk level? |

## Documentation Standard
Every documentation file should help an AI-assisted engineer make fewer assumptions. Avoid vague placeholders. Include inputs, outputs, rules, failure modes, and acceptance criteria where relevant.

