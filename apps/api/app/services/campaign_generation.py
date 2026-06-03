from decimal import Decimal
import json
import re
from uuid import UUID

from apps.api.app.schemas.campaigns import CampaignKeyword
from apps.api.app.schemas.keyword_review import ApprovedKeywordSetItem
from apps.api.app.schemas.product_profiles import ProductProfile
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet


CAMPAIGN_RULE_VERSION = "campaign_creation_rules_v1"
DEFAULT_DAILY_BUDGET = Decimal("10.0000")
DEFAULT_BID = Decimal("1.0000")
ASIN_PATTERN = re.compile(r"^b[0-9a-z]{9}$", re.IGNORECASE)


def build_campaign_plan_json(*, product: ProductProfile, keyword_set_id: UUID, items: list[ApprovedKeywordSetItem]) -> dict:
    if not items:
        return {"keyword_set_id": str(keyword_set_id), "groups": [], "campaigns": [], "negative_keywords": []}

    sorted_items = sorted(items, key=lambda item: (item.relevance_score, item.search_volume or Decimal("0")), reverse=True)
    hero_item = sorted_items[0]
    remaining_items = sorted_items[1:]
    daily_budget = product.default_budget or DEFAULT_DAILY_BUDGET
    default_bid = product.default_bid or DEFAULT_BID

    hero_keyword = _keyword(hero_item, bid=default_bid)
    groups = [{"group_type": "hero", "group_index": 0, "keywords": [hero_keyword.model_dump(mode="json")]}]
    campaigns = [
        {
            "campaign_name": _campaign_name(product=product, match_type="Exact", keyword_or_group=hero_item.search_term),
            "ad_group_name": _ad_group_name(product=product, group_index=0),
            "match_type": "Exact",
            "daily_budget": str(daily_budget),
            "keywords": [hero_keyword.model_dump(mode="json")],
            "negative_keywords": [],
        }
    ]

    for group_index, batch in enumerate(_keyword_batches(remaining_items), start=1):
        keywords = [_keyword(item, bid=default_bid) for item in batch]
        groups.append({"group_type": "keyword_group", "group_index": group_index, "keywords": [keyword.model_dump(mode="json") for keyword in keywords]})
        for match_type in ("Exact", "Phrase", "Broad"):
            campaigns.append(
                {
                    "campaign_name": _campaign_name(product=product, group_index=group_index, match_type=match_type),
                    "ad_group_name": _ad_group_name(product=product, group_index=group_index),
                    "match_type": match_type,
                    "daily_budget": str(daily_budget),
                    "keywords": [keyword.model_dump(mode="json") for keyword in keywords],
                    "negative_keywords": _negative_keywords(match_type=match_type, keywords=keywords),
                }
            )

    return {
        "rule_version_id": CAMPAIGN_RULE_VERSION,
        "keyword_set_id": str(keyword_set_id),
        "hero_keyword": hero_keyword.model_dump(mode="json"),
        "groups": groups,
        "campaigns": campaigns,
        "safety_summary": _campaign_plan_safety_summary(product=product, campaigns=campaigns, items=items),
        "approval_boundary": {
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
            "amazon_ads_api_mutation": False,
        },
    }


def build_bulk_export_rows(*, plan_json: dict) -> list[dict]:
    rows: list[dict] = []
    for campaign in plan_json.get("campaigns", []):
        campaign_name = campaign["campaign_name"]
        ad_group_name = campaign["ad_group_name"]
        rows.append(
            {
                "Record Type": "Campaign",
                "Campaign Name": campaign_name,
                "Campaign Daily Budget": campaign["daily_budget"],
                "Campaign Status": "Enabled",
                "Ad Group Name": "",
                "Keyword Text": "",
                "Match Type": "",
                "Bid": "",
            }
        )
        rows.append(
            {
                "Record Type": "Ad Group",
                "Campaign Name": campaign_name,
                "Campaign Daily Budget": "",
                "Campaign Status": "",
                "Ad Group Name": ad_group_name,
                "Keyword Text": "",
                "Match Type": "",
                "Bid": "",
            }
        )
        for keyword in campaign["keywords"]:
            rows.append(
                {
                    "Record Type": "Keyword",
                    "Campaign Name": campaign_name,
                    "Campaign Daily Budget": "",
                    "Campaign Status": "",
                    "Ad Group Name": ad_group_name,
                    "Keyword Text": keyword["search_term"],
                    "Match Type": campaign["match_type"],
                    "Bid": keyword["bid"],
                }
            )
        for negative in campaign.get("negative_keywords", []):
            rows.append(
                {
                    "Record Type": "Negative keyword",
                    "Campaign Name": campaign_name,
                    "Campaign Daily Budget": "",
                    "Campaign Status": "",
                    "Ad Group Name": ad_group_name,
                    "Keyword Text": negative["keyword_text"],
                    "Match Type": negative["match_type"],
                    "Bid": "",
                }
            )
    return rows


def render_bulk_export_csv(rows: list[dict]) -> bytes:
    import csv
    import io

    fieldnames = ["Record Type", "Campaign Name", "Campaign Daily Budget", "Campaign Status", "Ad Group Name", "Keyword Text", "Match Type", "Bid"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _keyword(item: ApprovedKeywordSetItem, *, bid: Decimal) -> CampaignKeyword:
    return CampaignKeyword(
        keyword_candidate_id=item.keyword_candidate_id,
        search_term=item.search_term,
        search_volume=item.search_volume,
        relevance_score=item.relevance_score,
        bid=bid,
    )


def _keyword_batches(items: list[ApprovedKeywordSetItem]) -> list[list[ApprovedKeywordSetItem]]:
    if not items:
        return []
    if len(items) <= 7:
        return [items]
    return [items[index : index + 7] for index in range(0, len(items), 7)]


def _negative_keywords(*, match_type: str, keywords: list[CampaignKeyword]) -> list[dict]:
    if match_type == "Phrase":
        return [{"keyword_text": keyword.search_term, "match_type": "Negative Exact", "rule": "phrase_exact_overlap_prevention"} for keyword in keywords]
    if match_type == "Broad":
        return [{"keyword_text": keyword.search_term, "match_type": "Negative Phrase", "rule": "broad_phrase_overlap_prevention"} for keyword in keywords]
    return []


def _campaign_plan_safety_summary(*, product: ProductProfile, campaigns: list[dict], items: list[ApprovedKeywordSetItem]) -> dict:
    total_daily_budget = sum((Decimal(str(campaign["daily_budget"])) for campaign in campaigns), Decimal("0"))
    terms = [item.search_term.strip().lower() for item in items]
    duplicate_terms = sorted({term for term in terms if terms.count(term) > 1})
    asin_like_terms = sorted({item.search_term for item in items if ASIN_PATTERN.match(item.search_term.strip())})
    low_volume_terms = sorted({item.search_term for item in items if item.search_volume is None or item.search_volume <= 0})
    warnings: list[dict] = []
    if asin_like_terms:
        warnings.append(
            {
                "code": "ASIN_TERMS_NEED_PRODUCT_TARGETING_REVIEW",
                "message": "Some approved terms look like ASINs and should be reviewed for product targeting instead of keyword campaigns.",
                "risk_label": "possible_asin_targeting",
                "terms": asin_like_terms,
            }
        )
    if duplicate_terms:
        warnings.append(
            {
                "code": "DUPLICATE_APPROVED_TERMS",
                "message": "Duplicate approved terms can create overlapping campaign traffic.",
                "risk_label": "possible_duplicate",
                "terms": duplicate_terms,
            }
        )
    if low_volume_terms:
        warnings.append(
            {
                "code": "LOW_DATA_APPROVED_TERMS",
                "message": "Some approved terms have no positive search-volume evidence; review before scaling.",
                "risk_label": "not_enough_data",
                "terms": low_volume_terms,
            }
        )
    if total_daily_budget > (product.default_budget or DEFAULT_DAILY_BUDGET) * Decimal("10"):
        warnings.append(
            {
                "code": "TOTAL_DAILY_BUDGET_EXPOSURE",
                "message": "Campaign plan daily budgets add up to a high account exposure; confirm total budget before export.",
                "risk_label": "high_risk",
            }
        )
    return {
        "campaign_count": len(campaigns),
        "total_daily_budget": str(total_daily_budget.quantize(Decimal("0.0001"))),
        "default_campaign_budget": str((product.default_budget or DEFAULT_DAILY_BUDGET).quantize(Decimal("0.0001"))),
        "risk_labels": sorted({warning["risk_label"] for warning in warnings}) or ["safe"],
        "warnings": warnings,
        "requires_budget_confirmation": True,
        "requires_existing_campaign_duplicate_check": True,
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    }


def _campaign_name(*, product: ProductProfile, match_type: str, group_index: int | None = None, keyword_or_group: str | None = None) -> str:
    safe_name = product.product_name.strip().replace(",", " ")
    label = (keyword_or_group or (f"Relevant{group_index}" if group_index is not None else "Relevant1")).strip().replace(",", " ")
    return f"{safe_name} / SP / Manual / {match_type} / {label} / {_date_label()}"


def _ad_group_name(*, product: ProductProfile, group_index: int) -> str:
    safe_name = product.product_name.strip().replace(",", " ")
    return f"{safe_name} - G{group_index}"


def _date_label() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%b %d").replace(" 0", " ")


# =============================================================================
# Dual-Path Campaign Generation: Deterministic + AI
# =============================================================================

CAMPAIGN_GENERATION_AI_AGENT_ID = "campaign_generation_agent"


class DualPathCampaignGeneration(DualPathDecisionService[dict]):
    """Dual-path campaign generation service.

    Deterministic path: build_campaign_plan_json (exact rule-based grouping).
    AI path: LLM reviews keywords and proposes campaign structure.
    Both paths produce the same output schema (campaign plan dict).
    """

    AGENT_ID = CAMPAIGN_GENERATION_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Campaign Generation Agent"

    def _deterministic_path(self, inputs: dict) -> dict:
        """Run deterministic campaign plan generation."""
        return build_campaign_plan_json(
            product=inputs["product"],
            keyword_set_id=inputs["keyword_set_id"],
            items=inputs["items"],
        )

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        product: ProductProfile = inputs["product"]
        items: list[ApprovedKeywordSetItem] = inputs["items"]
        items_for_prompt = [
            {
                "search_term": item.search_term,
                "search_volume": str(item.search_volume) if item.search_volume else None,
                "relevance_score": item.relevance_score,
            }
            for item in items[:100]
        ]

        system = (
            "You are the AdSurf Campaign Generation Agent for Amazon Ads. "
            "Your job is to propose campaign structures from approved keywords. "
            f"{safety_prompt_snippet()}"
            "You propose campaign plans only — they must be reviewed by a human before any bulk sheet export. "
            "Return JSON only. "
            "Every output must include decision_source='ai' and requires_human_approval=true."
        )
        user = {
            "task": "generate_campaign_plan",
            "product": {
                "product_name": product.product_name,
                "default_budget": str(product.default_budget) if product.default_budget else "10.0000",
                "default_bid": str(product.default_bid) if product.default_bid else "1.0000",
            },
            "approved_keywords": items_for_prompt,
            "campaign_rules": {
                "hero_keyword": "top by relevance_score then search_volume",
                "keyword_batch_size": 7,
                "match_types": ["Exact", "Phrase", "Broad"],
                "negative_keywords": "Phrase campaigns get Negative Exact, Broad campaigns get Negative Phrase",
                "campaign_name_format": "{ProductName} / SP / Manual / {MatchType} / {KeywordOrRelevantGroup} / {Mon DD}",
            },
            "required_output_shape": {
                "campaign_plan": {
                    "hero_keyword": {"search_term": "...", "bid": "...", "relevance_score": 0},
                    "groups": [{"group_type": "hero | keyword_group", "group_index": 0, "keywords": [{"search_term": "...", "bid": "..."}]}],
                    "campaigns": [{
                        "campaign_name": "...",
                        "ad_group_name": "...",
                        "match_type": "Exact | Phrase | Broad",
                        "daily_budget": "...",
                        "keywords": [{"search_term": "...", "bid": "..."}],
                        "negative_keywords": [{"keyword_text": "...", "match_type": "Negative Exact | Negative Phrase", "rule": "..."}],
                    }],
                    "decision_source": "ai",
                    "requires_human_approval": True,
                    "executes_live_amazon_change": False,
                }
            },
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)},
        ]

    def _validate_ai_output(self, ai_json: dict, inputs: dict) -> list[str]:
        errors: list[str] = []
        plan = ai_json.get("campaign_plan", {})
        if not plan:
            errors.append("AI output must include campaign_plan.")
        if plan.get("decision_source") != "ai":
            errors.append("campaign_plan.decision_source must be 'ai'.")
        if plan.get("requires_human_approval") is not True:
            errors.append("campaign_plan.requires_human_approval must be true.")
        if plan.get("executes_live_amazon_change") is not False:
            errors.append("campaign_plan.executes_live_amazon_change must be false.")
        if not plan.get("campaigns"):
            errors.append("campaign_plan.campaigns must not be empty.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> dict:
        """Parse AI output into campaign plan dict."""
        plan = ai_json.get("campaign_plan", {})
        return {
            "rule_version_id": CAMPAIGN_RULE_VERSION,
            "keyword_set_id": str(inputs.get("keyword_set_id", "")),
            "hero_keyword": plan.get("hero_keyword", {}),
            "groups": plan.get("groups", []),
            "campaigns": plan.get("campaigns", []),
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }

    def _empty_result(self) -> dict:
        return {"keyword_set_id": "", "groups": [], "campaigns": [], "negative_keywords": []}
