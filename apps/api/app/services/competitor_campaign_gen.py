"""Campaign generation directly from competitor cleaned rows (items 8-15).

Wires the competitor pipeline into Amazon bulk sheet campaign creation.
Uses the 6-component naming convention: ProductName / SP / Manual / MatchType / Keyword-Group / Date.
"""

from datetime import UTC, datetime
from decimal import Decimal
import json
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow, CompetitorUpload, CampaignGenerationResponse
from apps.api.app.services.dual_path_decision import DualPathDecisionService, safety_prompt_snippet

DEFAULT_DAILY_BUDGET = Decimal("10.0000")
DEFAULT_BID = Decimal("1.0000")
BATCH_SIZE = 7  # Default, overridden by product profile keyword_batch_size


class CompetitorCampaignGenerationService:
    def __init__(self, repository: CompetitorCleanedRepository) -> None:
        self._repository = repository

    def generate_from_verified(
        self,
        *,
        workspace_id: UUID,
        upload_id: UUID,
        product_id: UUID,
        product_name: str = "Product",
        batch_size: int = BATCH_SIZE,
        daily_budget: Decimal = DEFAULT_DAILY_BUDGET,
        default_bid: Decimal = DEFAULT_BID,
    ) -> CampaignGenerationResponse:
        upload = self._repository.get_upload(workspace_id=workspace_id, upload_id=upload_id)
        if upload is None:
            raise ApiError(code="COMPETITOR_UPLOAD_NOT_FOUND", message="Competitor upload was not found.", status_code=404)

        # Load only verified + approved rows
        all_verified: list[CompetitorCleanedRow] = []
        page = 1
        while True:
            rows, total = self._repository.list_rows(
                workspace_id=workspace_id,
                competitor_upload_id=upload_id,
                page=page,
                page_size=1000,
            )
            if not rows:
                break
            verified = [r for r in rows if r.verification_status == "verified" and r.scoring_status == "approved" and r.search_term]
            all_verified.extend(verified)
            if page * 1000 >= total:
                break
            page += 1

        if not all_verified:
            raise ApiError(code="NO_VERIFIED_KEYWORDS", message="No verified and approved keywords found for campaign generation.", status_code=409)

        # Sort by relevance_score desc, then search_volume desc
        all_verified.sort(key=lambda r: (r.relevance_score or 0, r.search_volume or 0), reverse=True)

        # Top 20-50 terms (plan item 11)
        top_terms = all_verified[:50]
        hero_term = top_terms[0]
        remaining = top_terms[1:]

        date_str = _date_label()
        safe_name = product_name.strip().replace(",", " ")

        # Hero campaign (plan item 9)
        hero_campaign_name = _campaign_name(product_name=safe_name, match_type="Exact", keyword_or_group=hero_term.search_term, date_label=date_str)
        hero_ad_group = f"{safe_name} - G0"
        campaigns = [
            {
                "Record Type": "Campaign",
                "Campaign Name": hero_campaign_name,
                "Campaign Daily Budget": str(daily_budget),
                "Campaign Status": "Enabled",
                "Ad Group Name": "",
                "Keyword Text": "",
                "Match Type": "",
                "Bid": "",
            },
            {
                "Record Type": "Ad Group",
                "Campaign Name": hero_campaign_name,
                "Campaign Daily Budget": "",
                "Campaign Status": "",
                "Ad Group Name": hero_ad_group,
                "Keyword Text": "",
                "Match Type": "",
                "Bid": "",
            },
            {
                "Record Type": "Keyword",
                "Campaign Name": hero_campaign_name,
                "Campaign Daily Budget": "",
                "Campaign Status": "",
                "Ad Group Name": hero_ad_group,
                "Keyword Text": hero_term.search_term,
                "Match Type": "Exact",
                "Bid": str(default_bid),
            },
        ]

        # Grouped campaigns (items 12-15)
        batches = self._batch_keywords(remaining, batch_size)
        for group_idx, batch in enumerate(batches, start=1):
            group_label = f"Relevant{group_idx}"
            for match_type in ("Exact", "Phrase", "Broad"):
                campaign_name = _campaign_name(product_name=safe_name, match_type=match_type, keyword_or_group=group_label, date_label=date_str)
                ad_group_name = f"{safe_name} - G{group_idx}"
                campaigns.append({
                    "Record Type": "Campaign",
                    "Campaign Name": campaign_name,
                    "Campaign Daily Budget": str(daily_budget),
                    "Campaign Status": "Enabled",
                    "Ad Group Name": "",
                    "Keyword Text": "",
                    "Match Type": "",
                    "Bid": "",
                })
                campaigns.append({
                    "Record Type": "Ad Group",
                    "Campaign Name": campaign_name,
                    "Campaign Daily Budget": "",
                    "Campaign Status": "",
                    "Ad Group Name": ad_group_name,
                    "Keyword Text": "",
                    "Match Type": "",
                    "Bid": "",
                })
                for term in batch:
                    campaigns.append({
                        "Record Type": "Keyword",
                        "Campaign Name": campaign_name,
                        "Campaign Daily Budget": "",
                        "Campaign Status": "",
                        "Ad Group Name": ad_group_name,
                        "Keyword Text": term.search_term,
                        "Match Type": match_type,
                        "Bid": str(default_bid),
                    })

                # Negative keywords (items 14-15)
                if match_type == "Phrase":
                    for term in batch:
                        campaigns.append({
                            "Record Type": "Negative keyword",
                            "Campaign Name": campaign_name,
                            "Campaign Daily Budget": "",
                            "Campaign Status": "",
                            "Ad Group Name": ad_group_name,
                            "Keyword Text": term.search_term,
                            "Match Type": "Negative Exact",
                            "Bid": "",
                        })
                elif match_type == "Broad":
                    for term in batch:
                        campaigns.append({
                            "Record Type": "Negative keyword",
                            "Campaign Name": campaign_name,
                            "Campaign Daily Budget": "",
                            "Campaign Status": "",
                            "Ad Group Name": ad_group_name,
                            "Keyword Text": term.search_term,
                            "Match Type": "Negative Phrase",
                            "Bid": "",
                        })

        return CampaignGenerationResponse(
            upload=upload,
            campaign_count=1 + len(batches) * 3,  # Hero + grouped (Exact/Phrase/Broad each)
            hero_campaign_name=hero_campaign_name,
            group_count=len(batches),
            bulk_export_preview=campaigns[:40],  # First 40 rows as preview
        )

    def export_csv_rows(self, plan: CampaignGenerationResponse) -> list[dict]:
        """Return the full list of bulk sheet rows."""
        return plan.bulk_export_preview

    @staticmethod
    def _batch_keywords(items: list[CompetitorCleanedRow], batch_size: int) -> list[list[CompetitorCleanedRow]]:
        if not items:
            return []
        if len(items) <= batch_size:
            return [items]
        return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


# =============================================================================
# Dual-Path Competitor Campaign Generation: Deterministic + AI
# =============================================================================

COMPETITOR_CAMPAIGN_GEN_AI_AGENT_ID = "competitor_campaign_generation_agent"


class DualPathCompetitorCampaignGeneration(DualPathDecisionService[list[dict]]):
    """Dual-path competitor campaign generation service.

    Deterministic path: _deterministic_competitor_campaign_rows (exact rule-based).
    AI path: LLM reviews verified competitor keywords and proposes bulk sheet rows.
    Both paths produce the same output schema (list of bulk sheet row dicts).
    """

    AGENT_ID = COMPETITOR_CAMPAIGN_GEN_AI_AGENT_ID
    AGENT_DISPLAY_NAME = "Competitor Campaign Generation Agent"

    def _deterministic_path(self, inputs: dict) -> list[dict]:
        """Run deterministic competitor campaign generation."""
        terms: list[CompetitorCleanedRow] = inputs["top_terms"]
        product_name: str = inputs.get("product_name", "Product")
        daily_budget: Decimal = inputs.get("daily_budget", DEFAULT_DAILY_BUDGET)
        default_bid: Decimal = inputs.get("default_bid", DEFAULT_BID)
        batch_size: int = inputs.get("batch_size", BATCH_SIZE)

        if not terms:
            return []

        date_str = _date_label()
        safe_name = product_name.strip().replace(",", " ")
        hero_term = terms[0]
        remaining = terms[1:]
        rows: list[dict] = []

        hero_campaign = _campaign_name(product_name=safe_name, match_type="Exact", keyword_or_group=hero_term.search_term, date_label=date_str)
        hero_ad_group = f"{safe_name} - G0"
        rows.append({"Record Type": "Campaign", "Campaign Name": hero_campaign, "Campaign Daily Budget": str(daily_budget), "Campaign Status": "Enabled", "Ad Group Name": "", "Keyword Text": "", "Match Type": "", "Bid": ""})
        rows.append({"Record Type": "Ad Group", "Campaign Name": hero_campaign, "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": hero_ad_group, "Keyword Text": "", "Match Type": "", "Bid": ""})
        rows.append({"Record Type": "Keyword", "Campaign Name": hero_campaign, "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": hero_ad_group, "Keyword Text": hero_term.search_term, "Match Type": "Exact", "Bid": str(default_bid)})

        batches = [remaining[i:i + batch_size] for i in range(0, len(remaining), batch_size)]
        for group_idx, batch in enumerate(batches, start=1):
            group_label = f"Relevant{group_idx}"
            for match_type in ("Exact", "Phrase", "Broad"):
                campaign_name = _campaign_name(product_name=safe_name, match_type=match_type, keyword_or_group=group_label, date_label=date_str)
                ad_group_name = f"{safe_name} - G{group_idx}"
                rows.append({"Record Type": "Campaign", "Campaign Name": campaign_name, "Campaign Daily Budget": str(daily_budget), "Campaign Status": "Enabled", "Ad Group Name": "", "Keyword Text": "", "Match Type": "", "Bid": ""})
                rows.append({"Record Type": "Ad Group", "Campaign Name": campaign_name, "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": ad_group_name, "Keyword Text": "", "Match Type": "", "Bid": ""})
                for term in batch:
                    rows.append({"Record Type": "Keyword", "Campaign Name": campaign_name, "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": ad_group_name, "Keyword Text": term.search_term, "Match Type": match_type, "Bid": str(default_bid)})
                if match_type == "Phrase":
                    for term in batch:
                        rows.append({"Record Type": "Negative keyword", "Campaign Name": campaign_name, "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": ad_group_name, "Keyword Text": term.search_term, "Match Type": "Negative Exact", "Bid": ""})
                elif match_type == "Broad":
                    for term in batch:
                        rows.append({"Record Type": "Negative keyword", "Campaign Name": campaign_name, "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": ad_group_name, "Keyword Text": term.search_term, "Match Type": "Negative Phrase", "Bid": ""})
        return rows

    def _ai_prompt(self, inputs: dict) -> list[dict[str, str]]:
        terms: list[CompetitorCleanedRow] = inputs["top_terms"]
        product_name: str = inputs.get("product_name", "Product")
        terms_for_prompt = [
            {"search_term": t.search_term, "search_volume": str(t.search_volume) if t.search_volume else None, "relevance_score": t.relevance_score}
            for t in terms[:50]
        ]

        system = (
            "You are the AdSurf Competitor Campaign Generation Agent. "
            "Your job is to propose Amazon Ads bulk sheet campaign rows from verified competitor keywords. "
            f"{safety_prompt_snippet()}"
            "You propose bulk sheet rows only — they must be reviewed by a human before any export. "
            "Return JSON only. "
            "Every output must include decision_source='ai' and requires_human_approval=true."
        )
        user = {
            "task": "generate_competitor_campaign_bulk_sheet_rows",
            "product_name": product_name,
            "hero_term": terms_for_prompt[0] if terms_for_prompt else None,
            "remaining_terms": terms_for_prompt[1:] if len(terms_for_prompt) > 1 else [],
            "campaign_rules": {
                "hero_campaign_exact_only": True,
                "keyword_batch_size": 7,
                "match_types": ["Exact", "Phrase", "Broad"],
                "negative_keywords": "Phrase campaigns get Negative Exact, Broad campaigns get Negative Phrase",
                "campaign_name_format": "{ProductName} / SP / Manual / {MatchType} / {KeywordOrRelevantGroup} / {Mon DD}",
            },
            "required_output_shape": {
                "bulk_sheet_rows": [
                    {
                        "Record Type": "Campaign | Ad Group | Keyword | Negative keyword",
                        "Campaign Name": "...",
                        "Campaign Daily Budget": "string or empty",
                        "Campaign Status": "Enabled or empty",
                        "Ad Group Name": "string or empty",
                        "Keyword Text": "string or empty",
                        "Match Type": "Exact | Phrase | Broad | Negative Exact | Negative Phrase or empty",
                        "Bid": "string or empty",
                    }
                ],
                "decision_source": "ai",
                "requires_human_approval": True,
                "executes_live_amazon_change": False,
            },
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, sort_keys=True)},
        ]

    def _validate_ai_output(self, ai_json: dict, inputs: dict) -> list[str]:
        errors: list[str] = []
        rows = ai_json.get("bulk_sheet_rows", [])
        if not rows:
            errors.append("AI output must include bulk_sheet_rows.")
        if ai_json.get("decision_source") != "ai":
            errors.append("decision_source must be 'ai'.")
        if ai_json.get("requires_human_approval") is not True:
            errors.append("requires_human_approval must be true.")
        if ai_json.get("executes_live_amazon_change") is not False:
            errors.append("executes_live_amazon_change must be false.")
        for i, row in enumerate(rows):
            if row.get("Record Type") not in ("Campaign", "Ad Group", "Keyword", "Negative keyword"):
                errors.append(f"bulk_sheet_rows[{i}].Record Type is invalid.")
        return errors

    def _parse_ai_output(self, ai_json: dict, inputs: dict) -> list[dict]:
        return ai_json.get("bulk_sheet_rows", [])

    def _empty_result(self) -> list[dict]:
        return []


def _date_label() -> str:
    return datetime.now(UTC).strftime("%b %d").replace(" 0", " ")


def _campaign_name(*, product_name: str, match_type: str, keyword_or_group: str | None, date_label: str) -> str:
    label = (keyword_or_group or "Relevant1").strip().replace(",", " ")
    return f"{product_name} / SP / Manual / {match_type} / {label} / {date_label}"
