"""Campaign generation directly from competitor cleaned rows (items 8-15).

Wires the competitor pipeline into Amazon bulk sheet campaign creation.
Uses the 6-component naming convention: ProductName / SP / Manual / MatchType / Keyword-Group / Date.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.competitor_cleaned import CompetitorCleanedRepository
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow, CompetitorUpload, CampaignGenerationResponse

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

        date_str = datetime.now(UTC).strftime("%b %d").lower()  # e.g. "may 29"
        safe_name = product_name.strip().replace(",", " ")

        # Hero campaign (plan item 9)
        hero_campaign_name = f"SP - Manual - {safe_name} - {hero_term.search_term} - Exact - {date_str}"
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
                campaign_name = f"SP - Manual - {safe_name} - {group_label} - {match_type} - {date_str}"
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