# Coding Standards

## General
- Keep rule logic deterministic, tested, and documented.
- Use typed contracts for API request and response payloads.
- Keep tenant id explicit in backend queries and worker payloads.
- Store audit events for customer-impacting decisions.
- Update docs when behavior changes.

## Backend
Use FastAPI routers by domain, Pydantic schemas for contracts, service modules for orchestration, and isolated rule modules for business decisions.

## Frontend
Use typed API clients, shadcn/ui components, Tailwind utility classes, and clear loading/error/empty states.

## Workers
Workers must be idempotent, retry-safe, tenant-scoped, and able to resume from stored state.

