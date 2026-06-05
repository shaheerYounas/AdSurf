"""Quick test to verify all database fixes work with SQLite."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("DATABASE_URL", "sqlite:///./apps/api/adsurf.db")
os.environ.setdefault("STORAGE_ADAPTER", "local")

from uuid import uuid4
from apps.api.app.core.database import get_database_engine
from sqlalchemy import text

def test_datetime_now():
    """Test that datetime('now') works in SQLite."""
    engine = get_database_engine()
    with engine.begin() as conn:
        result = conn.execute(text("select datetime('now')")).scalar_one()
        assert result is not None, "datetime('now') returned None"
    print("✓ datetime('now') works")

def test_json_insert_without_cast():
    """Test that JSON parameters can be inserted without cast(... as jsonb)."""
    import json
    engine = get_database_engine()
    workspace_id = "00000000-0000-0000-0000-000000000001"
    with engine.begin() as conn:
        # Test inserting JSON into audit_logs without cast
        conn.execute(
            text("""
                insert into audit_logs (id, workspace_id, actor_user_id, event_type, object_type, object_id, metadata_json, created_at)
                values (:id, :workspace_id, :actor_user_id, :event_type, :object_type, :object_id, :metadata_json, :created_at)
            """),
            {
                "id": str(uuid4()),
                "workspace_id": workspace_id,
                "actor_user_id": None,
                "event_type": "test.db_fix_verification",
                "object_type": "test",
                "object_id": None,
                "metadata_json": json.dumps({"test": True, "fix": "jsonb_removed"}),
                "created_at": "2026-06-04T00:00:00Z",
            }
        )
    print("✓ JSON insert without cast(... as jsonb) works")

def test_monitoring_import_insert():
    """Test monitoring import insert with fixed SQL."""
    import json
    from datetime import UTC, datetime
    engine = get_database_engine()
    workspace_id = "00000000-0000-0000-0000-000000000001"

    # First need a product_id and upload_id that exist
    with engine.begin() as conn:
        product = conn.execute(
            text("select id from product_profiles where workspace_id = :wsid limit 1"),
            {"wsid": workspace_id}
        ).mappings().first()
        upload = conn.execute(
            text("select id from uploads where workspace_id = :wsid limit 1"),
            {"wsid": workspace_id}
        ).mappings().first()
        parse_run = conn.execute(
            text("select id from upload_parse_runs where workspace_id = :wsid limit 1"),
            {"wsid": workspace_id}
        ).mappings().first()

    if not product or not upload or not parse_run:
        print("⚠ Skipping monitoring import test - no data in DB")
        return

    now = datetime.now(UTC).isoformat()
    import_id = str(uuid4())
    engine2 = get_database_engine()
    with engine2.begin() as conn:
        conn.execute(
            text("""
                insert into monitoring_imports (
                    id, workspace_id, product_id, upload_id, parse_run_id, report_type, status,
                    date_range_start, date_range_end, total_rows, processed_rows, error_rows,
                    data_quality_warnings_json, created_by, error_message, created_at, updated_at
                )
                values (
                    :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :report_type, :status,
                    :date_range_start, :date_range_end, :total_rows, :processed_rows, :error_rows,
                    :data_quality_warnings_json, :created_by, :error_message, :created_at, :updated_at
                )
            """),
            {
                "id": import_id,
                "workspace_id": workspace_id,
                "product_id": str(product["id"]),
                "upload_id": str(upload["id"]),
                "parse_run_id": str(parse_run["id"]),
                "report_type": "sponsored_products_search_term",
                "status": "queued",
                "date_range_start": None,
                "date_range_end": None,
                "total_rows": 0,
                "processed_rows": 0,
                "error_rows": 0,
                "data_quality_warnings_json": json.dumps([]),
                "created_by": "00000000-0000-0000-0000-000000000001",
                "error_message": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        # Clean up
        conn.execute(text("delete from monitoring_imports where id = :id"), {"id": import_id})
    print("✓ monitoring_imports insert without cast(... as jsonb) works")

def test_update_with_datetime_now():
    """Test that datetime('now') in UPDATE works."""
    engine = get_database_engine()
    workspace_id = "00000000-0000-0000-0000-000000000001"
    with engine.begin() as conn:
        # Just test the syntax; if no rows match the where clause it still validates SQL
        conn.execute(
            text("""
                update recommendations
                set status = 'pending',
                    decided_at = datetime('now'), updated_at = datetime('now')
                where workspace_id = :workspace_id and id = :fake_id
            """),
            {"workspace_id": workspace_id, "fake_id": str(uuid4())}
        )
    print("✓ datetime('now') in UPDATE works")

def test_is_null_safe_equals():
    """Test IS operator for NULL-safe comparison (replaces IS NOT DISTINCT FROM)."""
    engine = get_database_engine()
    workspace_id = "00000000-0000-0000-0000-000000000001"
    with engine.begin() as conn:
        result = conn.execute(
            text("select count(*) from agent_configs where workspace_id = :wsid and product_id IS :product_id"),
            {"wsid": workspace_id, "product_id": None}
        ).scalar_one()
        assert isinstance(result, int)
    print("✓ IS (NULL-safe equality) works as replacement for IS NOT DISTINCT FROM")

def main():
    print("Testing database fixes...")
    print()
    test_datetime_now()
    test_json_insert_without_cast()
    test_monitoring_import_insert()
    test_update_with_datetime_now()
    test_is_null_safe_equals()
    print()
    print("All database tests passed!")

if __name__ == "__main__":
    main()
