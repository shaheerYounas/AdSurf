"""Search Term Mining Agent for AdSurf.

Classifies search terms into actionable categories based on performance
data, match type, and conversion signals. Upgrades the keyword scoring
agent into a proper search term intelligence engine.

Classifications:
- harvest_to_exact: Converting from non-exact, should be isolated
- harvest_to_phrase: Good from broad/auto, promote to phrase
- keep_broad_discovery: Profitable broad discovery term
- add_negative_exact: Wasted clicks, zero orders
- add_negative_phrase: Pattern waste across variation
- watch: Borderline performance, not enough data
- ignore_low_data: Too few data points
- brand_defense: Branded term needing protection
- competitor_term: Competitor brand/ASIN targeting
- research_intent: Informational queries (how, what, best, etc.)
- irrelevant_intent: Clearly irrelevant to product
"""

from decimal import Decimal
from typing import Any

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    RecommendationConfidence,
    RecommendationEntityType,
    RecommendationPriority,
    RecommendationType,
)


RESEARCH_INTENT_PATTERNS = [
    "how ", "what ", "why ", "when ", "where ", "who ",
    "best ", "top ", "review", "vs ", "versus", "compare",
    "guide", "tutorial", "cheap", "affordable", "discount",
    "alternative", "replacement for",
]

IRRELEVANT_PATTERNS = [
    "free ", "jobs", "salary", "used ", "repair", "parts",
    "manual", "warranty", "customer service", "phone number",
]


class SearchTermClassification:
    def __init__(
        self,
        classification: str,
        confidence: str,
        priority: str,
        reason: str,
        recommended_action: str | None = None,
        recommended_match_type: str | None = None,
    ):
        self.classification = classification
        self.confidence = confidence
        self.priority = priority
        self.reason = reason
        self.recommended_action = recommended_action
        self.recommended_match_type = recommended_match_type


def classify_search_term(
    snapshot: MonitoringSnapshot,
    *,
    target_acos: Decimal,
    brand_terms: set[str] | None = None,
    competitor_terms: set[str] | None = None,
    product_keywords: set[str] | None = None,
) -> SearchTermClassification:
    """Classify a search term into one of the defined categories.

    Returns SearchTermClassification with recommended action.
    """
    term = snapshot.customer_search_term.strip().lower()
    match_type = (snapshot.match_type or "").strip().lower()
    orders = snapshot.orders
    clicks = snapshot.clicks
    spend = snapshot.spend
    sales = snapshot.sales
    acos = snapshot.acos
    impressions = snapshot.impressions

    brand_terms = brand_terms or set()
    competitor_terms = competitor_terms or set()
    product_keywords = product_keywords or set()

    # 1. Check intent patterns first
    if _matches_irrelevant_pattern(term):
        return SearchTermClassification(
            classification="irrelevant_intent",
            confidence=RecommendationConfidence.HIGH.value,
            priority=RecommendationPriority.CRITICAL.value,
            reason="Search term appears clearly irrelevant to advertised product.",
            recommended_action="add_negative_exact",
            recommended_match_type="exact",
        )

    if _matches_research_pattern(term) and orders == 0 and clicks >= 10:
        return SearchTermClassification(
            classification="research_intent",
            confidence=RecommendationConfidence.MEDIUM.value,
            priority=RecommendationPriority.LOW.value,
            reason="Search term shows research intent without conversion. Monitor before action.",
            recommended_action="watch_only",
        )

    # 2. Brand terms
    if term in brand_terms or any(brand in term for brand in brand_terms):
        if match_type in {"broad", "auto", "phrase"}:
            return SearchTermClassification(
                classification="brand_defense",
                confidence=RecommendationConfidence.HIGH.value,
                priority=RecommendationPriority.HIGH.value,
                reason="Branded search term should be in an exact match brand campaign for better control.",
                recommended_action="harvest_search_term_to_exact",
                recommended_match_type="exact",
            )
        return SearchTermClassification(
            classification="brand_defense",
            confidence=RecommendationConfidence.HIGH.value,
            priority=RecommendationPriority.MEDIUM.value,
            reason="Branded term tracked. Monitor bid position and competitor conquest.",
            recommended_action="watch_lock",
        )

    # 3. Competitor terms
    if term in competitor_terms or any(comp in term for comp in competitor_terms):
        return SearchTermClassification(
            classification="competitor_term",
            confidence=RecommendationConfidence.MEDIUM.value,
            priority=RecommendationPriority.MEDIUM.value,
            reason="Competitor targeting term. Evaluate ROAS carefully.",
            recommended_action="watch_lock",
        )

    # 4. Low data - not enough to decide
    if clicks < 5 and impressions < 20:
        return SearchTermClassification(
            classification="ignore_low_data",
            confidence=RecommendationConfidence.LOW.value,
            priority=RecommendationPriority.LOW.value,
            reason=f"Only {clicks} clicks and {impressions} impressions. Too little data for meaningful classification.",
            recommended_action="no_action_low_data",
        )

    # 5. Zero order waste
    if orders == 0 and clicks >= 20 and spend >= Decimal("10"):
        if match_type in {"exact", "phrase"}:
            return SearchTermClassification(
                classification="add_negative_exact",
                confidence=RecommendationConfidence.HIGH.value,
                priority=RecommendationPriority.HIGH.value,
                reason=f"No orders from {clicks} clicks and ${spend:.2f} spend. Search term is wasted spend.",
                recommended_action="add_negative_exact",
                recommended_match_type="exact",
            )
        return SearchTermClassification(
            classification="add_negative_phrase",
            confidence=RecommendationConfidence.HIGH.value,
            priority=RecommendationPriority.HIGH.value,
            reason=f"No orders from {clicks} clicks via {match_type} match. Pattern should be negative phrase.",
            recommended_action="add_negative_phrase",
            recommended_match_type="phrase",
        )

    if orders == 0 and clicks >= 10 and spend >= Decimal("5"):
        return SearchTermClassification(
            classification="watch",
            confidence=RecommendationConfidence.MEDIUM.value,
            priority=RecommendationPriority.MEDIUM.value,
            reason=f"No orders yet but {clicks} clicks with ${spend:.2f} spend. Watch another cycle before adding negative.",
            recommended_action="watch_only",
        )

    # 6. Converting from non-exact - harvest opportunity
    if orders >= 2 and match_type in {"broad", "auto", "phrase", "-"}:
        if acos is not None and acos <= target_acos:
            return SearchTermClassification(
                classification="harvest_to_exact",
                confidence=RecommendationConfidence.HIGH.value,
                priority=RecommendationPriority.HIGH.value,
                reason=f"{orders} orders at {acos:.1%} ACOS from {match_type} match. Harvest this term to exact match for better control.",
                recommended_action="harvest_search_term_to_exact",
                recommended_match_type="exact",
            )
        if acos is not None and acos > target_acos * Decimal("1.25"):
            return SearchTermClassification(
                classification="harvest_to_phrase",
                confidence=RecommendationConfidence.MEDIUM.value,
                priority=RecommendationPriority.MEDIUM.value,
                reason=f"Converting but ACOS {acos:.1%} is above target {target_acos:.1%}. Harvest to phrase for controlled testing.",
                recommended_action="harvest_search_term_to_phrase",
                recommended_match_type="phrase",
            )

    # 7. Good exact match performer
    if orders >= 2 and match_type == "exact" and acos is not None and acos <= target_acos:
        return SearchTermClassification(
            classification="keep_broad_discovery",
            confidence=RecommendationConfidence.HIGH.value,
            priority=RecommendationPriority.LOW.value,
            reason=f"Strong exact match performer: {orders} orders at {acos:.1%} ACOS. Consider bid increase for more volume.",
            recommended_action="watch_lock",
        )

    # 8. Converting but high ACOS
    if orders >= 1 and acos is not None and acos > target_acos * Decimal("1.5"):
        return SearchTermClassification(
            classification="watch",
            confidence=RecommendationConfidence.MEDIUM.value,
            priority=RecommendationPriority.MEDIUM.value,
            reason=f"Converting at {acos:.1%} ACOS, well above target {target_acos:.1%}. Consider bid decrease or move to phrase.",
            recommended_action="watch_only",
        )

    # 9. Under-tested but showing promise
    if orders >= 1 and clicks < 10:
        return SearchTermClassification(
            classification="watch",
            confidence=RecommendationConfidence.LOW.value,
            priority=RecommendationPriority.LOW.value,
            reason=f"Early conversion signals with only {clicks} clicks. Continue watching for more data.",
            recommended_action="watch_only",
        )

    # Default: watch
    return SearchTermClassification(
        classification="watch",
        confidence=RecommendationConfidence.LOW.value,
        priority=RecommendationPriority.LOW.value,
        reason=f"Insufficient data for strong classification. Keep monitoring.",
        recommended_action="watch_only",
    )


def mine_search_terms(
    snapshots: list[MonitoringSnapshot],
    *,
    target_acos: Decimal,
    brand_terms: set[str] | None = None,
    competitor_terms: set[str] | None = None,
    product_keywords: set[str] | None = None,
) -> dict[str, Any]:
    """Mine all search terms from snapshots and return classified results.

    Returns a comprehensive analysis with:
    - classifications: list of classified terms
    - summary: counts by classification
    - harvest_candidates: terms to harvest to exact/phrase
    - negative_candidates: terms to add as negatives
    - brand_terms_found: branded terms detected
    - competitor_terms_found: competitor terms detected
    - wasted_spend_total: total wasted spend from zero-order terms
    """
    classifications = []
    for snapshot in snapshots:
        classification = classify_search_term(
            snapshot,
            target_acos=target_acos,
            brand_terms=brand_terms,
            competitor_terms=competitor_terms,
            product_keywords=product_keywords,
        )
        classifications.append({
            "customer_search_term": snapshot.customer_search_term,
            "campaign_name": snapshot.campaign_name,
            "ad_group_name": snapshot.ad_group_name,
            "targeting": snapshot.targeting,
            "match_type": snapshot.match_type,
            "clicks": snapshot.clicks,
            "spend": str(snapshot.spend),
            "orders": snapshot.orders,
            "sales": str(snapshot.sales),
            "acos": str(snapshot.acos) if snapshot.acos else None,
            "classification": classification.classification,
            "confidence": classification.confidence,
            "priority": classification.priority,
            "reason": classification.reason,
            "recommended_action": classification.recommended_action,
            "recommended_match_type": classification.recommended_match_type,
        })

    # Summary counts
    counts: dict[str, int] = {}
    for item in classifications:
        key = item["classification"]
        counts[key] = counts.get(key, 0) + 1

    harvest_candidates = [
        item for item in classifications
        if item["classification"] in {"harvest_to_exact", "harvest_to_phrase", "brand_defense"}
    ]

    negative_candidates = [
        item for item in classifications
        if item["classification"] in {"add_negative_exact", "add_negative_phrase", "irrelevant_intent"}
    ]

    wasted_spend = sum(
        float(item["spend"])
        for item in classifications
        if item["classification"] in {"add_negative_exact", "add_negative_phrase", "irrelevant_intent"}
        and int(item.get("orders", 0)) == 0
    )

    brand_found = [
        item for item in classifications
        if item["classification"] == "brand_defense"
    ]

    competitor_found = [
        item for item in classifications
        if item["classification"] == "competitor_term"
    ]

    return {
        "classifications": classifications,
        "summary": {
            "total_terms": len(classifications),
            "counts": counts,
            "harvest_candidates": len(harvest_candidates),
            "negative_candidates": len(negative_candidates),
            "wasted_spend_total": wasted_spend,
            "brand_terms_found": len(brand_found),
            "competitor_terms_found": len(competitor_found),
        },
        "harvest_candidates": harvest_candidates[:50],
        "negative_candidates": negative_candidates[:50],
        "brand_terms_found": brand_found[:20],
        "competitor_terms_found": competitor_found[:20],
    }


def _matches_research_pattern(term: str) -> bool:
    return any(pattern in term for pattern in RESEARCH_INTENT_PATTERNS)


def _matches_irrelevant_pattern(term: str) -> bool:
    return any(pattern in term for pattern in IRRELEVANT_PATTERNS)