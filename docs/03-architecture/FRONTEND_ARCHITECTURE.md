# Frontend Architecture

## Responsibilities
| Area | Frontend owns |
| --- | --- |
| Navigation | Product profiles, uploads, keyword review, campaign plans, exports, monitoring, recommendations, audit. |
| Forms | Validate required user inputs before API calls. |
| Review UI | Show scores, rejection reasons, plan structure, negatives, and recommendation evidence. |
| Approval UI | Require explicit confirmation for approvals and rejections. |
| Charts | Display spend, clicks, sales, ACOS, and recommendation timeline with Recharts. |

## Constraints
- Use server-aware auth state from Supabase Auth.
- Never infer tenant access client-side only.
- Do not hide approval risk behind vague button copy.
- Show deterministic rule explanations near AI summaries.

## Acceptance Criteria
- Users can complete MVP workflow without reading raw spreadsheets.
- Every approval action shows what will change and records user intent through the API.

