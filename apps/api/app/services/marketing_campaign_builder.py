"""Marketing Campaign Builder — Phase 2 of the Marketing Project.

Consumes a list of ApprovedKeyword objects (from Phase 1) and produces a
structured CampaignPlanResult with a hero campaign and grouped campaigns
(Exact, Phrase, Broad) for the remaining keywords.

Design constraints:
  - Pure service: no DB, no HTTP, no side effects.
  - Follow sp_search_term_pipeline.py dataclass/StrEnum patterns.
  - Naming convention: {ProductName}_{AdType}_{Targeting}_{MatchType}_{KeywordOrGroup}_{Date}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from apps.api.app.services.competitor_research_pipeline import ApprovedKeyword


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DAILY_BUDGET = Decimal("10.00")
DEFAULT_BID = Decimal("1.00")

BATCH_MIN = 5
BATCH_MAX = 7


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MatchType(StrEnum):
    EXACT = "exact"
    PHRASE = "phrase"
    BROAD = "broad"


class AdType(StrEnum):
    SP = "SP"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NegativeKeyword:
    keyword: str
    match_type: MatchType


@dataclass
class AdGroupSpec:
    name: str
    keyword: str
    bid: Decimal
    match_type: MatchType


@dataclass
class CampaignSpec:
    name: str
    match_type: MatchType
    daily_budget: Decimal
    ad_groups: list[AdGroupSpec] = field(default_factory=list)
    negative_keywords: list[NegativeKeyword] = field(default_factory=list)
    is_hero: bool = False


@dataclass
class CampaignPlanResult:
    product_name: str
    hero_campaign: CampaignSpec
    grouped_campaigns: list[CampaignSpec] = field(default_factory=list)
    total_keywords: int = 0
    batch_count: int = 0


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class MarketingCampaignBuilder:
    """Pure service that builds a campaign plan from approved keywords.

    Usage::

        builder = MarketingCampaignBuilder()
        plan = builder.build(
            approved_keywords=approved,
            product_name="CoffeeMaker",
            created_date="May11",
        )
    """

    def build(
        self,
        approved_keywords: list[ApprovedKeyword],
        product_name: str,
        created_date: str = "",
    ) -> CampaignPlanResult:
        """Build a full campaign plan from the approved keyword list.

        Steps
        -----
        1. Sort by relevance_score desc, then search_volume desc.
        2. Hero: first keyword → 1 Campaign, 1 AdGroup, 1 Keyword, no negatives.
        3. Remaining: split into batches of 5–7; for each batch create 3 campaigns
           (Exact, Phrase, Broad) with the appropriate negative keyword lists.
        """
        if not approved_keywords:
            # Return a minimal empty plan rather than raising
            return CampaignPlanResult(
                product_name=product_name,
                hero_campaign=CampaignSpec(
                    name=self._build_campaign_name(
                        product_name=product_name,
                        ad_type=AdType.SP,
                        targeting="Manual",
                        match_type=MatchType.EXACT,
                        keyword_or_group="Hero",
                        date_str=created_date,
                    ),
                    match_type=MatchType.EXACT,
                    daily_budget=DEFAULT_DAILY_BUDGET,
                    ad_groups=[],
                    negative_keywords=[],
                    is_hero=True,
                ),
                grouped_campaigns=[],
                total_keywords=0,
                batch_count=0,
            )

        # Step 1 — Sort
        sorted_keywords = sorted(
            approved_keywords,
            key=lambda kw: (-kw.relevance_score, -kw.search_volume),
        )

        # Step 2 — Hero campaign
        hero_kw = sorted_keywords[0]
        hero_campaign = self._build_hero_campaign(
            keyword=hero_kw,
            product_name=product_name,
            created_date=created_date,
        )

        # Step 3 — Grouped campaigns for remaining keywords
        remaining = sorted_keywords[1:]
        batches = self._split_into_batches(remaining)
        grouped_campaigns: list[CampaignSpec] = []

        for group_num, batch in enumerate(batches, start=1):
            grouped_campaigns.extend(
                self._build_batch_campaigns(
                    batch=batch,
                    group_num=group_num,
                    product_name=product_name,
                    created_date=created_date,
                )
            )

        return CampaignPlanResult(
            product_name=product_name,
            hero_campaign=hero_campaign,
            grouped_campaigns=grouped_campaigns,
            total_keywords=len(sorted_keywords),
            batch_count=len(batches),
        )

    # ------------------------------------------------------------------
    # Hero campaign builder
    # ------------------------------------------------------------------

    def _build_hero_campaign(
        self,
        keyword: ApprovedKeyword,
        product_name: str,
        created_date: str,
    ) -> CampaignSpec:
        campaign_name = self._build_campaign_name(
            product_name=product_name,
            ad_type=AdType.SP,
            targeting="Manual",
            match_type=MatchType.EXACT,
            keyword_or_group=keyword.keyword,
            date_str=created_date,
        )
        ad_group_name = self._build_ad_group_name(
            product_name=product_name,
            match_type=MatchType.EXACT,
            keyword_or_group=keyword.keyword,
        )
        ad_group = AdGroupSpec(
            name=ad_group_name,
            keyword=keyword.keyword,
            bid=DEFAULT_BID,
            match_type=MatchType.EXACT,
        )
        return CampaignSpec(
            name=campaign_name,
            match_type=MatchType.EXACT,
            daily_budget=DEFAULT_DAILY_BUDGET,
            ad_groups=[ad_group],
            negative_keywords=[],
            is_hero=True,
        )

    # ------------------------------------------------------------------
    # Batch campaign builder (Exact, Phrase, Broad)
    # ------------------------------------------------------------------

    def _build_batch_campaigns(
        self,
        batch: list[ApprovedKeyword],
        group_num: int,
        product_name: str,
        created_date: str,
    ) -> list[CampaignSpec]:
        group_label = f"Group{group_num}"
        campaigns: list[CampaignSpec] = []

        # a) Exact Match — no negatives
        exact_campaign = self._build_single_match_campaign(
            batch=batch,
            product_name=product_name,
            match_type=MatchType.EXACT,
            group_label=group_label,
            created_date=created_date,
            negative_keywords=[],
        )
        campaigns.append(exact_campaign)

        # b) Phrase Match — negative EXACT = all keywords in this batch
        phrase_negatives = [
            NegativeKeyword(keyword=kw.keyword, match_type=MatchType.EXACT)
            for kw in batch
        ]
        phrase_campaign = self._build_single_match_campaign(
            batch=batch,
            product_name=product_name,
            match_type=MatchType.PHRASE,
            group_label=group_label,
            created_date=created_date,
            negative_keywords=phrase_negatives,
        )
        campaigns.append(phrase_campaign)

        # c) Broad Match — negative PHRASE = all keywords in this batch
        broad_negatives = [
            NegativeKeyword(keyword=kw.keyword, match_type=MatchType.PHRASE)
            for kw in batch
        ]
        broad_campaign = self._build_single_match_campaign(
            batch=batch,
            product_name=product_name,
            match_type=MatchType.BROAD,
            group_label=group_label,
            created_date=created_date,
            negative_keywords=broad_negatives,
        )
        campaigns.append(broad_campaign)

        return campaigns

    def _build_single_match_campaign(
        self,
        batch: list[ApprovedKeyword],
        product_name: str,
        match_type: MatchType,
        group_label: str,
        created_date: str,
        negative_keywords: list[NegativeKeyword],
    ) -> CampaignSpec:
        campaign_name = self._build_campaign_name(
            product_name=product_name,
            ad_type=AdType.SP,
            targeting="Manual",
            match_type=match_type,
            keyword_or_group=group_label,
            date_str=created_date,
        )
        ad_groups = [
            AdGroupSpec(
                name=self._build_ad_group_name(
                    product_name=product_name,
                    match_type=match_type,
                    keyword_or_group=kw.keyword,
                ),
                keyword=kw.keyword,
                bid=DEFAULT_BID,
                match_type=match_type,
            )
            for kw in batch
        ]
        return CampaignSpec(
            name=campaign_name,
            match_type=match_type,
            daily_budget=DEFAULT_DAILY_BUDGET,
            ad_groups=ad_groups,
            negative_keywords=negative_keywords,
            is_hero=False,
        )

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------

    def _build_campaign_name(
        self,
        product_name: str,
        ad_type: AdType,
        targeting: str,
        match_type: MatchType,
        keyword_or_group: str,
        date_str: str,
    ) -> str:
        """Format: {ProductName}_{AdType}_{Targeting}_{MatchType}_{KeywordOrGroup}_{Date}

        - product_name: spaces stripped (removed, not replaced)
        - keyword_or_group: spaces replaced with underscores
        - match_type: title-cased (Exact, Phrase, Broad)
        """
        safe_product = product_name.strip().replace(" ", "")
        safe_keyword = keyword_or_group.strip().replace(" ", "_")
        match_label = match_type.value.title()  # "Exact" | "Phrase" | "Broad"
        parts = [safe_product, str(ad_type), targeting, match_label, safe_keyword]
        if date_str:
            parts.append(date_str)
        return "_".join(parts)

    def _build_ad_group_name(
        self,
        product_name: str,
        match_type: MatchType,
        keyword_or_group: str,
    ) -> str:
        """Ad group name mirrors the campaign naming convention for clarity."""
        safe_product = product_name.strip().replace(" ", "")
        safe_keyword = keyword_or_group.strip().replace(" ", "_")
        match_label = match_type.value.title()
        return f"{safe_product}_{match_label}_{safe_keyword}"

    # ------------------------------------------------------------------
    # Batch splitter
    # ------------------------------------------------------------------

    @staticmethod
    def _split_into_batches(
        keywords: list[ApprovedKeyword],
    ) -> list[list[ApprovedKeyword]]:
        """Split keywords into batches of BATCH_MIN–BATCH_MAX (5–7).

        If the final chunk would fall below BATCH_MIN it is merged into the
        preceding batch rather than left as an under-populated group.
        """
        if not keywords:
            return []
        if len(keywords) <= BATCH_MAX:
            return [keywords]
        batches: list[list[ApprovedKeyword]] = []
        for start in range(0, len(keywords), BATCH_MAX):
            batches.append(keywords[start : start + BATCH_MAX])
        # Merge an undersized final batch into the previous one
        if len(batches) > 1 and len(batches[-1]) < BATCH_MIN:
            last = batches.pop()
            batches[-1] = batches[-1] + last
        return batches
