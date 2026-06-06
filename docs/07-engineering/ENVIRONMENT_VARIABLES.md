# Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| APP_ENV | Yes | local, test, preview, staging, production. Missing or unknown values fail closed for workspace auth. |
| DEV_HOST | Local dev only | Host used by the dev launcher. Defaults to `127.0.0.1`. |
| WEB_DEV_PORT | Local dev only | Preferred web dev port. Defaults to `4310`; launcher scans upward if busy. |
| API_DEV_PORT | Local dev only | Preferred API dev port. Defaults to `8720`; launcher scans upward if busy. |
| WEB_APP_URL | Yes | Frontend base URL. |
| API_BASE_URL | Yes | API base URL. |
| NEXT_PUBLIC_API_BASE_URL | Browser only | Frontend API base URL exposed to Next.js. `npm run dev` sets this to the selected API port. |
| FASTAPI_HOST | Local/API | Uvicorn host when running the API directly. |
| FASTAPI_PORT | Local/API | Preferred API port when running the API directly. `npm run dev:api` scans upward if busy. |
| CORS_ALLOWED_ORIGINS | API | Comma-separated browser origins allowed to call the API. `npm run dev` sets this to the selected web port. |
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
- The FastAPI SQLAlchemy engine uses non-persistent connections for `DATABASE_URL` so repeated Agent Control Center saves do not hold Supabase pooler session slots.
- Server-side Supabase Storage requires a valid `SUPABASE_SERVICE_ROLE_KEY`; anon and publishable keys are not sufficient for backend upload/export object writes.
- `SUPABASE_STORAGE_BUCKET_UPLOADS` must point to a private bucket that exists in the Supabase project, such as `workspace-uploads`.

## Local Port Selection
- Use `npm run dev` to start the web app and API together. The launcher chooses app-specific ports before either service starts, avoiding common defaults such as `3000`, `5173`, `8000`, and `8080`.
- Default local URLs are `http://127.0.0.1:4310` for web and `http://127.0.0.1:8720` for API. If a port is busy, the launcher scans upward and prints the selected URLs.
- When both services are started together, the launcher injects `NEXT_PUBLIC_API_BASE_URL`, `API_BASE_URL`, `WEB_APP_URL`, and `CORS_ALLOWED_ORIGINS` so the frontend and backend agree on the selected ports.
