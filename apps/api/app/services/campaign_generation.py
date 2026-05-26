from decimal import Decimal
from uuid import UUID

from apps.api.app.schemas.campaigns import CampaignKeyword
from apps.api.app.schemas.keyword_review import ApprovedKeywordSetItem
from apps.api.app.schemas.product_profiles import ProductProfile


CAMPAIGN_RULE_VERSION = "campaign_creation_rules_v1"
DEFAULT_DAILY_BUDGET = Decimal("10.0000")
DEFAULT_BID = Decimal("1.0000")


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
            "campaign_name": _campaign_name(product=product, group_index=0, match_type="Hero"),
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


def _campaign_name(*, product: ProductProfile, group_index: int, match_type: str) -> str:
    safe_name = product.product_name.strip().replace(",", " ")
    return f"{safe_name} - G{group_index} - {match_type}"


def _ad_group_name(*, product: ProductProfile, group_index: int) -> str:
    safe_name = product.product_name.strip().replace(",", " ")
    return f"{safe_name} - G{group_index}"
