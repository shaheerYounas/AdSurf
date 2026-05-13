# Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| APP_ENV | Yes | local, preview, staging, production. |
| WEB_APP_URL | Yes | Frontend base URL. |
| API_BASE_URL | Yes | API base URL. |
| SUPABASE_URL | Yes | Supabase project URL. |
| SUPABASE_ANON_KEY | Yes | Browser-safe Supabase key. |
| SUPABASE_SERVICE_ROLE_KEY | Server only | Backend/admin operations. |
| DATABASE_URL | Server only | Postgres connection. |
| AI_PROVIDER | Optional in MVP | Selected AI backend. |
| AI_API_KEY | Optional in MVP | AI provider credential. |
| DEFAULT_DAILY_BUDGET_USD | Yes | Default $10 budget. |
| DEFAULT_BID_USD | Yes | Default $1.00 bid. |

## Rule
`.env.example` documents variables; real `.env` files are never committed.

