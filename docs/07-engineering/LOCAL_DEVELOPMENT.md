# Local Development

## MVP Setup Intent
Local development will eventually run Next.js, FastAPI, Python workers, Supabase local services or a development Supabase project, and test suites.

## Expected Commands Later
| Command | Purpose |
| --- | --- |
| `npm run dev:web` | Start the Next.js frontend shell. |
| `npm run dev:api` | Start the FastAPI backend shell with Uvicorn. |
| `python -m pytest tests/unit tests/integration` | Run backend, migration, and documentation guardrail tests. |
| `npm --workspace apps/web run test` | Run frontend unit tests. |
| `playwright test` | Run E2E tests. |

## Local Data Rules
Use synthetic product profiles and anonymized spreadsheets. Never commit customer uploads, generated exports, `.env`, or local reports.

## Batch 1 Status
Batch 1 may use placeholder auth and in-memory product profile storage while Supabase Auth, RLS, and Postgres persistence are being scaffolded. These placeholders must remain isolated from production settings and must be replaced before upload, keyword, campaign, export, monitoring, or recommendation workflows are implemented.

Placeholder auth is allowed only when `APP_ENV` is `local` or `test`. Missing, unknown, preview, staging, and production values fail closed until real Supabase Auth and workspace membership checks are configured.

In preview, staging, and production, deployed auth also fails closed with `AUTH_NOT_CONFIGURED` when `SUPABASE_JWT_SECRET` is missing. The JWT verification skeleton must not accept bearer tokens until Supabase Auth verification and workspace membership lookup are configured.

## Batch 2 Local API Auth Headers
Local/test API requests to workspace-scoped routes must include:

| Header | Purpose |
| --- | --- |
| `x-user-id` | Synthetic local/test user id. |
| `x-test-workspaces` | Comma-separated `{workspace_id}:{role}` entries for role-per-workspace test membership. |

Example:

```text
x-test-workspaces: 00000000-0000-0000-0000-000000000001:analyst,00000000-0000-0000-0000-000000000002:viewer
```

The role applies only to the workspace listed in the same entry.

## Batch 2 Database Behavior
When `DATABASE_URL` is configured, product profile routes use the database repository. When `DATABASE_URL` is absent in local/test, a local repository adapter is used for tests and scaffolding only. Outside local/test, missing `DATABASE_URL` fails closed.

For offline SQLite development, the API initializes its local schema on startup from `scripts/sqlite_schema.sql`. The bootstrap includes product, upload, campaign, monitoring, workflow, and custom agent builder runtime tables, plus seed rows for public custom agent templates. Custom agent builder routes must validate the parent agent, knowledge base, thread, memory, and run against the requested `workspace_id` before returning or mutating child records.

When starting the API from the repository root with `npm run dev:api`, `python-dotenv` loads the root `.env` first. Keep the root `DATABASE_URL` aligned with the SQLite file you intend to inspect, for example:

```bash
DATABASE_URL=sqlite:///./apps/api/adsurf.db
```

The API-local `.env` files are useful reference copies, but they are not the first env files loaded by the root dev command.

## Batch 3 Upload Development
Local/test upload initialization uses the fake storage adapter by default and returns a `local-fake://signed-upload/...` URL. Preview, staging, and production do not silently use fake storage. To use fake storage in preview, set both:

```bash
$env:APP_ENV="preview"
$env:STORAGE_ADAPTER="fake"
$env:ALLOW_FAKE_STORAGE_IN_PREVIEW="true"
```

Production and staging should use `STORAGE_ADAPTER=supabase` once signed Supabase upload URL creation is wired. Local/test still returns a `local-fake://signed-upload/...` target for metadata parity, and the browser shell writes bytes through `PUT /v1/workspaces/{workspace_id}/uploads/{upload_id}/object` before confirming the upload. The worker then reads the stored object through the same storage adapter.

Batch 4 local worker reads uploaded objects through the same storage adapter. For local/test, place files under:

```bash
$env:LOCAL_UPLOAD_STORAGE_ROOT=".local-storage/uploads"
```

The local storage adapter maps server-generated storage paths under that root. The worker still does not read arbitrary local paths directly.

For local/test browser demos, `POST /v1/dev/process-upload-jobs` runs queued upload parsing jobs inside the API process. This endpoint is disabled outside `local` and `test` and exists only because in-memory local repositories are not shared with a separate worker process.

To reload the local Sponsored Products search-term report demo after restarting the API, keep the local API and web servers running and run:

```bash
python scripts/import_search_term_reports.py
```

For the frontend upload shell, set a local workspace id if you want the workspace field prefilled:

```bash
$env:NEXT_PUBLIC_LOCAL_WORKSPACE_ID="00000000-0000-0000-0000-000000000001"
```

## Optional Local RLS Integration Test
Run the static backend tests with:

```bash
python -m pytest tests/unit tests/integration
```

Run live RLS integration tests against a disposable local Postgres or Supabase database with:

```bash
$env:RLS_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:54322/postgres"
python -m pytest tests/integration/test_rls_integration.py
```

The RLS test is skipped unless `RLS_TEST_DATABASE_URL` is set and points to `localhost` or `127.0.0.1`. Use only a disposable local database because the test resets the foundation tables.

## Fixture File Exception
Spreadsheet files are ignored by default. Synthetic `.xls` and `.xlsx` fixtures may be committed only under `tests/fixtures/`.
