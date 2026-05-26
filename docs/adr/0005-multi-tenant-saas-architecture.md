# ADR 0005: Multi-Workspace SaaS Architecture

## Status
Accepted.

## Decision
Design the product as a multi-workspace SaaS from the start, with workspace-scoped database rows, storage paths, authorization checks, and audit logs.

## Consequences
Every workspace-owned record must carry workspace context. RLS and backend authorization are mandatory before production use.
