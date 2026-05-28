from apps.api.app.orchestration.graph_state import AdsWorkflowState


def route_after_report_detection(state: AdsWorkflowState) -> str:
    if state.get("errors"):
        return "failure"
    if state.get("warnings") and any(warning.get("code") == "REPORT_COLUMNS_MISSING" for warning in state.get("warnings", [])):
        return "human_approval_gate"
    return "product_resolution"


def route_after_ai_brain(state: AdsWorkflowState) -> str:
    if state.get("errors") and not state.get("recommendations"):
        return "failure"
    return "human_approval_gate"
