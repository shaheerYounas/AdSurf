from uuid import UUID

from apps.api.app.core.config import get_settings
from apps.api.app.repositories.agent_control import get_agent_control_repository
from apps.api.app.repositories.audit_logs import get_audit_log_repository
from apps.api.app.services.monitoring_worker import MonitoringWorker

from tests.integration.test_keyword_scoring_api import auth_headers, client
from tests.integration.test_monitoring_recommendations_api import _processed_sp_report_upload


def test_agent_registry_and_config_role_protection(monkeypatch, tmp_path) -> None:
    workspace_id, _, _ = _processed_sp_report_upload(monkeypatch, tmp_path)

    registry = client.get(f"/v1/workspaces/{workspace_id}/agents", headers=auth_headers(workspace_id, role="viewer"))
    forbidden = client.patch(
        f"/v1/workspaces/{workspace_id}/agent-configs/ai_recommendation_brain_agent",
        headers=auth_headers(workspace_id, role="viewer"),
        json={"enabled": False, "reason": "Viewer cannot configure agents"},
    )
    updated = client.patch(
        f"/v1/workspaces/{workspace_id}/agent-configs/ai_recommendation_brain_agent",
        headers=auth_headers(workspace_id, role="admin"),
        json={"enabled": False, "strictness_level": "conservative", "confidence_threshold": "high", "reason": "Use fallback only"},
    )

    assert registry.status_code == 200
    agent_ids = {agent["agent_id"] for agent in registry.json()["data"]}
    assert {"performance_import_agent", "metrics_analysis_agent", "ai_recommendation_brain_agent", "stakeholder_reporting_agent"}.issubset(agent_ids)
    assert all(agent["can_mutate_live_amazon_ads"] is False for agent in registry.json()["data"])
    assert forbidden.status_code == 403
    assert updated.status_code == 200
    assert updated.json()["data"]["enabled"] is False

    providers = client.get(f"/v1/workspaces/{workspace_id}/agent-ai-providers", headers=auth_headers(workspace_id, role="viewer"))
    assert providers.status_code == 200
    assert providers.json()["meta"]["secrets_exposed"] is False
    assert {"primary", "deepseek", "fallback", "deterministic"}.issubset({item["provider"] for item in providers.json()["data"]})


def test_disabled_agent_is_skipped_and_workflow_graph_exposes_edges(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)
    client.patch(
        f"/v1/workspaces/{workspace_id}/agent-configs/ai_recommendation_brain_agent",
        headers=auth_headers(workspace_id, role="admin"),
        json={"enabled": False, "reason": "Skip DeepSeek while testing control center"},
    )
    import_response = client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    import_id = import_response.json()["data"]["import_record"]["id"]

    result = MonitoringWorker().process_one()
    workflow = client.get(f"/v1/workspaces/{workspace_id}/monitoring/imports/{import_id}/agent-workflow", headers=auth_headers(workspace_id, role="viewer"))
    runs = client.get(f"/v1/workspaces/{workspace_id}/agent-runs?monitoring_import_id={import_id}", headers=auth_headers(workspace_id, role="viewer"))
    recommendations = client.get(f"/v1/workspaces/{workspace_id}/recommendations", headers=auth_headers(workspace_id, role="viewer")).json()["data"]

    assert result.import_record.status == "succeeded"
    assert workflow.status_code == 200
    nodes = {node["agent_id"]: node for node in workflow.json()["data"]["nodes"]}
    assert nodes["ai_recommendation_brain_agent"]["status"] == "skipped"
    assert len(workflow.json()["data"]["edges"]) >= 7
    assert any("normalized metrics" in edge["data_passed_summary"] for edge in workflow.json()["data"]["edges"])
    assert runs.status_code == 200
    assert all(run["can_mutate_live_amazon_ads"] is False for run in runs.json()["data"])
    assert all(recommendation["evidence_json"]["decision_source"] == "fallback_rules" for recommendation in recommendations)
    events = get_agent_control_repository().list_events(workspace_id=UUID(workspace_id), monitoring_import_id=UUID(import_id))
    assert any(event.event_type == "agent_skipped" and event.agent_id == "ai_recommendation_brain_agent" for event in events)


def test_agent_controls_and_rerun_are_audited(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AI_RECOMMENDATION_MODE", "deterministic_fallback")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()
    workspace_id, product_id, upload_id = _processed_sp_report_upload(monkeypatch, tmp_path)
    client.post(
        f"/v1/workspaces/{workspace_id}/products/{product_id}/monitoring-imports",
        headers=auth_headers(workspace_id, role="analyst"),
        json={"upload_id": upload_id},
    )
    MonitoringWorker().process_one()
    run = client.get(f"/v1/workspaces/{workspace_id}/agent-runs", headers=auth_headers(workspace_id, role="analyst")).json()["data"][0]

    paused = client.post(f"/v1/workspaces/{workspace_id}/agent-runs/{run['id']}/pause", headers=auth_headers(workspace_id, role="analyst"), json={"reason": "Pause for inspection"})
    stopped = client.post(f"/v1/workspaces/{workspace_id}/agent-runs/{run['id']}/stop", headers=auth_headers(workspace_id, role="analyst"), json={"reason": "Stop after inspection"})
    rerun = client.post(f"/v1/workspaces/{workspace_id}/agent-runs/{run['id']}/rerun", headers=auth_headers(workspace_id, role="analyst"), json={"reason": "Rerun for comparison"})
    events = client.get(f"/v1/workspaces/{workspace_id}/agent-runs/{run['id']}/events", headers=auth_headers(workspace_id, role="viewer"))

    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "paused"
    assert stopped.status_code == 200
    assert stopped.json()["data"]["status"] == "stopped"
    assert rerun.status_code == 200
    assert rerun.json()["data"]["id"] != run["id"]
    assert rerun.json()["data"]["status"] == "queued"
    assert events.status_code == 200
    event_types = {event["event_type"] for event in events.json()["data"]}
    assert {"agent_paused", "agent_stopped"}.issubset(event_types)
    audit_repository = get_audit_log_repository()
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="agent.pause") == 1
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="agent.stop") == 1
    assert audit_repository.count(workspace_id=UUID(workspace_id), event_type="agent.rerun") == 1
