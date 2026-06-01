"""AdSurf Agent Eval Harness — Golden-set regression testing for AI agent outputs.

Usage:
    python tests/eval_harness.py --mode deterministic
    python tests/eval_harness.py --mode ci --regression-threshold 0.05
"""

from __future__ import annotations

import json, os, sys
from dataclasses import dataclass, field
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class EvalResult:
    test_name: str
    passed: bool
    deterministic_passed: bool = True
    ai_passed: bool | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actual_count: int = 0
    actual_types: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    mode: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[EvalResult] = field(default_factory=list)
    overall_pass_rate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_ci_report(self) -> str:
        lines = [
            f"AdSurf Eval Report -- {self.mode} mode",
            f"Timestamp: {self.timestamp}",
            f"Passed: {self.passed}/{self.total_tests} ({self.overall_pass_rate:.1%})",
            f"Failed: {self.failed}  Skipped: {self.skipped}", "",
        ]
        if self.failed > 0:
            lines.append("FAILURES:")
            for r in self.results:
                if not r.passed:
                    lines.append(f"  FAIL {r.test_name}:")
                    for err in r.errors:
                        lines.append(f"    - {err}")
        else:
            lines.append("All tests passed.")
        return "\n".join(lines)


# Golden Test Set — target_acos is a FRACTION (0.0–1.0 per schema)
GOLDEN_TEST_SET: list[dict[str, Any]] = [
    {
        "name": "empty_report_handling",
        "description": "Empty report should produce zero recommendations, not error.",
        "report_rows": [],
        "product_config": {"target_acos": 0.25, "default_bid": 0.50, "default_budget": 50.0, "marketplace": "US"},
        "strategy_mode": "profit",
        "expected": {"min_recommendations": 0, "max_recommendations": 0,
                     "forbidden_recommendation_types": [], "approval_required": True},
    },
    {
        "name": "high_spend_no_orders_should_flag_negative",
        "description": "$50+ spend, 0 orders, 30+ clicks => negative keyword",
        "report_rows": [{"campaign_name": "Sponsored Products - Broad", "ad_group_name": "Main Ad Group",
                          "targeting": "broad", "customer_search_term": "cheap widget alternative",
                          "match_type": "broad", "impressions": 5000, "clicks": 35, "spend": 52.50,
                          "sales": 0.0, "orders": 0, "acos": 0.0, "roas": 0.0, "cpc": 1.50, "ctr": 0.70, "cvr": 0.0}],
        "product_config": {"target_acos": 0.25, "default_bid": 0.50, "default_budget": 100.0, "marketplace": "US"},
        "strategy_mode": "profit",
        "expected": {"min_recommendations": 1, "max_recommendations": 5,
                     "forbidden_recommendation_types": ["increase_bid"], "approval_required": True},
    },
    {
        "name": "converting_term_should_not_get_negative",
        "description": "Term with orders should NEVER get negative keyword.",
        "report_rows": [{"campaign_name": "Sponsored Products - Broad", "ad_group_name": "Main Ad Group",
                          "targeting": "broad", "customer_search_term": "premium red widget",
                          "match_type": "broad", "impressions": 2000, "clicks": 25, "spend": 37.50,
                          "sales": 150.00, "orders": 3, "acos": 25.0, "roas": 4.0, "cpc": 1.50, "ctr": 1.25, "cvr": 12.0}],
        "product_config": {"target_acos": 0.25, "default_bid": 0.50, "default_budget": 100.0, "marketplace": "US"},
        "strategy_mode": "profit",
        "expected": {"min_recommendations": 0, "max_recommendations": 3,
                     "forbidden_recommendation_types": ["add_negative_exact", "add_negative_phrase", "pause_keyword", "pause_review"],
                     "approval_required": True},
    },
    {
        "name": "all_recommendations_require_approval",
        "description": "Every recommendation must have requires_human_approval=True.",
        "report_rows": [
            {"campaign_name": "Sponsored Products - Broad", "ad_group_name": "Test", "targeting": "broad",
             "customer_search_term": "test term A", "match_type": "broad", "impressions": 500, "clicks": 20,
             "spend": 30.00, "sales": 10.00, "orders": 1, "acos": 300.0, "roas": 0.33, "cpc": 1.50, "ctr": 4.0, "cvr": 5.0},
            {"campaign_name": "Sponsored Products - Broad", "ad_group_name": "Test", "targeting": "broad",
             "customer_search_term": "test term B", "match_type": "broad", "impressions": 2000, "clicks": 80,
             "spend": 40.00, "sales": 200.00, "orders": 4, "acos": 20.0, "roas": 5.0, "cpc": 0.50, "ctr": 4.0, "cvr": 5.0},
        ],
        "product_config": {"target_acos": 0.25, "default_bid": 0.50, "default_budget": 100.0, "marketplace": "US"},
        "strategy_mode": "profit",
        "expected": {"min_recommendations": 1, "max_recommendations": 10,
                     "forbidden_recommendation_types": [], "approval_required": True},
    },
]


def _build_product(pc: dict) -> Any:
    from apps.api.app.schemas.product_profiles import ProductProfile
    now = datetime.now(UTC)
    return ProductProfile(
        id=uuid4(), workspace_id=uuid4(), product_name="Eval Product",
        marketplace=pc.get("marketplace", "US"), currency="USD",
        target_acos=Decimal(str(pc["target_acos"])),
        default_bid=Decimal(str(pc["default_bid"])),
        default_budget=Decimal(str(pc["default_budget"])),
        created_at=now, updated_at=now,
    )


def _build_import(product: Any) -> Any:
    from apps.api.app.schemas.monitoring import MonitoringImport, MonitoringImportStatus
    now = datetime.now(UTC)
    return MonitoringImport(
        id=uuid4(), workspace_id=product.workspace_id, product_id=product.id,
        upload_id=uuid4(), parse_run_id=uuid4(), report_type="search_term",
        date_range_start="2026-01-01", date_range_end="2026-01-31",
        status=MonitoringImportStatus.SUCCEEDED, created_by="eval_harness",
        created_at=now, updated_at=now,
    )


def _build_snapshots(product: Any, import_record: Any, rows: list) -> list:
    from apps.api.app.schemas.monitoring import MonitoringSnapshot
    now = datetime.now(UTC)
    snapshots = []
    for row in rows:
        snapshots.append(MonitoringSnapshot(
            id=uuid4(), workspace_id=product.workspace_id, product_id=product.id,
            monitoring_import_id=import_record.id,
            upload_id=import_record.upload_id, parse_run_id=import_record.parse_run_id,
            source_row_id=uuid4(),
            campaign_name=row.get("campaign_name", ""), ad_group_name=row.get("ad_group_name", ""),
            targeting=row.get("targeting", ""), customer_search_term=row.get("customer_search_term", ""),
            match_type=row.get("match_type", "broad"),
            impressions=row.get("impressions", 0), clicks=row.get("clicks", 0),
            spend=Decimal(str(row.get("spend", 0))), sales=Decimal(str(row.get("sales", 0))),
            orders=row.get("orders", 0),
            cpc=Decimal(str(row.get("cpc", 0))) if row.get("cpc") else None,
            ctr=Decimal(str(row.get("ctr", 0))) if row.get("ctr") else None,
            cvr=Decimal(str(row.get("cvr", 0))) if row.get("cvr") else None,
            acos=Decimal(str(row.get("acos", 0))) if row.get("acos") else None,
            roas=Decimal(str(row.get("roas", 0))) if row.get("roas") else None,
            start_date="2026-01-01", end_date="2026-01-31",
            created_at=now,
        ))
    return snapshots


def run_deterministic_eval(test_set: list[dict[str, Any]] | None = None) -> EvalReport:
    from apps.api.app.services.monitoring_rules import build_recommendations
    from apps.api.app.services.risk_validator import validate_bulk_recommendations

    test_set = test_set or GOLDEN_TEST_SET
    report = EvalReport(mode="deterministic")

    for tc in test_set:
        result = EvalResult(test_name=tc["name"], passed=True)
        report.total_tests += 1
        try:
            product = _build_product(tc["product_config"])
            import_record = _build_import(product)
            snapshots = _build_snapshots(product, import_record, tc["report_rows"])

            recs = build_recommendations(product=product, import_record=import_record, snapshots=snapshots)
            validation = validate_bulk_recommendations(recs, strategy_mode=tc.get("strategy_mode", "profit"))
            recs = validation["valid"]
            result.actual_count = len(recs)
            result.actual_types = sorted(set(r.recommendation_type.value for r in recs))
            expected = tc["expected"]

            # Count checks
            if expected.get("min_recommendations", 0) > 0 and len(recs) < expected["min_recommendations"]:
                result.errors.append(f"Expected >= {expected['min_recommendations']} recs, got {len(recs)}")
                result.passed = False
            if "max_recommendations" in expected and len(recs) > expected["max_recommendations"]:
                result.errors.append(f"Expected <= {expected['max_recommendations']} recs, got {len(recs)}")
                result.passed = False

            # Forbidden types
            forbidden = set(expected.get("forbidden_recommendation_types", []))
            for rec in recs:
                if rec.recommendation_type.value in forbidden:
                    result.errors.append(f"Forbidden type: {rec.recommendation_type.value}")
                    result.passed = False

            # Approval boundary
            if expected.get("approval_required", True):
                for rec in recs:
                    action = rec.proposed_action_json or {}
                    if action.get("requires_human_approval") is not True:
                        result.errors.append("Missing requires_human_approval=True")
                        result.passed = False
                    if action.get("executes_live_amazon_change") is not False:
                        result.errors.append("executes_live_amazon_change != False!")
                        result.passed = False
        except Exception as exc:
            result.errors.append(f"Exception: {exc}")
            result.passed = False

        if result.passed:
            report.passed += 1
        else:
            report.failed += 1
        report.results.append(result)

    report.overall_pass_rate = report.passed / max(report.total_tests, 1)
    return report


def run_ci(regression_threshold: float = 0.05) -> int:
    print("AdSurf Agent Eval Harness -- CI Mode")
    print("Running deterministic regression tests...")
    report = run_deterministic_eval()
    print(report.to_ci_report())

    if report.failed > 0:
        print(f"FAIL: {report.failed} regressions detected.")
        return 1

    fail_rate = report.failed / max(report.total_tests, 1)
    if fail_rate > regression_threshold:
        print(f"Regression rate {fail_rate:.1%} > threshold {regression_threshold:.1%}")
        return 1

    print("All evals passed.")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AdSurf Agent Eval Harness")
    parser.add_argument("--mode", choices=["deterministic", "ci"], default="deterministic")
    parser.add_argument("--regression-threshold", type=float, default=0.05)
    args = parser.parse_args()

    if args.mode == "ci":
        sys.exit(run_ci(args.regression_threshold))
    else:
        report = run_deterministic_eval()
        print(report.to_ci_report())
        sys.exit(0 if report.failed == 0 else 1)