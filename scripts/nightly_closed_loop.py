"""Nightly Closed-Loop Calibration Job for AdSurf.

Process: learning_feedback.analyze_outcomes() → rule_calibration.calibrate_rules_from_feedback() → persist

Usage:
    python scripts/nightly_closed_loop.py
    python scripts/nightly_closed_loop.py --workspace-id <uuid> --dry-run
"""

from __future__ import annotations

import json, sys
from argparse import ArgumentParser
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_nightly_closed_loop(
    *,
    workspace_id: UUID | None = None,
    min_observations: int = 5,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the nightly closed-loop calibration across all workspaces."""
    from apps.api.app.services.rule_calibration import calibrate_rules_from_feedback

    job_id = uuid4()
    started_at = datetime.now(UTC)
    result: dict[str, Any] = {
        "job_id": str(job_id), "started_at": started_at.isoformat(),
        "workspaces_processed": 0, "parameters_adjusted": 0,
        "parameters_unchanged": 0, "parameters_skipped": 0,
        "calibrations": [], "errors": [], "dry_run": dry_run,
    }

    # In production: iterate workspaces, load 14-day-old recommendations,
    # run analyze_outcomes, feed to calibrate_rules_from_feedback, persist.
    # Stub: demonstrate the calibration pipeline.
    feedback_stub = {
        "analysis_timestamp": datetime.now(UTC).isoformat(),
        "total_recommendations": 0, "total_evaluated": 0,
        "outcome_distribution": {}, "improvement_rate": 0.0,
        "deterioration_rate": 0.0, "results": [],
        "rule_effectiveness": {}, "summary": "No data available.",
        "next_cycle_suggestions": [],
    }

    ws_id = workspace_id or uuid4()
    calibration = calibrate_rules_from_feedback(
        workspace_id=ws_id, feedback_results=feedback_stub,
        min_observations=min_observations,
    )

    result["workspaces_processed"] = 1
    result["parameters_adjusted"] = calibration.parameters_adjusted
    result["parameters_unchanged"] = calibration.parameters_unchanged
    result["parameters_skipped"] = calibration.parameters_skipped
    result["calibrations"].append({
        "workspace_id": calibration.workspace_id,
        "parameters_adjusted": calibration.parameters_adjusted,
        "summary": calibration.summary,
    })
    result["completed_at"] = datetime.now(UTC).isoformat()
    return result


if __name__ == "__main__":
    parser = ArgumentParser(description="AdSurf Nightly Closed-Loop Calibration")
    parser.add_argument("--workspace-id", type=str, default=None)
    parser.add_argument("--min-observations", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ws_uuid = UUID(args.workspace_id) if args.workspace_id else None
    results = run_nightly_closed_loop(
        workspace_id=ws_uuid, min_observations=args.min_observations,
        dry_run=args.dry_run,
    )

    print(json.dumps(results, indent=2, default=str) if args.json else
          f"Nightly closed-loop complete: {results['parameters_adjusted']} parameters adjusted, "
          f"{results['parameters_unchanged']} unchanged, {results['parameters_skipped']} skipped.")

    sys.exit(1 if results.get("errors") else 0)