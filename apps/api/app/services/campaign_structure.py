"""Campaign Structure Agent for AdSurf.

Recommends structural changes to campaigns, ad groups, and targeting
based on performance patterns and best practices.

Recommendations include:
- Move converting search term from auto/broad to exact
- Create isolated exact campaign for hero terms
- Separate branded and non-branded campaigns
- Separate competitor targeting
- Separate product targeting from keyword targeting
- Separate launch campaigns from profit campaigns
- Separate high-margin products from low-margin products
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from apps.api.app.schemas.monitoring import (
    MonitoringSnapshot,
    RecommendationType,
)


def analyze_campaign_structure(
    snapshots: list[MonitoringSnapshot],
    *,
    target_acos: Decimal,
    brand_terms: set[str] | None = None,
    competitor_terms: set[str] | None = None,
    high_margin_asins: set[str] | None = None,
    low_margin_asins: set[str] | None = None,
) -> dict[str, Any]:
    """Analyze campaign structure and recommend improvements.

    Returns a comprehensive campaign structure analysis with recommendations.
    """
    brand_terms = brand_terms or set()
    competitor_terms = competitor_terms or set()

    # Group by campaign
    campaigns: dict[str, list[MonitoringSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        campaigns[snapshot.campaign_name].append(snapshot)

    campaign_analysis = {}
    for campaign_name, campaign_snapshots in campaigns.items():
        campaign_analysis[campaign_name] = _analyze_single_campaign(
            campaign_name,
            campaign_snapshots,
            target_acos=target_acos,
            brand_terms=brand_terms,
            competitor_terms=competitor_terms,
        )

    # Cross-campaign analysis
    cross_campaign_recommendations = _cross_campaign_analysis(
        campaign_analysis,
        snapshots=snapshots,
        target_acos=target_acos,
        brand_terms=brand_terms,
        competitor_terms=competitor_terms,
    )

    # Hero term detection
    hero_terms = _detect_hero_terms(snapshots, target_acos=target_acos)

    # Mixed intent detection
    mixed_intent_campaigns = _detect_mixed_intent(campaign_analysis, brand_terms, competitor_terms)

    # Overall structure score
    structure_score = _calculate_structure_score(
        campaign_analysis,
        cross_campaign_recommendations,
        hero_terms,
        mixed_intent_campaigns,
    )

    return {
        "campaigns": campaign_analysis,
        "cross_campaign_recommendations": cross_campaign_recommendations,
        "hero_terms": hero_terms,
        "mixed_intent_campaigns": mixed_intent_campaigns,
        "structure_score": structure_score,
        "summary": _generate_structure_summary(
            campaign_analysis,
            cross_campaign_recommendations,
            hero_terms,
            structure_score,
        ),
    }


def _analyze_single_campaign(
    campaign_name: str,
    snapshots: list[MonitoringSnapshot],
    *,
    target_acos: Decimal,
    brand_terms: set[str],
    competitor_terms: set[str],
) -> dict:
    """Analyze a single campaign for structure issues."""
    total_spend = sum((s.spend for s in snapshots), Decimal("0"))
    total_sales = sum((s.sales for s in snapshots), Decimal("0"))
    total_orders = sum(s.orders for s in snapshots)
    total_clicks = sum(s.clicks for s in snapshots)

    acos = float(total_spend / total_sales) if total_sales > 0 else None
    roas = float(total_sales / total_spend) if total_spend > 0 else None

    match_types = {s.match_type for s in snapshots if s.match_type}
    search_terms = {s.customer_search_term.strip().lower() for s in snapshots}
    targets = {s.targeting.strip().lower() for s in snapshots}

    # Detect issues
    issues = []

    # Mixed match types in one campaign
    if len(match_types) > 2:
        issues.append({
            "type": "mixed_match_types",
            "severity": "medium",
            "detail": f"Campaign contains {len(match_types)} match types: {', '.join(match_types)}. Consider separating by match type.",
        })

    # Brand and non-brand together
    has_brand = any(term in brand_terms or any(b in term for b in brand_terms) for term in search_terms)
    has_non_brand = any(
        term not in brand_terms and not any(b in term for b in brand_terms)
        for term in search_terms
    )
    if has_brand and has_non_brand:
        issues.append({
            "type": "brand_non_brand_mixed",
            "severity": "high",
            "detail": "Branded and non-branded terms mixed in same campaign. Separate for better budget control.",
            "recommendation": "split_campaign",
        })

    # High spend, low performance
    if total_spend >= Decimal("50") and acos is not None and acos > float(target_acos) * 2:
        issues.append({
            "type": "high_spend_poor_performance",
            "severity": "high",
            "detail": f"Campaign spent ${total_spend:.2f} with ACOS {acos:.1%}, well above target {float(target_acos):.1%}.",
            "recommendation": "review_budget_and_bids",
        })

    # Converts but mixed with poor performers
    converting_terms = [s for s in snapshots if s.orders >= 2]
    if converting_terms and len(converting_terms) < len(snapshots) * 0.3:
        issues.append({
            "type": "few_winners_many_losers",
            "severity": "medium",
            "detail": f"Only {len(converting_terms)}/{len(snapshots)} terms converting. Consider harvesting winners to dedicated campaign.",
            "recommendation": "create_exact_campaign",
        })

    return {
        "campaign_name": campaign_name,
        "total_spend": str(total_spend),
        "total_sales": str(total_sales),
        "total_orders": total_orders,
        "total_clicks": total_clicks,
        "acos": acos,
        "roas": roas,
        "match_types": list(match_types),
        "search_term_count": len(search_terms),
        "target_count": len(targets),
        "issues": issues,
        "health": "good" if len(issues) == 0 else "needs_attention" if len(issues) <= 2 else "needs_restructure",
    }


def _cross_campaign_analysis(
    campaign_analysis: dict,
    snapshots: list[MonitoringSnapshot],
    *,
    target_acos: Decimal,
    brand_terms: set[str],
    competitor_terms: set[str],
) -> list[dict]:
    """Analyze across campaigns for structural recommendations."""
    recommendations = []

    # Find campaigns that should be split
    campaign_names = list(campaign_analysis.keys())

    # Duplicate targeting across campaigns
    target_campaign_map: dict[str, set[str]] = defaultdict(set)
    for snapshot in snapshots:
        target_key = snapshot.targeting.strip().lower()
        target_campaign_map[target_key].add(snapshot.campaign_name)

    duplicates = {t: cs for t, cs in target_campaign_map.items() if len(cs) > 1}
    if duplicates:
        recommendations.append({
            "type": "duplicate_targeting",
            "severity": "medium",
            "detail": f"{len(duplicates)} targets appear in multiple campaigns. Consider consolidating or using portfolio approach.",
            "affected_targets": list(duplicates.keys())[:10],
        })

    # Campaigns without clear structure
    for name, analysis in campaign_analysis.items():
        if analysis["search_term_count"] > 50:
            recommendations.append({
                "type": "large_campaign",
                "severity": "low",
                "detail": f"Campaign '{name}' has {analysis['search_term_count']} unique search terms. Consider splitting into more focused campaigns.",
                "campaign": name,
            })

    # Recommend brand campaign if not exists
    has_brand_campaign = any(
        "brand" in name.lower() or "defense" in name.lower()
        for name in campaign_names
    )
    has_brand_terms_in_other = False
    for snapshot in snapshots:
        if "brand" in snapshot.campaign_name.lower() or "defense" in snapshot.campaign_name.lower():
            continue
        search_term_lower = snapshot.customer_search_term.strip().lower()
        if search_term_lower in brand_terms or any(b in search_term_lower for b in brand_terms):
            has_brand_terms_in_other = True
            break
    if not has_brand_campaign and has_brand_terms_in_other:
        recommendations.append({
            "type": "create_brand_campaign",
            "severity": "high",
            "detail": "No dedicated brand campaign detected. Create a brand defense campaign for branded search terms with exact match.",
            "recommendation": "create_exact_campaign",
        })

    return recommendations


def _detect_hero_terms(
    snapshots: list[MonitoringSnapshot],
    *,
    target_acos: Decimal,
) -> list[dict]:
    """Detect hero search terms that deserve their own exact campaign."""
    hero_candidates = [
        s for s in snapshots
        if s.orders >= 3
        and s.sales > Decimal("50")
        and s.acos is not None
        and s.acos <= target_acos * Decimal("0.80")
    ]

    # Sort by sales descending
    hero_candidates.sort(key=lambda s: s.sales, reverse=True)

    return [
        {
            "search_term": s.customer_search_term,
            "campaign": s.campaign_name,
            "ad_group": s.ad_group_name,
            "orders": s.orders,
            "sales": str(s.sales),
            "acos": str(s.acos) if s.acos else None,
            "match_type": s.match_type,
            "recommendation": "Create isolated exact campaign" if s.match_type not in {"exact"} else "Consider bid increase and budget allocation",
        }
        for s in hero_candidates[:10]
    ]


def _detect_mixed_intent(
    campaign_analysis: dict,
    brand_terms: set[str],
    competitor_terms: set[str],
) -> list[dict]:
    """Detect campaigns with mixed intent (brand + competitor + generic)."""
    mixed = []
    for name, analysis in campaign_analysis.items():
        intents_found = set()
        if analysis.get("has_brand"):
            intents_found.add("brand")
        if analysis.get("has_competitor"):
            intents_found.add("competitor")
        if len(intents_found) > 1:
            mixed.append({
                "campaign": name,
                "intents": list(intents_found),
                "recommendation": "Separate into dedicated campaigns by intent",
            })
    return mixed


def _calculate_structure_score(
    campaign_analysis: dict,
    cross_campaign_recommendations: list,
    hero_terms: list,
    mixed_intent_campaigns: list,
) -> dict:
    """Calculate an overall campaign structure health score."""
    score = 100

    # Deduct for issues
    for analysis in campaign_analysis.values():
        issue_count = len(analysis.get("issues", []))
        score -= issue_count * 5

    # Deduct for cross-campaign issues
    score -= len(cross_campaign_recommendations) * 10

    # Deduct for mixed intent
    score -= len(mixed_intent_campaigns) * 8

    # Bonus for hero terms (they're good)
    score += min(len(hero_terms) * 2, 10)

    score = max(0, min(100, score))

    return {
        "overall_score": score,
        "rating": "excellent" if score >= 90 else "good" if score >= 70 else "fair" if score >= 50 else "poor",
        "issue_count": sum(len(a.get("issues", [])) for a in campaign_analysis.values()),
        "cross_campaign_issues": len(cross_campaign_recommendations),
        "hero_terms_count": len(hero_terms),
        "mixed_intent_campaigns": len(mixed_intent_campaigns),
    }


def _generate_structure_summary(
    campaign_analysis: dict,
    cross_campaign_recommendations: list,
    hero_terms: list,
    structure_score: dict,
) -> str:
    """Generate a human-readable structure summary."""
    total_campaigns = len(campaign_analysis)
    needs_restructure = sum(
        1 for a in campaign_analysis.values()
        if a.get("health") == "needs_restructure"
    )

    lines = [
        f"Analyzed {total_campaigns} campaigns.",
        f"Overall structure score: {structure_score['overall_score']}/100 ({structure_score['rating']}).",
    ]

    if hero_terms:
        lines.append(f"Found {len(hero_terms)} hero terms that could benefit from dedicated campaigns.")

    if needs_restructure:
        lines.append(f"{needs_restructure} campaign(s) need structural improvements.")

    if cross_campaign_recommendations:
        lines.append(f"{len(cross_campaign_recommendations)} cross-campaign optimization opportunities detected.")

    if structure_score["overall_score"] < 50:
        lines.append("Priority: Campaign structure needs significant improvement for optimal performance.")
    elif structure_score["overall_score"] < 70:
        lines.append("Priority: Several structural improvements recommended for better budget control.")
    else:
        lines.append("Campaign structure is generally healthy with minor optimization opportunities.")

    return "\n".join(lines)