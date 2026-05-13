# Security

## Security Model
This product handles customer business data, uploaded keyword research, generated campaign exports, and future Amazon Ads credentials. Treat all tenant data as confidential.

## MVP Security Requirements
| Area | Requirement |
| --- | --- |
| Auth | Supabase Auth validates users; backend enforces tenant membership and role. |
| Authorization | Roles control profile edits, uploads, approvals, exports, admin actions, and audit access. |
| Storage | Uploaded files and generated exports live in tenant-scoped Supabase Storage paths. |
| Secrets | Secrets are environment variables only and never committed. |
| AI data | AI providers receive only minimum necessary structured data. |
| Audit | Log uploads, scoring runs, campaign generation, exports, recommendations, and approvals. |
| Dangerous actions | No live ad change can occur in MVP; later API execution must require approval records. |

## Data Classification
| Data | Classification | Handling |
| --- | --- | --- |
| Product profiles | Confidential | Tenant-scoped database rows. |
| Uploaded research files | Confidential | Private storage, signed URL access only. |
| Generated bulk sheets | Confidential | Private storage, approval required before download. |
| Monitoring reports | Confidential | Tenant-scoped rows and private source files. |
| AI prompts and outputs | Confidential | Store metadata and structured outputs; redact secrets. |
| Amazon Ads tokens | Restricted future data | Not in MVP; later encrypted and access-controlled. |

## Vulnerability Handling
Report security issues privately to the repository owner. Do not open public issues with exploit details. Fixes must include tests or verification notes and update documentation if behavior changes.

## Never Commit
- `.env` files
- Supabase service role keys
- AI provider API keys
- Amazon Ads API credentials
- Customer uploads
- Generated bulk sheets
- Monitoring exports
- Local logs containing tenant data

