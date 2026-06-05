-- Migration: Bulk product import tables
-- Adds tables for tracking bulk CSV/XLSX product profile imports,
-- per-row validation results, and the audit log trail.

-- ─────────────────────────────────────────────
-- Enums
-- ─────────────────────────────────────────────

do $$ begin
  create type bulk_import_status as enum (
    'parsing',
    'validating',
    'ready_for_review',
    'creating',
    'completed',
    'failed',
    'cancelled'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type bulk_import_row_status as enum (
    'valid',
    'invalid',
    'duplicate_in_file',
    'already_exists',
    'skipped',
    'created',
    'updated',
    'failed'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type bulk_import_conflict_strategy as enum (
    'skip_existing',
    'update_existing',
    'create_only_missing'
  );
exception when duplicate_object then null; end $$;

-- ─────────────────────────────────────────────
-- bulk_product_imports
-- One record per bulk file upload attempt.
-- ─────────────────────────────────────────────

create table if not exists bulk_product_imports (
  id                        uuid primary key default gen_random_uuid(),
  workspace_id              uuid not null references workspaces(id) on delete restrict,
  upload_id                 uuid null references uploads(id) on delete set null,

  -- File identity
  original_filename         text not null,
  file_hash                 text null,
  file_hash_algorithm       text not null default 'sha256',

  -- Lifecycle
  status                    bulk_import_status not null default 'parsing',
  conflict_strategy         bulk_import_conflict_strategy not null default 'skip_existing',

  -- Summary counts (filled in after validation)
  total_rows                integer not null default 0,
  valid_rows                integer not null default 0,
  invalid_rows              integer not null default 0,
  duplicate_in_file_rows    integer not null default 0,
  already_exists_rows       integer not null default 0,
  created_rows              integer not null default 0,
  updated_rows              integer not null default 0,
  skipped_rows              integer not null default 0,
  failed_rows               integer not null default 0,

  -- Column mapping detected during parse
  detected_columns_json     jsonb not null default '{}',

  -- Workspace defaults used as fallbacks
  workspace_default_acos    numeric(8,4) null,
  workspace_default_budget  numeric(12,4) null,
  workspace_default_bid     numeric(12,4) null,

  error_message             text null,
  created_by                uuid null,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

create index if not exists idx_bulk_product_imports_workspace
  on bulk_product_imports(workspace_id, created_at desc);

create index if not exists idx_bulk_product_imports_file_hash
  on bulk_product_imports(workspace_id, file_hash)
  where file_hash is not null;

-- ─────────────────────────────────────────────
-- bulk_product_import_rows
-- One record per row from the uploaded file.
-- ─────────────────────────────────────────────

create table if not exists bulk_product_import_rows (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspaces(id) on delete restrict,
  import_id           uuid not null references bulk_product_imports(id) on delete cascade,

  row_number          integer not null,
  status              bulk_import_row_status not null default 'valid',

  -- Mapped fields (null = not provided or not mapped)
  product_name        text null,
  asin                text null,
  sku                 text null,
  marketplace         text null,
  currency            text null,
  target_acos         numeric(8,4) null,
  default_budget      numeric(12,4) null,
  default_bid         numeric(12,4) null,
  brand               text null,
  category            text null,
  notes               text null,

  -- Outcome
  product_id          uuid null references product_profiles(id) on delete set null,
  validation_errors   jsonb not null default '[]',
  raw_row_json        jsonb not null default '{}',

  created_at          timestamptz not null default now()
);

create index if not exists idx_bulk_import_rows_import
  on bulk_product_import_rows(import_id, row_number);

create index if not exists idx_bulk_import_rows_status
  on bulk_product_import_rows(import_id, status);

-- ─────────────────────────────────────────────
-- Extend product_profiles with bulk import tracking fields
-- (brand, category, notes, created_from_upload_id)
-- ─────────────────────────────────────────────

alter table product_profiles
  add column if not exists brand               text null,
  add column if not exists category            text null,
  add column if not exists notes               text null,
  add column if not exists created_from_import_id uuid null
    references bulk_product_imports(id) on delete set null;

-- ─────────────────────────────────────────────
-- Audit log event types (informational comment)
-- ─────────────────────────────────────────────
-- New event_type values used by bulk import:
--   bulk_upload_started
--   product_created
--   product_skipped_duplicate
--   product_validation_failed
--   bulk_product_import_completed

comment on table bulk_product_imports is
  'Tracks bulk CSV/XLSX product profile import jobs. '
  'One record per file upload. Rows are in bulk_product_import_rows. '
  'Audit events use event_type: bulk_upload_started, product_created, '
  'product_skipped_duplicate, product_validation_failed, bulk_product_import_completed.';
