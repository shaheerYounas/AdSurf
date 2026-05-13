# Local Development

## MVP Setup Intent
Local development will eventually run Next.js, FastAPI, Python workers, Supabase local services or a development Supabase project, and test suites.

## Expected Commands Later
| Command | Purpose |
| --- | --- |
| `pnpm dev` | Start frontend when scaffolded. |
| `uvicorn` or equivalent | Start FastAPI when scaffolded. |
| `pytest` | Run backend and worker tests. |
| `vitest` | Run frontend unit tests. |
| `playwright test` | Run E2E tests. |

## Local Data Rules
Use synthetic product profiles and anonymized spreadsheets. Never commit customer uploads, generated exports, `.env`, or local reports.

