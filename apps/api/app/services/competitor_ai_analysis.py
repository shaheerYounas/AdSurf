"""AI-powered competitor insight analysis.

Takes a list of captured SERP results for a keyword and uses the workspace's
configured AI provider (DeepSeek by default) to generate a structured
competitive analysis.

Output is structured JSON that maps directly to competitor_ai_insights table.
"""

from __future__ import annotations

import json
from typing import Any

from apps.api.app.core.config import get_settings


COMPETITOR_ANALYSIS_SYSTEM_PROMPT = """\
You are a professional Amazon Ads analyst specializing in competitive research.
You analyze search engine results page (SERP) data from Amazon and produce
structured competitive insights for an Amazon seller.

Your output must be valid JSON. Do not add markdown fences, commentary, or
explanation text outside the JSON object.

You must be conservative and evidence-based:
- Do not recommend bid increases based on a single data point.
- Do not recommend negative keywords without spend evidence.
- Do not assume a keyword is weak just because there are strong competitors.
- Use the metrics you have; do not hallucinate metrics you don't have.
"""

COMPETITOR_ANALYSIS_USER_TEMPLATE = """\
Analyze the following Amazon SERP data for keyword: "{keyword}"

Total organic results captured: {organic_count}
Total sponsored results captured: {sponsored_count}

Organic results (position, title, price, rating, review_count, badges):
{organic_summary}

Sponsored results (position, title, price, rating, review_count):
{sponsored_summary}

Return a JSON object with exactly these fields:
{{
  "competitor_strength": "Low|Medium|High|Very High",
  "competitor_strength_score": 0-100,
  "sponsored_intensity": "Low|Medium|High",
  "organic_difficulty": "Low|Medium|High",
  "product_market_fit": "Poor|Fair|Good|Excellent",
  "relevance_score": 0-100,
  "risk_score": 0-100,
  "opportunity_score": 0-100,
  "avg_price_range": "e.g. $8.99–$12.99 or N/A",
  "avg_review_count": "e.g. 2,000+ or N/A",
  "avg_price_min_usd": float or null,
  "avg_price_max_usd": float or null,
  "avg_review_count_number": integer or null,
  "recommended_ad_strategy": "one or two sentences",
  "listing_improvement": "one or two sentences about listing quality vs competitors, or null",
  "action_recommendation": "increase_bid|decrease_bid|move_to_exact|keep_running|avoid|watch",
  "full_summary": "3-5 sentence narrative covering competitor landscape, opportunity, and ad strategy recommendation"
}}

Scoring guidance:
- opportunity_score: 80-100 = clear gap in market, 40-79 = moderate opportunity, 0-39 = crowded/difficult
- competitor_strength_score: 80-100 = strong/established, 40-79 = moderate, 0-39 = weak competition
- risk_score: 80-100 = high risk (strong competitors, high spend needed), 0-39 = low risk
- If sponsored intensity is low, that may indicate an opportunity.
- If average review count is very high (5000+), the keyword is likely dominated by established brands.
"""


def _summarise_results(results: list[dict], max_items: int = 8) -> str:
    lines = []
    for r in results[:max_items]:
        parts = [f"#{r.get('position', '?')}"]
        if r.get("title"):
            parts.append(r["title"][:60])
        if r.get("price_text"):
            parts.append(r["price_text"])
        if r.get("rating") is not None:
            parts.append(f"{r['rating']}★")
        if r.get("review_count") is not None:
            parts.append(f"{r['review_count']:,} reviews")
        badges = []
        if r.get("is_best_seller"):
            badges.append("BestSeller")
        if r.get("is_amazon_choice"):
            badges.append("AmazonChoice")
        if r.get("is_prime"):
            badges.append("Prime")
        if badges:
            parts.append("[" + ",".join(badges) + "]")
        lines.append(" | ".join(parts))
    return "\n".join(lines) if lines else "No results captured."


def _call_ai(prompt: str, system: str) -> dict[str, Any]:
    """Call the workspace AI provider and parse the JSON response."""
    settings = get_settings()

    provider = settings.ai_provider or "deepseek"
    base_url = settings.deepseek_base_url or "https://api.deepseek.com"
    api_key = settings.deepseek_api_key or settings.ai_api_key or ""
    model = settings.deepseek_model or "deepseek-chat"

    if not api_key:
        raise RuntimeError("No AI API key configured. Set DEEPSEEK_API_KEY or AI_API_KEY in your environment.")

    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"AI provider returned HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc

    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


class CompetitorAiAnalysisService:
    """
    Generates a competitive insight dict for one keyword given its SERP results.
    Falls back to a deterministic heuristic summary if AI is unavailable.
    """

    def analyse_keyword(
        self,
        *,
        keyword: str,
        organic_results: list[dict],
        sponsored_results: list[dict],
        use_ai: bool = True,
    ) -> dict[str, Any]:
        """
        Returns a dict that maps to competitor_ai_insights table columns.
        """
        if use_ai:
            try:
                return self._ai_analyse(keyword, organic_results, sponsored_results)
            except Exception as exc:
                # Fall back to heuristic if AI fails
                result = self._heuristic_analyse(keyword, organic_results, sponsored_results)
                result["full_summary"] = (
                    f"[AI unavailable: {exc}] {result.get('full_summary', '')}"
                )
                return result
        return self._heuristic_analyse(keyword, organic_results, sponsored_results)

    def _ai_analyse(
        self,
        keyword: str,
        organic_results: list[dict],
        sponsored_results: list[dict],
    ) -> dict[str, Any]:
        settings = get_settings()
        model = settings.deepseek_model or "deepseek-chat"

        prompt = COMPETITOR_ANALYSIS_USER_TEMPLATE.format(
            keyword=keyword,
            organic_count=len(organic_results),
            sponsored_count=len(sponsored_results),
            organic_summary=_summarise_results(organic_results),
            sponsored_summary=_summarise_results(sponsored_results),
        )

        raw = _call_ai(prompt, COMPETITOR_ANALYSIS_SYSTEM_PROMPT)

        # Normalise types
        def _int(v: Any, default: int | None = None) -> int | None:
            try:
                return int(v) if v is not None else default
            except (ValueError, TypeError):
                return default

        def _float(v: Any) -> float | None:
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        return {
            "competitor_strength": raw.get("competitor_strength"),
            "competitor_strength_score": _int(raw.get("competitor_strength_score")),
            "sponsored_intensity": raw.get("sponsored_intensity"),
            "organic_difficulty": raw.get("organic_difficulty"),
            "product_market_fit": raw.get("product_market_fit"),
            "relevance_score": _int(raw.get("relevance_score")),
            "risk_score": _int(raw.get("risk_score")),
            "opportunity_score": _int(raw.get("opportunity_score")),
            "avg_price_range": raw.get("avg_price_range"),
            "avg_review_count": raw.get("avg_review_count"),
            "avg_price_min_usd": _float(raw.get("avg_price_min_usd")),
            "avg_price_max_usd": _float(raw.get("avg_price_max_usd")),
            "avg_review_count_number": _int(raw.get("avg_review_count_number")),
            "recommended_ad_strategy": raw.get("recommended_ad_strategy"),
            "listing_improvement": raw.get("listing_improvement"),
            "action_recommendation": raw.get("action_recommendation"),
            "full_summary": raw.get("full_summary"),
            "ai_model": model,
            "ai_provider": "deepseek",
        }

    @staticmethod
    def _heuristic_analyse(
        keyword: str,
        organic_results: list[dict],
        sponsored_results: list[dict],
    ) -> dict[str, Any]:
        """
        Deterministic fallback analysis using simple heuristics.
        """
        all_results = organic_results + sponsored_results

        # Price stats
        prices = [r["price_usd"] for r in all_results if r.get("price_usd") and r["price_usd"] > 0]
        price_min = min(prices) if prices else None
        price_max = max(prices) if prices else None
        price_range = f"${price_min:.2f}–${price_max:.2f}" if price_min and price_max else "N/A"

        # Review stats
        reviews = [r["review_count"] for r in all_results if r.get("review_count")]
        avg_reviews = int(sum(reviews) / len(reviews)) if reviews else None
        review_str = f"{avg_reviews:,}" if avg_reviews else "N/A"

        # Competitor strength heuristics
        high_review_count = sum(1 for r in reviews if r and r > 1000) if reviews else 0
        strength_score = min(100, int((high_review_count / max(len(all_results), 1)) * 100 + 20))
        strength_label = "High" if strength_score >= 65 else "Medium" if strength_score >= 35 else "Low"

        # Sponsored intensity
        sponsored_ratio = len(sponsored_results) / max(len(all_results), 1)
        sponsored_label = "High" if sponsored_ratio > 0.5 else "Medium" if sponsored_ratio > 0.25 else "Low"

        # Opportunity: inverse of strength + low sponsored
        opportunity = max(0, min(100, 100 - strength_score + (20 if sponsored_ratio < 0.3 else 0)))

        action = (
            "increase_bid" if opportunity >= 60 and strength_score < 50
            else "watch" if opportunity >= 40
            else "keep_running"
        )

        summary = (
            f"Keyword '{keyword}': {len(organic_results)} organic, {len(sponsored_results)} sponsored results. "
            f"Competitor strength is {strength_label} with average {review_str} reviews. "
            f"Price range visible: {price_range}. "
            f"Opportunity score: {opportunity}/100. "
            f"Recommended action: {action}."
        )

        return {
            "competitor_strength": strength_label,
            "competitor_strength_score": strength_score,
            "sponsored_intensity": sponsored_label,
            "organic_difficulty": strength_label,
            "product_market_fit": "Fair",
            "relevance_score": 50,
            "risk_score": strength_score,
            "opportunity_score": opportunity,
            "avg_price_range": price_range,
            "avg_review_count": review_str,
            "avg_price_min_usd": price_min,
            "avg_price_max_usd": price_max,
            "avg_review_count_number": avg_reviews,
            "recommended_ad_strategy": f"Monitor carefully. Competitor strength is {strength_label}.",
            "listing_improvement": None,
            "action_recommendation": action,
            "full_summary": summary,
            "ai_model": None,
            "ai_provider": "heuristic",
        }
