from uuid import UUID

from sqlalchemy import text

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.sqlite_init import initialize_sqlite_schema
from apps.api.app.repositories.custom_agents import AgentTemplateRepository


def test_sqlite_bootstrap_creates_custom_agent_runtime_tables(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "adsurf.db"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    get_database_engine.cache_clear()

    initialize_sqlite_schema()

    engine = get_database_engine()
    expected_tables = {
        "custom_agents",
        "agent_tools",
        "knowledge_bases",
        "knowledge_base_files",
        "agent_templates",
        "custom_agent_runs",
    }
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("select name from sqlite_master where type = 'table'")
            ).all()
        }
        local_workspace = connection.execute(
            text("select id from workspaces where id = '00000000-0000-0000-0000-000000000001'")
        ).scalar_one_or_none()
        product_fk_index = connection.execute(
            text("select name from sqlite_master where type = 'index' and name = 'product_profiles_workspace_id_id_unique'")
        ).scalar_one_or_none()

    assert expected_tables.issubset(tables)
    assert local_workspace == "00000000-0000-0000-0000-000000000001"
    assert product_fk_index == "product_profiles_workspace_id_id_unique"

    templates = AgentTemplateRepository().list_templates()
    assert len(templates) == 5
    assert all(isinstance(template.config_json, dict) for template in templates)
    assert all(UUID(str(template.id)) for template in templates)

    get_database_engine.cache_clear()
    get_settings.cache_clear()
