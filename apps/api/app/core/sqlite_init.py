"""SQLite schema initialization. Creates tables on first use if they don't exist."""

from functools import lru_cache
from pathlib import Path

from apps.api.app.core.database import get_database_engine


_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "scripts" / "sqlite_schema.sql"


@lru_cache
def _get_schema_sql() -> str:
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def initialize_sqlite_schema() -> None:
    """Run CREATE TABLE IF NOT EXISTS for all schema objects."""
    engine = get_database_engine()
    schema_sql = _get_schema_sql()
    # Split on CREATE TABLE and CREATE INDEX because execute() can't run multiple statements
    # We'll split carefully and run each DDL statement individually.
    statements = _split_ddl_statements(schema_sql)
    with engine.begin() as connection:
        for stmt in statements:
            clean = stmt.strip()
            if not clean or clean.startswith("--"):
                continue
            try:
                connection.exec_driver_sql(clean)
            except Exception as exc:
                # Table/index already exists is fine in some edge cases
                if "already exists" not in str(exc).lower():
                    raise


def _split_ddl_statements(schema: str) -> list[str]:
    """Split schema SQL into individual DDL statements.

    Handles CREATE TABLE, CREATE INDEX, INSERT INTO, and ALTER TABLE
    by detecting statement terminators (closing ); or bare ;).
    """
    statements: list[str] = []
    current: list[str] = []

    for line in schema.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        # A DDL statement ends with ); or just ; at end of line
        is_closing = stripped.rstrip(";").rstrip().endswith(");")
        is_semicolon = stripped.rstrip().endswith(";") and not is_closing
        if is_closing or is_semicolon:
            stmt = "\n".join(current).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        remaining = "\n".join(current).strip()
        if remaining and not remaining.startswith("--"):
            statements.append(remaining)

    return statements
