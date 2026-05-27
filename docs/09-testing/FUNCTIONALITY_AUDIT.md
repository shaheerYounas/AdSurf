# AdSurf Functionality Audit

## PHASE 1 — Environment and app health check

### Local Startup Commands

**Frontend**
```bash
cd apps/web
npm run dev
```

**Backend**
```bash
cd apps/api
# Uses uvicorn internally or directly
uvicorn app.main:app --reload
```

**Workers**
Background jobs might be handled directly in the FastAPI process using BackgroundTasks or via Celery/arq. Need to verify.

**Tests**
```bash
# Frontend
cd apps/web
npm run test

# Backend
cd apps/api
pytest
```

**Migrations**
Supabase migrations:
```bash
supabase start # starts local db and applies migrations
supabase db push
```

### Missing Env Vars / Blockers
- Need to ensure `NEXT_PUBLIC_API_BASE_URL` points to `http://localhost:8000` or whatever the backend runs on.
- Need a valid `.env` with Supabase local keys and any external API Keys like DeepSeek.

## PHASE 2 — Feature Checklist

### A. App shell/navigation
- [ ] Dashboard link
- [ ] Agents link
- [ ] Products link
- [ ] New product link
- [ ] Recommendations link
- [ ] Approvals link
- [ ] Settings link
- [ ] Agent Ops sidebar links
- [ ] Main menu link

### B. Dashboard
- [ ] loads workspace summary
- [ ] refresh button works
- [ ] product counts show
- [ ] upload counts show
- [ ] pending recommendations show
- [ ] error state appears if API fails
- [ ] empty state appears if no data

### C. Products
- [ ] product list loads
- [ ] create product form opens
- [ ] create product works
- [ ] product detail opens
- [ ] product data saves correctly
- [ ] validation errors display

### D. Single-product upload flow
- [ ] choose CSV/XLSX file
- [ ] upload button enabled after file selected
- [ ] upload request is sent
- [ ] upload record is created
- [ ] file bytes are stored
- [ ] upload status changes
- [ ] parse worker/process runs
- [ ] parse result appears
- [ ] errors show if upload fails

### E. Account-level / Agent Control Center upload flow
- [ ] choose report file
- [ ] upload button enabled
- [ ] button click fires handler
- [ ] loading state appears
- [ ] API request is sent
- [ ] account import/upload record is created
- [ ] report type detection runs
- [ ] product/entity grouping starts
- [ ] agent workflow begins or queues
- [ ] success message appears
- [ ] failure message appears if backend fails
- [ ] user can see next step

### F. Agent Control Center
- [ ] agent cards load
- [ ] agent configs load
- [ ] workflow canvas loads
- [ ] inspector opens when agent clicked
- [ ] config changes save
- [ ] pause works
- [ ] resume works
- [ ] stop works
- [ ] rerun works
- [ ] rerun from selected agent works
- [ ] trace timeline loads
- [ ] approval checkpoints load
- [ ] simple/advanced mode works
- [ ] no controls silently fail

### G. AI recommendation flow
- [ ] DeepSeek mode loads config
- [ ] missing API key gives clear error
- [ ] DeepSeek API call happens when configured
- [ ] deterministic fallback works
- [ ] hybrid mode works
- [ ] AI output validation works
- [ ] invalid AI output is rejected safely
- [ ] AI run is logged
- [ ] recommendations are saved
- [ ] recommendations appear in UI

### H. Recommendations
- [ ] list loads
- [ ] filters work
- [ ] recommendation detail opens
- [ ] approve button works
- [ ] reject button works
- [ ] note is required
- [ ] audit record is created
- [ ] approval does not execute live Amazon Ads changes

### I. Approvals
- [ ] pending approvals load
- [ ] historical approvals load
- [ ] approval details show evidence
- [ ] error states work

### J. Workers
- [ ] upload parsing worker works
- [ ] monitoring worker works
- [ ] agent workflow worker works if present
- [ ] failed jobs are visible
- [ ] retry works if supported

## PHASE 10 — Initial Findings
1. Working features: File parsing, basic UI rendering, routing
2. Broken features: The "Upload Report" button was swallowing `fetch` errors transparently without showing them near the button.
3. Mock-only UI features: Many Agent Ops features (status colors, advanced flow UI toggles) don't have full backend fidelity when backend lacks data.
4. Missing backend endpoints: Need further debugging around `process-upload-jobs` in a truly detached background worker vs current HTTP endpoint trigger.
5. Frontend buttons not wired: Error handling across the application requires deeper API client wraps to show visually (toast notification framework is missing).
6. Backend endpoints not called: None observed yet out of the standard flow.
7. Database/storage blockers: If `.env` lacks storage credentials, upload fails early and needs proper visibility.
8. Recommended fix order:
   - Add a global Toast/Snackbar component.
   - Centralize API error handling in `client.ts` using the Toast system.
   - Start running End-to-End Playwright tests in CI.
