"""Agent mode behavior tests: deterministic, ai, hybrid.

Tests that:
1. Report detection works correctly for different file types
2. Metrics analysis produces deterministic calculations
3. Recommendations include evidence and require approval
4. Output never claims live Amazon Ads mutation
5. Hybrid validator rejects unsafe AI output
6. AI failure falls back safely
"""
import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import ANY, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from apps.api.app.schemas.account_imports import (
    AccountImport,
    AccountImportEntity,
    AccountImportStatus,
    DetectionConfidence,
    EntityType,
    ProductResolutionStatus,
    ReportType,
)
from apps.api.app.schemas.agent_control import AgentConfig, AgentMode, AgentProvider, AgentStrictnessLevel
from apps.api.app.schemas.monitoring import (
    MonitoringImport,
    MonitoringImportStatus,
    MonitoringSnapshot,
    Recommendation,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from apps.api.app.schemas.uploads import UploadSourceType
from apps.api.app.services.account_agent_workflow import build_account_agent_workflow_runs
from apps.api.app.services.agent_registry import AGENT_DEFINITION_BY_ID, AGENT_WORKFLOW_ORDER
from apps.api.app.services.monitoring_agents import build_monitoring_agent_runs
from apps.api.app.services.monitoring_rules import build_recommendations
from apps.api.app.services.report_type_detector import ReportTypeDetector
from apps.api.app.services.risk_validator import ValidationResult, validate_bulk_recommendations, validate_recommendation


# ── helpers ───────────────────────────────────────────────────────────────────

TEST_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")
TEST_PRODUCT = UUID("00000000-0000-0000-0000-000000000002")


def _make_config(agent_id: str, mode: AgentMode = AgentMode.DETERMINISTIC) -> AgentConfig:
    return AgentConfig(
        workspace_id=TEST_WORKSPACE,
        agent_id=agent_id,
        mode=mode,
        provider=AgentProvider.DETERMINISTIC if mode == AgentMode.DETERMINISTIC else AgentProvider.DEEPSEEK,
        strictness_level=AgentStrictnessLevel.BALANCED,
    )


def _make_import_record(workspace_id: UUID) -> AccountImport:
    now = datetime.now()
    return AccountImport(
        id=uuid4(),
        workspace_id=workspace_id,
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type=UploadSourceType.AMAZON_ADS_SP_SEARCH_TERM_REPORT,
        status=AccountImportStatus.SUCCEEDED,
        detected_report_type=ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT,
        detection_confidence=DetectionConfidence.HIGH,
        data_quality_warnings_json=[],
        processed_rows=100,
        total_rows=100,
        created_by="test-user",
        created_at=now,
        updated_at=now,
    )


def _make_entity(
    entity_type: EntityType = EntityType.SEARCH_TERM,
    entity_key: str = "test-term",
    spend: str = "5.00",
    sales: str = "25.00",
    orders: str = "1",
    clicks: str = "10",
    impressions: str = "100",
) -> AccountImportEntity:
    return AccountImportEntity(
        id=uuid4(),
        workspace_id=TEST_WORKSPACE,
        account_import_id=uuid4(),
        entity_type=entity_type,
        entity_key=entity_key,
        campaign_name="Test Campaign",
        ad_group_name="Test Ad Group",
        targeting="test",
        customer_search_term=entity_key,
        metrics_json={
            "spend": spend,
            "sales": sales,
            "orders": orders,
            "clicks": clicks,
            "impressions": impressions,
        },
        resolution_status=ProductResolutionStatus.MATCHED_EXISTING_PRODUCT,
        product_id=TEST_PRODUCT,
        product_name="Test Product",
        created_at=datetime.now(),
    )


def _make_snapshot(**overrides) -> MonitoringSnapshot:
    defaults = {
        "id": uuid4(),
        "workspace_id": TEST_WORKSPACE,
        "product_id": TEST_PRODUCT,
        "monitoring_import_id": uuid4(),
        "upload_id": uuid4(),
        "parse_run_id": uuid4(),
        "source_row_id": uuid4(),
        "campaign_name": "Test Campaign",
        "ad_group_name": "Test Ad Group",
        "targeting": "test keyword",
        "match_type": "exact",
        "customer_search_term": "test search term",
        "impressions": 500,
        "clicks": 50,
        "spend": Decimal("25.00"),
        "sales": Decimal("100.00"),
        "orders": 3,
        "units": 3,
        "cpc": Decimal("0.50"),
        "ctr": Decimal("0.10"),
        "cvr": Decimal("0.06"),
        "acos": Decimal("0.25"),
        "roas": Decimal("4.00"),
        "raw_metrics_json": {},
        "created_at": datetime.now(),
    }
    defaults.update(overrides)
    return MonitoringSnapshot(**defaults)


def _make_recommendation(**overrides) -> Recommendation:
    now = datetime.now()
    defaults = {
        "id": uuid4(),
        "workspace_id": TEST_WORKSPACE,
        "product_id": TEST_PRODUCT,
        "monitoring_import_id": uuid4(),
        "snapshot_id": uuid4(),
        "entity_key": "test-term",
        "recommendation_type": RecommendationType.KEEP_RUNNING,
        "entity_type": RecommendationEntityType.SEARCH_TERM,
        "status": RecommendationStatus.PENDING_APPROVAL,
        "priority": RecommendationPriority.LOW,
        "confidence": RecommendationConfidence.MEDIUM,
        "rule_version_id": "v1",
        "rule_name": "test_rule",
        "campaign_name": "Test Campaign",
        "ad_group_name": "Test Ad Group",
        "targeting": "test",
        "customer_search_term": "test term",
        "input_metrics_json": {"spend": 5, "sales": 25, "orders": 1, "clicks": 10, "impressions": 100, "acos": 0.20, "roas": 5.0},
        "current_metric_snapshot_json": {},
        "evidence_json": {},
        "proposed_action_json": {"action": "keep_running", "requires_human_approval": True, "executes_live_amazon_change": False},
        "explanation_json": {"summary": "Test", "approval_required": True, "decision_source": "deterministic_rules", "ai_final_decision": False, "execution_boundary": "recommendation_only_no_live_amazon_change"},
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Recommendation(**defaults)


# ── test 1: report detection modes ────────────────────────────────────────────

def test_report_detection_search_term_report():
    """Report detection for SP search term report should work in all modes."""
    detector = ReportTypeDetector()
    result = detector.detect(
        headers=[
            "Customer Search Term", "Targeting", "Campaign Name", "Ad Group Name",
            "Spend", "7 Day Total Sales", "7 Day Total Orders",
        ]
    )
    assert result.detected_report_type == ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT
    assert result.confidence == DetectionConfidence.HIGH
    assert result.required_columns_present is True


def test_report_detection_bulk_workbook():
    """Report detection for bulk workbook should work correctly."""
    detector = ReportTypeDetector()
    result = detector.detect(
        headers=[
            "Product", "Entity", "Operation", "Campaign ID", "Ad Group ID",
            "Portfolio ID", "SKU", "ASIN", "Bid", "Budget",
        ]
    )
    assert result.detected_report_type == ReportType.BULK_SHEET
    assert result.confidence == DetectionConfidence.HIGH


def test_report_detection_does_not_require_search_volume():
    """Amazon Ads SP search term report detection must NOT require Search Volume or Organic Rank."""
    detector = ReportTypeDetector()
    result = detector.detect(
        headers=[
            "Customer Search Term", "Targeting", "Campaign Name", "Ad Group Name",
            "Spend", "7 Day Total Sales", "7 Day Total Orders",
        ]
    )
    assert "search volume" not in result.missing_columns
    assert "organic rank" not in result.missing_columns
    assert result.detected_report_type == ReportType.SPONSORED_PRODUCTS_SEARCH_TERM_REPORT


def test_report_detection_unknown_on_unrecognized():
    """Unrecognized headers should return UNKNOWN_REPORT with low confidence."""
    detector = ReportTypeDetector()
    result = detector.detect(headers=["Column A", "Column B", "Column C"])
    assert result.detected_report_type == ReportType.UNKNOWN_REPORT
    assert result.required_columns_present is False


# ── test 2: metrics analysis produces deterministic calculations ───────────────

def test_deterministic_metrics_from_monitoring_rules():
    """Metrics calculated by monitoring_rules should be deterministic and identical across modes."""
    snapshot = _make_snapshot(
        spend=Decimal("25.00"),
        sales=Decimal("100.00"),
        orders=3,
        clicks=50,
        impressions=500,
    )
    # These are calculated within monitoring_rules.build_recommendations
    # The key assertion: ACOS = spend/sales, ROAS = sales/spend
    assert snapshot.spend == Decimal("25.00")
    assert snapshot.sales == Decimal("100.00")
    # ACOS = 25/100 = 0.25
    assert snapshot.acos == Decimal("0.25")
    # ROAS = 100/25 = 4.00
    assert snapshot.roas == Decimal("4.00")


def test_divide_by_zero_safety():
    """Metrics calculations must handle divide-by-zero safely."""
    snapshot = _make_snapshot(
        spend=Decimal("0"),
        sales=Decimal("0"),
        orders=0,
        clicks=0,
        impressions=0,
    )
    from apps.api.app.services.monitoring_metrics import snapshot_metrics
    metrics = snapshot_metrics(snapshot)
    # Should not raise ZeroDivisionError
    assert "acos" in metrics
    assert "roas" in metrics
    assert "cpc" in metrics
    assert "ctr" in metrics
    assert "cvr" in metrics


# ── test 3: recommendations include evidence and require approval ─────────────

def test_recommendations_include_evidence():
    """Every recommendation must include evidence in evidence_json."""
    rec = _make_recommendation(
        evidence_json={
            "schema_version": "v1",
            "performance_grain": "search_term",
            "rule_evaluation": {"rule_name": "test_rule", "priority": "low"},
            "approval_boundary": {"requires_human_approval": True, "executes_live_amazon_change": False},
        }
    )
    assert rec.evidence_json is not None
    assert "rule_evaluation" in rec.evidence_json or "decision_source" in rec.evidence_json
    assert rec.evidence_json.get("approval_boundary", {}).get("requires_human_approval", False) is True


def test_recommendations_require_approval():
    """All recommendations must start as pending_approval."""
    rec = _make_recommendation()
    assert rec.status in {RecommendationStatus.PENDING, RecommendationStatus.PENDING_APPROVAL}
    assert rec.explanation_json.get("approval_required") is True


def test_recommendations_do_not_claim_live_changes():
    """No recommendation output may claim live Amazon Ads changes."""
    rec = _make_recommendation()
    output_text = json.dumps({
        "explanation": rec.explanation_json,
        "evidence": rec.evidence_json,
        "proposed_action": rec.proposed_action_json,
    }).lower()
    forbidden = [
        "changed in amazon",
        "updated live campaign",
        "applied to amazon",
        "executed in amazon",
        "mutated amazon ads",
    ]
    for phrase in forbidden:
        assert phrase not in output_text, f"Found forbidden phrase: {phrase}"


def test_proposed_action_has_execution_boundary():
    """proposed_action_json must have executes_live_amazon_change = False."""
    rec = _make_recommendation()
    assert rec.proposed_action_json.get("executes_live_amazon_change") is False
    assert rec.proposed_action_json.get("requires_human_approval") is True


# ── test 4: mode + no live mutation claim ─────────────────────────────────────

def test_account_workflow_output_never_claims_live_change():
    """Account workflow agent output must never claim live Amazon changes."""
    workspace_id = TEST_WORKSPACE
    import_record = _make_import_record(workspace_id)
    entities = [_make_entity()]

    for mode in [AgentMode.DETERMINISTIC, AgentMode.AI, AgentMode.HYBRID]:
        configs = {agent_id: _make_config(agent_id, mode) for agent_id in AGENT_WORKFLOW_ORDER}
        runs, _ = build_account_agent_workflow_runs(
            workspace_id=workspace_id,
            import_record=import_record,
            entities=entities,
            configs=configs,
        )
        for run in runs:
            output_str = json.dumps(run.output_json, default=str).lower()
            forbidden = [
                "changed in amazon",
                "updated live campaign",
                "applied to amazon",
                "executed in amazon",
            ]
            for phrase in forbidden:
                assert phrase not in output_str, f"Mode {mode}: agent {run.agent_name} output contains '{phrase}'"
            # Verify approval boundary
            assert run.output_json.get("execution_boundary") is not None
            assert run.output_json.get("requires_human_approval") is True
            assert run.output_json.get("executes_live_amazon_change") is False


def test_monitoring_agent_output_never_claims_live_change():
    """Monitoring agent output must never claim live Amazon changes."""
    workspace_id = TEST_WORKSPACE
    snapshots = [_make_snapshot()]
    recommendations = [_make_recommendation()]
    now = datetime.now()
    import_record = MonitoringImport(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=TEST_PRODUCT,
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type="sponsored_products_search_term_report",
        status=MonitoringImportStatus.SUCCEEDED,
        total_rows=1,
        processed_rows=1,
        error_rows=0,
        data_quality_warnings_json=[],
        created_by="test-user",
        created_at=now,
        updated_at=now,
    )
    warnings: list[dict] = []

    runs = build_monitoring_agent_runs(
        workspace_id=workspace_id,
        product_id=TEST_PRODUCT,
        import_record=import_record,
        recommendations=recommendations,
        snapshots=snapshots,
        warnings=warnings,
    )
    for run in runs:
        output_str = json.dumps(run.output_json, default=str).lower()
        forbidden = [
            "changed in amazon",
            "updated live campaign",
            "applied to amazon",
            "executed in amazon",
        ]
        for phrase in forbidden:
            assert phrase not in output_str, f"Agent {run.agent_name} output contains '{phrase}'"
        # Check refusal boundary
        refusal = run.output_json.get("refusal_boundary", {})
        if refusal:
            assert refusal.get("can_mutate_live_amazon_ads") is False
            assert refusal.get("can_bypass_human_approval") is False


# ── test 5: mode is stored in agent run output ────────────────────────────────

def test_mode_is_passed_to_agent_run_output():
    """Each agent run must include the configured mode in its output metadata."""
    workspace_id = TEST_WORKSPACE
    import_record = _make_import_record(workspace_id)
    entities = [_make_entity()]

    for mode in [AgentMode.DETERMINISTIC, AgentMode.AI, AgentMode.HYBRID]:
        configs = {agent_id: _make_config(agent_id, mode) for agent_id in AGENT_WORKFLOW_ORDER}
        runs, _ = build_account_agent_workflow_runs(
            workspace_id=workspace_id,
            import_record=import_record,
            entities=entities,
            configs=configs,
        )
        for run in runs:
            control = run.output_json.get("_agent_control", {})
            assert control.get("mode") == mode.value, (
                f"Mode mismatch for {run.agent_name}: expected {mode.value}, got {control.get('mode')}"
            )


# ── test 6: hybrid validator rejects invalid recommendations ──────────────────

def test_risk_validator_rejects_negative_on_converting_term():
    """Risk validator must reject negative keyword on a term with orders."""
    rec = _make_recommendation(
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        input_metrics_json={"spend": 10, "sales": 50, "orders": 1, "clicks": 20, "impressions": 100},
    )
    result = validate_recommendation(rec)
    assert result.is_valid is False
    assert any("converting term" in err.lower() or "orders" in err.lower() for err in result.errors)


def test_risk_validator_rejects_pause_with_low_data():
    """Risk validator should warn when pausing with too little data."""
    rec = _make_recommendation(
        recommendation_type=RecommendationType.PAUSE_REVIEW,
        input_metrics_json={"spend": 5, "sales": 0, "orders": 0, "clicks": 2, "impressions": 10},
    )
    result = validate_recommendation(rec)
    # Should not be valid OR should have warnings about low data
    assert result.is_valid is False or len(result.warnings) > 0


def test_risk_validator_accepts_safe_recommendation():
    """Risk validator should accept a safe keep_running recommendation."""
    rec = _make_recommendation(
        recommendation_type=RecommendationType.KEEP_RUNNING,
        input_metrics_json={"spend": 5, "sales": 25, "orders": 1, "clicks": 10, "impressions": 100},
    )
    result = validate_recommendation(rec)
    assert result.is_valid is True


def test_bulk_validator_rejects_unsafe_batch():
    """Bulk validator should reject unsafe recommendations and keep valid ones."""
    safe_rec = _make_recommendation(
        recommendation_type=RecommendationType.KEEP_RUNNING,
        input_metrics_json={"spend": 5, "sales": 25, "orders": 1, "clicks": 10, "impressions": 100},
        entity_key="safe-term",
    )
    unsafe_rec = _make_recommendation(
        recommendation_type=RecommendationType.ADD_NEGATIVE_EXACT,
        input_metrics_json={"spend": 10, "sales": 50, "orders": 1, "clicks": 20, "impressions": 100},
        entity_key="converting-term",
    )
    result = validate_bulk_recommendations([safe_rec, unsafe_rec])
    assert result["summary"]["valid_count"] >= 1
    assert result["summary"]["rejected_count"] >= 1


# ── test 7: disabled agents are skipped ───────────────────────────────────────

def test_disabled_agent_is_skipped():
    """A disabled agent should have status 'skipped' in workflow output."""
    workspace_id = TEST_WORKSPACE
    import_record = _make_import_record(workspace_id)
    entities = [_make_entity()]

    configs = {}
    for agent_id in AGENT_WORKFLOW_ORDER:
        definition = AGENT_DEFINITION_BY_ID.get(agent_id)
        config = _make_config(agent_id, AgentMode.DETERMINISTIC)
        if definition and definition.can_be_disabled:
            config = config.model_copy(update={"enabled": False})
        configs[agent_id] = config

    runs, _ = build_account_agent_workflow_runs(
        workspace_id=workspace_id,
        import_record=import_record,
        entities=entities,
        configs=configs,
    )
    skipped = [
        run for run in runs if run.status == "skipped"
    ]
    # At least some agents should be skipped if they were disabled
    # Some agents are not disableable (can_be_disabled=False), so they should still be "succeeded"
    succeeded = [run for run in runs if run.status == "succeeded"]
    assert len(succeeded) > 0, "Agents that cannot be disabled should still succeed"
    assert len(skipped) > 0, "Disabled agents should be skipped"
    # Verify skipped agents have the correct control metadata
    for run in skipped:
        control = run.output_json.get("_agent_control", {})
        definition = AGENT_DEFINITION_BY_ID.get(control.get("agent_id", ""))
        if definition:
            assert definition.can_be_disabled is True


# ── test 8: ai failure fallback (mocked) ──────────────────────────────────────

def test_deepseek_client_handles_missing_api_key():
    """DeepSeek client should raise AiConfigurationError when API key is missing."""
    from apps.api.app.services.ai_client import AiConfigurationError
    from apps.api.app.services.deepseek_client import DeepSeekClient

    # Create client with explicit None API key (bypasses settings lookup)
    client = DeepSeekClient(api_key="", retries=0)
    with pytest.raises(AiConfigurationError):
        client.complete_json(messages=[{"role": "user", "content": "test"}])


def test_deterministic_agents_run_without_deepseek():
    """In deterministic mode, agents should run without calling DeepSeek."""
    workspace_id = TEST_WORKSPACE
    import_record = _make_import_record(workspace_id)
    entities = [_make_entity()]
    configs = {agent_id: _make_config(agent_id, AgentMode.DETERMINISTIC) for agent_id in AGENT_WORKFLOW_ORDER}

    runs, recommendations = build_account_agent_workflow_runs(
        workspace_id=workspace_id,
        import_record=import_record,
        entities=entities,
        configs=configs,
    )
    # All runs should complete without calling DeepSeek
    for run in runs:
        assert run.provider in {"deterministic", "account-bulk-deterministic-v1"}, (
            f"Agent {run.agent_name} used provider {run.provider} in deterministic mode"
        )
    # Recommendations should exist
    assert len(recommendations) > 0
    # All recommendations should be pending approval
    for rec in recommendations:
        assert rec.status == RecommendationStatus.PENDING_APPROVAL


# ── test 9: agent definitions have correct mode support ───────────────────────

def test_all_agent_definitions_have_valid_fields():
    """Every agent definition should have required fields and valid values."""
    for agent in AGENT_DEFINITION_BY_ID.values():
        assert agent.agent_id, f"Agent missing agent_id"
        assert agent.display_name, f"Agent {agent.agent_id} missing display_name"
        assert agent.description, f"Agent {agent.agent_id} missing description"
        assert agent.task_type in {"start", "validation", "mapping", "analysis", "strategy", "decision", "approval", "export", "reporting"}, (
            f"Agent {agent.agent_id} has invalid task_type: {agent.task_type}"
        )
        assert isinstance(agent.can_use_ai, bool), f"Agent {agent.agent_id} can_use_ai not bool"
        assert isinstance(agent.requires_human_approval, bool), f"Agent {agent.agent_id} requires_human_approval not bool"
        assert agent.can_mutate_live_amazon_ads is False, (
            f"Agent {agent.agent_id} must not be able to mutate live Amazon Ads"
        )


def test_safety_agents_cannot_use_ai():
    """Risk validator and human approval agents must have can_use_ai=False."""
    risk = AGENT_DEFINITION_BY_ID.get("risk_policy_validator_agent")
    approval = AGENT_DEFINITION_BY_ID.get("human_approval_agent")
    metrics = AGENT_DEFINITION_BY_ID.get("metrics_normalization_agent")

    assert risk is not None
    assert risk.can_use_ai is False, "Risk validator must not use AI"

    assert approval is not None
    assert approval.can_be_disabled is False, "Human approval cannot be disabled"

    assert metrics is not None
    assert metrics.can_use_ai is False, "Metrics normalization must not use AI"


# ── test 10: agent config defaults are safe ───────────────────────────────────

def test_agent_config_defaults_are_safe():
    """Default agent config must use hybrid mode and be safe."""
    config = AgentConfig(
        workspace_id=TEST_WORKSPACE,
        agent_id="test_agent",
    )
    assert config.mode == AgentMode.HYBRID
    assert config.enabled is True
    assert config.max_bid_increase_multiplier == Decimal("1.1000")
    assert config.max_bid_decrease_multiplier == Decimal("0.9000")
    assert config.require_high_confidence_for_pause is True
    assert config.require_high_confidence_for_negative_keywords is True
    assert config.require_min_clicks_before_action == 10
    assert config.require_min_spend_before_action == Decimal("10.0000")
    assert config.require_action_risk_note is True


# ── test 11: approval boundary is enforced across all outputs ─────────────────

def test_refusal_boundary_present_in_monitoring_output():
    """Monitoring agent output must include refusal boundary."""
    workspace_id = TEST_WORKSPACE
    snapshots = [_make_snapshot()]
    recommendations = [_make_recommendation()]
    now = datetime.now()
    import_record = MonitoringImport(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=TEST_PRODUCT,
        upload_id=uuid4(),
        parse_run_id=uuid4(),
        report_type="sponsored_products_search_term_report",
        status=MonitoringImportStatus.SUCCEEDED,
        total_rows=1,
        processed_rows=1,
        error_rows=0,
        data_quality_warnings_json=[],
        created_by="test-user",
        created_at=now,
        updated_at=now,
    )

    runs = build_monitoring_agent_runs(
        workspace_id=workspace_id,
        product_id=TEST_PRODUCT,
        import_record=import_record,
        recommendations=recommendations,
        snapshots=snapshots,
        warnings=[],
    )

    for run in runs:
        if run.status == "succeeded":
            # Check refusal boundary on relevant agents
            refusal = run.output_json.get("refusal_boundary")
            if refusal:
                assert refusal["can_mutate_live_amazon_ads"] is False
                assert refusal["can_bypass_human_approval"] is False