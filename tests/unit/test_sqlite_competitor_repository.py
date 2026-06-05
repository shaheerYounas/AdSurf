from datetime import UTC, datetime
from uuid import UUID, uuid4

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.sqlite_init import initialize_sqlite_schema
from apps.api.app.repositories.competitor_cleaned import PostgresCompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow, CompetitorUploadStatus


def test_sqlite_competitor_repository_inserts_upload_and_cleaned_rows(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "adsurf.db"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    get_database_engine.cache_clear()

    try:
        initialize_sqlite_schema()
        engine = get_database_engine()
        repository = PostgresCompetitorCleanedRepository(engine=engine)
        workspace_id = UUID("00000000-0000-0000-0000-000000000001")
        upload_id = uuid4()

        upload = repository.create_upload(
            upload_id=upload_id,
            workspace_id=workspace_id,
            product_id=None,
            original_filename="competitors.csv",
            storage_path=f"uploads/{upload_id}/competitors.csv",
            mime_type="text/csv",
            file_size_bytes=128,
            uploaded_by=str(uuid4()),
        )
        assert upload.status == CompetitorUploadStatus.QUEUED
        assert upload.created_at is not None

        inserted = repository.insert_rows(
            rows=[
                CompetitorCleanedRow(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    competitor_upload_id=upload_id,
                    row_number=1,
                    search_term="ceramic planter",
                    search_volume=1200,
                    competitor_rank_values_json=[{"competitor": "A", "numeric_value": 1}],
                    raw_metrics_json={"Search Term": "ceramic planter"},
                    created_at=datetime.now(UTC),
                )
            ]
        )

        rows, total = repository.list_rows(workspace_id=workspace_id, competitor_upload_id=upload_id)

        assert inserted == 1
        assert total == 1
        assert rows[0].created_at is not None
        assert rows[0].competitor_rank_values_json == [{"competitor": "A", "numeric_value": 1}]
        assert rows[0].raw_metrics_json == {"Search Term": "ceramic planter"}
    finally:
        get_database_engine.cache_clear()
        get_settings.cache_clear()
