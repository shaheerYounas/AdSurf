# ADR 0001: Use Next.js, FastAPI, and Supabase

## Status
Accepted.

## Decision
Use Next.js and TypeScript for the web app, FastAPI and Python for the API and workers, and Supabase PostgreSQL/Auth/Storage for persistence, identity, and files.

## Consequences
This stack supports a fast MVP, strong spreadsheet processing, managed auth/storage, and clear separation between dashboard, API, and workers. Major stack changes require a new ADR.

