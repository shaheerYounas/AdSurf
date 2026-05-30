"""Deterministic critic pass.

After the AI brain produces recommendations, we run a rule-based critic over
the top-N highest-impact items to catch decisions that look reasonable in
isolation but conflict with deterministic guardrails (e.g. recommending a
negative on a term with 3 orders, or pausing a campaign with no leading
indicators).

Skipping the LLM-vs-LLM "debate" pattern here is deliberate: a second LLM
call is expensive and rarely better than rules. We reserve LLM escalation for
the small set of items the deterministic critic can't resolve on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    Recommendation,
    RecommendationConfidence,
    RecommendationPriority,
    RecommendationType,
)


_DEFAULT_TOP_N = 25
_HIGH_IMPACT_SPEND = Decimal("25.00")
_DESTRUCTIVE_ACTIONS = {
    RecommendationType.ADD_NEGATIVE_EXACT,
    RecommendationType.ADD_NEGATIVE_PHRASE,
    RecommendationType.PAUSE_REVIEW,
}


@dataclass(frozen=True)
class CriticFinding:
    recommendation_id: str
    severity: str  # "block" | "downgrade" | "warn"
    reason: str
    suggestion: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "severity": self.severity,
            "reason": self.reason,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True)
class CriticResult:
    accepted: list[Recommendation]
    rejected: list[Recommendation]
    findings: list[CriticFinding]

    def to_json(self) -> dict[str, Any]:
        return {
            "accepted_count": len(self.accepted),
            "rejected_count": len(self.rejected),
            "findings": [f.to_json() for f in self.findings],
        }


def critique(
    *,
    recommendations: list[Recommendation],
    snapshots: list[MonitoringSnapshot],
    top_n: int = _DEFAULT_TOP_N,
) -> CriticResult:
    """Review the top-N highest-impact recommendations and apply rule-based
    overrides. Items that fall below the high-impact threshold are passed
    through unchanged.

    Severity semantics:
        - "block":     remove the recommendation entirely.
        - "downgrade": keep the recommendation but lower its priority and
                       confidence so reviewers see it last.
        - "warn":      keep as-is, attach a critic note for the reviewer.
    """

    snap_by_id = {s.id: s for s in snapshots}
    ranked = _rank_by_impact(recommendations, snap_by_id)
    high_impact_ids = {str(rec.id) for rec in ranked[:top_n] if _is_high_impact(rec, snap_by_id)}

    findings: list[CriticFinding] = []
    accepted: list[Recommendation] = []
    rejected: list[Recommendation] = []

    for rec in recommendations:
        if str(rec.id) not in high_impact_ids:
            accepted.append(rec)
            continue

        snapshot = snap_by_id.get(rec.snapshot_id) if rec.snapshot_id else None
        verdicts = _evaluate(rec, snapshot)

        if not verdicts:
            accepted.append(rec)
            continue

        worst = _worst_severity(verdicts)
        findings.extend(verdicts)

        if worst == "block":
            rejected.append(_attach_critic_note(rec, verdicts, status="rejected_by_critic"))
        elif worst == "downgrade":
            accepted.append(_downgrade(rec, verdicts))
        else:
            accepted.append(_attach_critic_note(rec, verdicts, status="critic_warning"))

    return CriticResult(accepted=accepted, rejected=rejected, findings=findings)


def _rank_by_impact(
    recommendations: list[Recommendation],
    snap_by_id: dict,
) -> list[Recommendation]:
    def impact(rec: Recommendation) -> Decimal:
        snap = snap_by_id.get(rec.snapshot_id) if rec.snapshot_id else None
        if snap is None:
            return Decimal("0")
        boost = Decimal("100") if rec.recommendation_type in _DESTRUCTIVE_ACTIONS else Decimal("0")
        return snap.spend + boost

    return sorted(recommendations, key=impact, reverse=True)


def _is_high_impact(rec: Recommendation, snap_by_id: dict) -> bool:
    if rec.recommendation_type in _DESTRUCTIVE_ACTIONS:
        return True
    snap = snap_by_id.get(rec.snapshot_id) if rec.snapshot_id else None
    if snap is None:
        return False
    return snap.spend >= _HIGH_IMPACT_SPEND


def _evaluate(rec: Recommendation, snapshot: MonitoringSnapshot | None) -> list[CriticFinding]:
    findings: list[CriticFinding] = []
    if snapshot is None:
        findings.append(
            CriticFinding(
                recommendation_id=str(rec.id),
                severity="block",
                reason="Critic could not match recommendation to a snapshot in the current import.",
            )
        )
        return findings

    rec_id = str(rec.id)

    if rec.recommendation_type in {
        RecommendationType.ADD_NEGATIVE_EXACT,
        RecommendationType.ADD_NEGATIVE_PHRASE,
    }:
        if snapshot.orders >= 2:
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="block",
                    reason=f"Negative keyword on a term with {snapshot.orders} orders is high-risk.",
                    suggestion="Reconsider as decrease_bid or watch_lock instead of negative.",
                )
            )
        elif snapshot.orders == 1 and snapshot.sales > 0:
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="downgrade",
                    reason="Single-order term proposed for negative — evidence is thin.",
                    suggestion="Consider watch_lock until at least 2-week trend is clear.",
                )
            )
        if snapshot.clicks < 10:
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="block",
                    reason=f"Only {snapshot.clicks} clicks — too little data to classify as waste.",
                )
            )

    if rec.recommendation_type == RecommendationType.PAUSE_REVIEW:
        if snapshot.clicks < 20 and snapshot.spend < Decimal("15"):
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="block",
                    reason="Pause review requires substantial spend or click history.",
                )
            )
        elif snapshot.orders > 0:
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="downgrade",
                    reason="Pause review on a term with order history needs human eyes first.",
                )
            )

    if rec.recommendation_type == RecommendationType.INCREASE_BID:
        if snapshot.orders == 0:
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="block",
                    reason="Cannot increase bid on a term with zero orders.",
                    suggestion="Hold at current bid until conversions appear.",
                )
            )
        elif snapshot.orders == 1:
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="downgrade",
                    reason="Single-order evidence is too thin to justify a bid increase.",
                )
            )

    if rec.recommendation_type == RecommendationType.DECREASE_BID:
        if snapshot.orders >= 3 and snapshot.acos is not None and snapshot.acos < Decimal("0.3"):
            findings.append(
                CriticFinding(
                    recommendation_id=rec_id,
                    severity="downgrade",
                    reason="Decreasing bid on a strong converter risks losing rank.",
                    suggestion="Only a small, controlled decrease — verify rank impact before next round.",
                )
            )

    return findings


def _worst_severity(findings: list[CriticFinding]) -> str:
    severities = {f.severity for f in findings}
    if "block" in severities:
        return "block"
    if "downgrade" in severities:
        return "downgrade"
    return "warn"


def _downgrade(rec: Recommendation, findings: list[CriticFinding]) -> Recommendation:
    return _attach_critic_note(
        rec,
        findings,
        status="critic_downgraded",
        priority=_downgrade_priority(rec.priority),
        confidence=_downgrade_confidence(rec.confidence),
    )


def _attach_critic_note(
    rec: Recommendation,
    findings: list[CriticFinding],
    *,
    status: str,
    priority: RecommendationPriority | None = None,
    confidence: RecommendationConfidence | None = None,
) -> Recommendation:
    explanation = dict(rec.explanation_json)
    explanation["critic_status"] = status
    explanation["critic_findings"] = [f.to_json() for f in findings]
    evidence = dict(rec.evidence_json)
    evidence["critic_findings"] = [f.to_json() for f in findings]
    update: dict[str, Any] = {"evidence_json": evidence, "explanation_json": explanation}
    if priority is not None:
        update["priority"] = priority
    if confidence is not None:
        update["confidence"] = confidence
    return rec.model_copy(update=update)


def _downgrade_priority(priority: RecommendationPriority) -> RecommendationPriority:
    if priority == RecommendationPriority.CRITICAL:
        return RecommendationPriority.HIGH
    if priority == RecommendationPriority.HIGH:
        return RecommendationPriority.MEDIUM
    if priority == RecommendationPriority.MEDIUM:
        return RecommendationPriority.LOW
    return priority


def _downgrade_confidence(confidence: RecommendationConfidence) -> RecommendationConfidence:
    order = [
        RecommendationConfidence.VERY_HIGH,
        RecommendationConfidence.HIGH,
        RecommendationConfidence.MEDIUM,
        RecommendationConfidence.LOW,
        RecommendationConfidence.VERY_LOW,
    ]
    try:
        idx = order.index(confidence)
    except ValueError:
        return confidence
    return order[min(idx + 1, len(order) - 1)]
