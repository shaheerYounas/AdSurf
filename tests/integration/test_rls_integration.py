import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


RLS_TEST_DATABASE_URL = os.getenv("RLS_TEST_DATABASE_URL")


pytestmark = pytest.mark.skipif(
    not RLS_TEST_DATABASE_URL,
    reason="Set RLS_TEST_DATABASE_URL to a disposable local Postgres/Supabase database to run RLS integration tests.",
)


def test_foundation_rls_policies_enforce_workspace_membership_and_roles() -> None:
    if RLS_TEST_DATABASE_URL and "localhost" not in RLS_TEST_DATABASE_URL and "127.0.0.1" not in RLS_TEST_DATABASE_URL:
        pytest.skip("RLS_TEST_DATABASE_URL must point to a local disposable database.")

    engine = create_engine(_normalize_database_url(RLS_TEST_DATABASE_URL), isolation_level="AUTOCOMMIT")
    user_a = uuid4()
    non_member = uuid4()
    workspace_a = uuid4()
    workspace_b = uuid4()
    workspace_c = uuid4()

    with engine.connect() as connection:
        _reset_database(connection)
        _install_supabase_auth_shim(connection)
        _apply_migrations(connection)
        _grant_test_privileges(connection)
        product_ids = _seed_workspace_data(connection, user_a, workspace_a, workspace_b, workspace_c)

        _become_authenticated_user(connection, user_a)
        memberships = connection.execute(text("select workspace_id from workspace_members order by workspace_id")).all()
        visible_products = connection.execute(text("select workspace_id from product_profiles order by workspace_id")).all()
        visible_uploads = connection.execute(text("select workspace_id from uploads order by workspace_id")).all()

        assert {row.workspace_id for row in memberships} == {workspace_a, workspace_b}
        assert {row.workspace_id for row in visible_products} == {workspace_a, workspace_b}
        assert {row.workspace_id for row in visible_uploads} == {workspace_a, workspace_b}

        connection.execute(
            text(
                """
                insert into product_profiles (workspace_id, product_name)
                values (:workspace_id, 'Analyst Insert Allowed')
                """
            ),
            {"workspace_id": workspace_a},
        )

        with pytest.raises(SQLAlchemyError):
            connection.execute(
                text(
                    """
                    insert into product_profiles (workspace_id, product_name)
                    values (:workspace_id, 'Viewer Insert Blocked')
                    """
                ),
                {"workspace_id": workspace_b},
            )

        connection.execute(
            text(
                """
                insert into uploads (
                    workspace_id, product_id, original_filename, storage_path, mime_type,
                    file_size_bytes, source_type
                )
                values (
                    :workspace_id, :product_id, 'Analyst Upload.csv', :storage_path, 'text/csv',
                    100, 'competitor_keyword_research'
                )
                """
            ),
            {
                "workspace_id": workspace_a,
                "product_id": product_ids[workspace_a],
                "storage_path": f"/workspaces/{workspace_a}/products/{product_ids[workspace_a]}/uploads/{uuid4()}/raw/analyst.csv",
            },
        )

        with pytest.raises(SQLAlchemyError):
            connection.execute(
                text(
                    """
                    insert into uploads (
                        workspace_id, product_id, original_filename, storage_path, mime_type,
                        file_size_bytes, source_type
                    )
                    values (
                        :workspace_id, :product_id, 'Viewer Upload.csv', :storage_path, 'text/csv',
                        100, 'competitor_keyword_research'
                    )
                    """
                ),
                {
                    "workspace_id": workspace_b,
                    "product_id": product_ids[workspace_b],
                    "storage_path": f"/workspaces/{workspace_b}/products/{product_ids[workspace_b]}/uploads/{uuid4()}/raw/viewer.csv",
                },
            )

        _become_authenticated_user(connection, non_member)
        non_member_products = connection.execute(text("select id from product_profiles")).all()
        non_member_uploads = connection.execute(text("select id from uploads")).all()

        assert non_member_products == []
        assert non_member_uploads == []


def test_parse_child_records_reject_mismatched_parse_run_scope() -> None:
    if RLS_TEST_DATABASE_URL and "localhost" not in RLS_TEST_DATABASE_URL and "127.0.0.1" not in RLS_TEST_DATABASE_URL:
        pytest.skip("RLS_TEST_DATABASE_URL must point to a local disposable database.")

    engine = create_engine(_normalize_database_url(RLS_TEST_DATABASE_URL), isolation_level="AUTOCOMMIT")
    workspace_a = uuid4()
    workspace_b = uuid4()
    upload_a = uuid4()
    upload_b = uuid4()
    parse_run_a = uuid4()
    job_a = uuid4()

    with engine.connect() as connection:
        _reset_database(connection)
        _install_supabase_auth_shim(connection)
        _apply_migrations(connection)
        product_a = _insert_workspace_product_upload(connection, workspace_a, upload_a, "A")
        product_b = _insert_workspace_product_upload(connection, workspace_b, upload_b, "B")
        connection.execute(
            text(
                """
                insert into job_queue (id, workspace_id, job_type, idempotency_key)
                values (:job_id, :workspace_id, 'process_upload', :idempotency_key)
                """
            ),
            {"job_id": job_a, "workspace_id": workspace_a, "idempotency_key": str(job_a)},
        )
        connection.execute(
            text(
                """
                insert into upload_parse_runs (
                    id, workspace_id, product_id, upload_id, job_id, status, parser_version,
                    original_filename, storage_path, detected_file_type
                )
                values (
                    :parse_run_id, :workspace_id, :product_id, :upload_id, :job_id, 'running', 'test',
                    'a.csv', '/workspaces/a/raw/a.csv', 'csv'
                )
                """
            ),
            {
                "parse_run_id": parse_run_a,
                "workspace_id": workspace_a,
                "product_id": product_a,
                "upload_id": upload_a,
                "job_id": job_a,
            },
        )

        with pytest.raises(SQLAlchemyError):
            connection.execute(
                text(
                    """
                    insert into upload_parsed_rows (
                        workspace_id, product_id, upload_id, parse_run_id, row_number,
                        row_data_json, row_hash
                    )
                    values (
                        :workspace_id, :product_id, :upload_id, :parse_run_id, 2,
                        '{"term":"shoes"}'::jsonb, 'hash'
                    )
                    """
                ),
                {
                    "workspace_id": workspace_b,
                    "product_id": product_b,
                    "upload_id": upload_b,
                    "parse_run_id": parse_run_a,
                },
            )
        connection.rollback()

        with pytest.raises(SQLAlchemyError):
            connection.execute(
                text(
                    """
                    insert into upload_parse_errors (
                        workspace_id, product_id, upload_id, parse_run_id, row_number,
                        error_code, error_message
                    )
                    values (
                        :workspace_id, :product_id, :upload_id, :parse_run_id, null,
                        'TEST_ERROR', 'bad scope'
                    )
                    """
                ),
                {
                    "workspace_id": workspace_b,
                    "product_id": product_b,
                    "upload_id": upload_b,
                    "parse_run_id": parse_run_a,
                },
            )


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _reset_database(connection) -> None:
    connection.execute(text("reset role"))
    for statement in [
        "drop table if exists approved_keyword_set_items cascade",
        "drop table if exists approved_keyword_sets cascade",
        "drop table if exists keyword_candidate_overrides cascade",
        "drop table if exists keyword_candidates cascade",
        "drop table if exists keyword_scoring_runs cascade",
        "drop table if exists upload_column_mappings cascade",
        "drop table if exists upload_column_profile_columns cascade",
        "drop table if exists upload_column_profiles cascade",
        "drop table if exists upload_parse_errors cascade",
        "drop table if exists upload_parsed_rows cascade",
        "drop table if exists upload_parse_runs cascade",
        "drop table if exists outbox_events cascade",
        "drop table if exists job_queue cascade",
        "drop table if exists rule_versions cascade",
        "drop table if exists audit_logs cascade",
        "drop table if exists uploads cascade",
        "drop table if exists product_profiles cascade",
        "drop table if exists workspace_members cascade",
        "drop table if exists workspaces cascade",
        "drop type if exists approved_keyword_set_status cascade",
        "drop type if exists reviewed_keyword_status cascade",
        "drop type if exists keyword_candidate_override_action cascade",
        "drop type if exists keyword_candidate_status cascade",
        "drop type if exists keyword_scoring_run_status cascade",
        "drop type if exists upload_column_mapping_type cascade",
        "drop type if exists upload_column_mapping_status cascade",
        "drop type if exists upload_column_inferred_data_type cascade",
        "drop type if exists upload_column_profile_status cascade",
        "drop type if exists upload_parse_status cascade",
        "drop type if exists upload_source_type cascade",
        "drop type if exists upload_status cascade",
        "drop type if exists outbox_status cascade",
        "drop type if exists job_status cascade",
        "drop type if exists product_profile_status cascade",
        "drop type if exists workspace_member_status cascade",
        "drop type if exists workspace_status cascade",
        "drop type if exists workspace_role cascade",
        "drop function if exists public.current_user_has_workspace_role(uuid, text[]) cascade",
        "drop function if exists public.current_user_is_workspace_member(uuid) cascade",
    ]:
        connection.execute(text(statement))


def _install_supabase_auth_shim(connection) -> None:
    connection.execute(text("create schema if not exists auth"))
    connection.execute(
        text(
            """
            create or replace function auth.uid()
            returns uuid
            language sql
            stable
            as $$
              select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
            $$;
            """
        )
    )
    connection.execute(
        text(
            """
            do $$
            begin
              if not exists (select 1 from pg_roles where rolname = 'authenticated') then
                create role authenticated;
              end if;
            end $$;
            """
        )
    )


def _apply_migrations(connection) -> None:
    for path in [
        Path("supabase/migrations/202605140001_initial_foundation.sql"),
        Path("supabase/migrations/202605140002_foundation_rls.sql"),
        Path("supabase/migrations/202605140003_uploads_foundation.sql"),
        Path("supabase/migrations/202605140004_upload_integrity_hardening.sql"),
        Path("supabase/migrations/202605140005_upload_parse_foundation.sql"),
        Path("supabase/migrations/202605140006_column_mapping_foundation.sql"),
        Path("supabase/migrations/202605140007_keyword_scoring_foundation.sql"),
        Path("supabase/migrations/202605140008_keyword_review_foundation.sql"),
    ]:
        connection.execute(text(path.read_text(encoding="utf-8")))


def _grant_test_privileges(connection) -> None:
    connection.execute(text("grant usage on schema public to authenticated"))
    connection.execute(
        text(
            """
            grant select on workspaces, workspace_members, product_profiles, uploads, upload_parse_runs,
              upload_parsed_rows, upload_parse_errors, upload_column_profiles, upload_column_profile_columns,
              upload_column_mappings, keyword_scoring_runs, keyword_candidates, audit_logs, rule_versions,
              keyword_candidate_overrides, approved_keyword_sets, approved_keyword_set_items,
              job_queue, outbox_events
              to authenticated
            """
        )
    )
    connection.execute(text("grant insert, update on product_profiles to authenticated"))
    connection.execute(text("grant insert, update on uploads to authenticated"))
    connection.execute(text("grant insert, update on upload_column_mappings to authenticated"))
    connection.execute(text("grant insert on keyword_candidate_overrides, approved_keyword_sets, approved_keyword_set_items to authenticated"))


def _seed_workspace_data(connection, user_a, workspace_a, workspace_b, workspace_c) -> dict:
    product_ids = {}
    for workspace_id, name in [(workspace_a, "A"), (workspace_b, "B"), (workspace_c, "C")]:
        connection.execute(
            text("insert into workspaces (id, name) values (:id, :name)"),
            {"id": workspace_id, "name": f"Workspace {name}"},
        )
        product_id = connection.execute(
            text("insert into product_profiles (workspace_id, product_name) values (:workspace_id, :name) returning id"),
            {"workspace_id": workspace_id, "name": f"Product {name}"},
        ).scalar_one()
        product_ids[workspace_id] = product_id
        connection.execute(
            text(
                """
                insert into uploads (
                    workspace_id, product_id, original_filename, storage_path, mime_type,
                    file_size_bytes, source_type
                )
                values (
                    :workspace_id, :product_id, :filename, :storage_path, 'text/csv',
                    100, 'competitor_keyword_research'
                )
                """
            ),
            {
                "workspace_id": workspace_id,
                "product_id": product_id,
                "filename": f"Product {name}.csv",
                "storage_path": f"/workspaces/{workspace_id}/products/{product_id}/uploads/{uuid4()}/raw/product-{name}.csv",
            },
        )

    connection.execute(
        text(
            """
            insert into workspace_members (workspace_id, user_id, role)
            values
              (:workspace_a, :user_a, 'analyst'),
              (:workspace_b, :user_a, 'viewer')
            """
        ),
        {"workspace_a": workspace_a, "workspace_b": workspace_b, "user_a": user_a},
    )
    return product_ids


def _insert_workspace_product_upload(connection, workspace_id, upload_id, suffix: str):
    connection.execute(text("insert into workspaces (id, name) values (:id, :name)"), {"id": workspace_id, "name": f"Workspace {suffix}"})
    product_id = connection.execute(
        text("insert into product_profiles (workspace_id, product_name) values (:workspace_id, :name) returning id"),
        {"workspace_id": workspace_id, "name": f"Product {suffix}"},
    ).scalar_one()
    connection.execute(
        text(
            """
            insert into uploads (
                id, workspace_id, product_id, original_filename, storage_path, mime_type,
                file_size_bytes, source_type
            )
            values (
                :upload_id, :workspace_id, :product_id, :filename, :storage_path, 'text/csv',
                100, 'competitor_keyword_research'
            )
            """
        ),
        {
            "upload_id": upload_id,
            "workspace_id": workspace_id,
            "product_id": product_id,
            "filename": f"Product {suffix}.csv",
            "storage_path": f"/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/product-{suffix}.csv",
        },
    )
    return product_id


def _become_authenticated_user(connection, user_id) -> None:
    try:
        connection.execute(text("reset role"))
        connection.execute(text("set role authenticated"))
    except SQLAlchemyError as exc:
        pytest.skip(f"Database role setup does not allow SET ROLE authenticated: {exc}")
    connection.execute(text("select set_config('request.jwt.claim.sub', :user_id, false)"), {"user_id": str(user_id)})
