BEGIN;

-- Public views default to owner/definer permissions in Postgres. Keep this
-- analytics view in invoker mode so ai_runs workspace RLS applies to callers.
ALTER VIEW public.token_usage_by_workspace
SET (security_invoker = true);

COMMIT;
