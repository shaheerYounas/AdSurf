# ADR 0005: Multi-Tenant SaaS Architecture

## Status
Accepted.

## Decision
Design the product as a multi-tenant SaaS from the start, with tenant-scoped database rows, storage paths, authorization checks, and audit logs.

## Consequences
Every tenant-owned record must carry tenant context. RLS and backend authorization are mandatory before production use.

