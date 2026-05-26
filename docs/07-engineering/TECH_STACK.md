# Tech Stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Frontend | Next.js, TypeScript | Strong SaaS dashboard foundation and typed UI. |
| UI | Tailwind CSS, shadcn/ui, lucide-react | Fast, accessible, consistent components. |
| Charts | Recharts | Practical dashboard charting. |
| Backend | FastAPI, Python | Excellent data processing and API ergonomics. |
| Database | Supabase PostgreSQL | Managed Postgres, auth integration, RLS. |
| Storage | Supabase Storage | Private workspace-scoped files and exports. |
| Processing | Pandas, openpyxl | CSV/XLSX cleaning and generation. |
| Workers | Python background workers | Isolate long-running processing. |
| Auth | Supabase Auth | MVP-ready identity provider. |
| AI | Provider-agnostic abstraction | Avoid lock-in and preserve safety controls. |
| Tests | pytest, Vitest, Playwright | Backend rules, frontend units, E2E workflows. |

## Constraint
Do not introduce alternate major frameworks without an ADR.
