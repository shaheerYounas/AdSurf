# Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| APP_ENV | Yes | local, test, preview, staging, production. Missing or unknown values fail closed for workspace auth. |
| WEB_APP_URL | Yes | Frontend base URL. |
| API_BASE_URL | Yes | API base URL. |
| SUPABASE_URL | Yes | Supabase project URL. |
| SUPABASE_ANON_KEY | Yes | Browser-safe Supabase key. |
| SUPABASE_PUBLISHABLE_KEY | Browser only | Supabase publishable key for frontend clients when used. |
| SUPABASE_SERVICE_ROLE_KEY | Server only | Backend/admin operations. |
| DATABASE_URL | Server only | Postgres connection. |
| AI_PROVIDER | Optional in MVP | Selected AI backend. |
| AI_API_KEY | Optional in MVP | AI provider credential. |
| AI_FALLBACK_PROVIDER | Optional in MVP | Fallback AI provider (e.g., freemodel). |
| AI_FALLBACK_API_KEY | Optional in MVP | Fallback AI provider API credential. |
| AI_FALLBACK_MODEL | Optional in MVP | Fallback AI model name (e.g., FRE-5.5). |
| AI_FALLBACK_BASE_URL | Optional in MVP | Fallback AI API base URL. |
| AI_RECOMMENDATION_MODE | Optional | `deepseek`, `deterministic_fallback`, or `hybrid`. Defaults to deterministic fallback for local development. |
| AI_REQUEST_TIMEOUT_SECONDS | Optional | Timeout for AI provider requests. |
| DEEPSEEK_API_KEY | Required for DeepSeek recommendations | DeepSeek API credential. Never log or commit this value. |
| DEEPSEEK_BASE_URL | Optional | DeepSeek OpenAI-compatible base URL. Defaults to `https://api.deepseek.com`. |
| DEEPSEEK_MODEL | Optional | DeepSeek model used for recommendation generation. Defaults to `deepseek-chat`. |
| DEFAULT_DAILY_BUDGET_USD | Yes | Default $10 budget. |
| DEFAULT_BID_USD | Yes | Default $1.00 bid. |

## Rule
`.env.example` documents variables; real `.env` files are never committed.

## Supabase Local Development Notes
- `DATABASE_URL` should use Supabase's IPv4-compatible pooler connection string when the direct `db.<project-ref>.supabase.co` host is not reachable from the local network.
- Server-side Supabase Storage requires a valid `SUPABASE_SERVICE_ROLE_KEY`; anon and publishable keys are not sufficient for backend upload/export object writes.
- `SUPABASE_STORAGE_BUCKET_UPLOADS` must point to a private bucket that exists in the Supabase project, such as `workspace-uploads`.
