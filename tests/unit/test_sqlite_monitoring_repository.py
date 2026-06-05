from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.sqlite_init import initialize_sqlite_schema
from apps.api.app.repositories.monitoring import PostgresMonitoringRepository
from apps.api.app.schemas.monitoring import (
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)


def test_sqlite_monitoring_repository_records_decision_created_at(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "adsurf.db"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    get_database_engine.cache_clear()

    try:
        initialize_sqlite_schema()
        engine = get_database_engine()
        repository = PostgresMonitoringRepository(engine=engine)
        workspace_id = UUID("00000000-0000-0000-0000-000000000001")
        recommendation_id = uuid4()
        now = datetime.now(UTC)

        repository.insert_recommendations(
            recommendations=[
                Recommendation(
                    id=recommendation_id,
                    workspace_id=workspace_id,
                    recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
                    entity_type=RecommendationEntityType.SEARCH_TERM,
                    status=RecommendationStatus.PENDING_APPROVAL,
                    priority=RecommendationPriority.HIGH,
                    confidence=RecommendationConfidence.HIGH,
                    rule_version_id="test",
                    rule_name="zero_order_spend_rule",
                    campaign_name="Campaign",
                    ad_group_name="Ad group",
                    targeting="keyword",
                    customer_search_term="wasted term",
                    input_metrics_json={"spend": "12.50", "clicks": 5, "orders": 0},
                    current_metric_snapshot_json={"spend": "12.50", "clicks": 5, "orders": 0},
                    evidence_json={"decision_source": "fallback_rules"},
                    proposed_action_json={
                        "requires_human_approval": True,
                        "executes_live_amazon_change": False,
                    },
                    explanation_json={"summary": "Review wasted spend."},
                    created_at=now,
                    updated_at=now,
                )
            ]
        )

        updated, decision = repository.decide_recommendation(
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            decision=RecommendationStatus.APPROVED,
            actor_user_id="00000000-0000-0000-0000-000000000001",
            note="Approved for manual export review",
        )

        with engine.begin() as connection:
            stored_created_at = connection.execute(
                text("select created_at from recommendation_decisions where recommendation_id = :recommendation_id"),
                {"recommendation_id": recommendation_id},
            ).scalar_one()

        assert updated is not None
        assert updated.status == RecommendationStatus.APPROVED
        assert decision is not None
        assert decision.created_at is not None
        assert stored_created_at
    finally:
        get_database_engine.cache_clear()
        get_settings.cache_clear()
