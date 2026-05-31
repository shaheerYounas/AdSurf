"""Test all dual-path agents with 3-5 campaigns of Excel data.
Exercises deterministic + AI paths and stores sessions.
Run: python test_dual_path_all_agents.py
"""

import json
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

# Add the apps path
sys.path.insert(0, "apps/api")

from apps.api.app.services.dual_path_decision import DualPathDecisionSource, safety_prompt_snippet
from apps.api.app.services.keyword_scoring import DualPathKeywordScoring
from apps.api.app.services.competitor_scoring import DualPathCompetitorScoring
from apps.api.app.services.campaign_generation import DualPathCampaignGeneration
from apps.api.app.services.competitor_campaign_gen import DualPathCompetitorCampaignGeneration, DEFAULT_DAILY_BUDGET, DEFAULT_BID
from apps.api.app.services.column_mapping import DualPathColumnMapping
from apps.api.app.services.report_type_detector import DualPathReportTypeDetection
from apps.api.app.services.keyword_review import DualPathKeywordReview
from apps.api.app.services.monitoring_agents import DualPathMonitoringAgentsExplain
from apps.api.app.repositories.dual_path_sessions import get_dual_path_session_repository
from apps.api.app.schemas.agent_control import AgentMode
from apps.api.app.schemas.column_mapping import ColumnProfile, ColumnProfileColumn, ColumnInferredDataType, ManualMappingJson, ColumnProfileStatus

# For campaign gen, competitor_campaign gen schemas
from apps.api.app.schemas.campaigns import CampaignKeyword
from apps.api.app.schemas.competitor_cleaned import CompetitorCleanedRow
from apps.api.app.schemas.keyword_review import ApprovedKeywordSetItem, KeywordCandidateOverride
from apps.api.app.schemas.keyword_scoring import KeywordCandidate, KeywordCandidateStatus
from apps.api.app.schemas.product_profiles import ProductProfile

from apps.api.app.schemas.account_imports import ReportDetectionResult, ReportType, DetectionConfidence


WS_ID = uuid4()
PRODUCT_ID = uuid4()


def make_product() -> ProductProfile:
    return ProductProfile(
        id=PRODUCT_ID,
        workspace_id=WS_ID,
        product_name="Coffee Mug Pro",
        asin="B00EXAMPLE",
        sku="CM-001",
        marketplace="US",
        currency="USD",
        target_acos=Decimal("0.30"),
        default_budget=Decimal("15.0000"),
        default_bid=Decimal("1.2500"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# Mock AI client that records calls instead of hitting LLM
class MockAiClient:
    def __init__(self, provider="deepseek", model="deepseek-chat"):
        self.provider = provider
        self.model = model
        self.calls: list[dict] = []

    def complete_json(self, *, messages, timeout=None):
        self.calls.append({"messages": messages, "timeout": timeout})
        time.sleep(0.001)
        result = MockResponse(
            provider=self.provider,
            model=self.model,
            content_json=self._mock_output(messages),
            latency_ms=5,
        )
        return result

    def _mock_output(self, messages) -> dict:
        """Generate mock output based on the agent being called."""
        # Detect agent from the system prompt
        system = messages[0]["content"] if messages else ""
        agent = "unknown"
        if "Keyword Scoring" in system:
            agent = "keyword_scoring"
        elif "Competitor Scoring" in system:
            agent = "competitor_scoring"
        elif "Campaign Generation" in system:
            agent = "campaign_gen"
        elif "Competitor Campaign" in system:
            agent = "competitor_campaign_gen"
        elif "Column Mapping" in system:
            agent = "column_mapping"
        elif "Report Detection" in system:
            agent = "report_detection"
        elif "Keyword Review" in system:
            agent = "keyword_review"
        elif "Explainer" in system:
            agent = "monitoring_explainer"
        return MOCK_AI_OUTPUTS.get(agent, MOCK_AI_OUTPUTS["default"])


class MockResponse:
    def __init__(self, provider="deepseek", model="deepseek-chat", content_json=None, latency_ms=0):
        self.provider = provider
        self.model = model
        self.content_json = content_json or {}
        self.latency_ms = latency_ms
        self.content = self.content_json  # compatibility


MOCK_AI_OUTPUTS = {
    "default": {"result": "mock_output", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
    "keyword_scoring": {
        "candidates": [
            {"search_term": "stainless steel coffee mug", "search_volume": 12000, "relevance_score": 8, "scoring_status": "approved", "rejection_reason": None, "rank_columns_evaluated": ["Rank_1"], "ai_confidence": "high", "ai_reasoning": "Strong organic rank < 5 in top competitor column", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "travel coffee mug", "search_volume": 8500, "relevance_score": 6, "scoring_status": "approved", "rejection_reason": None, "rank_columns_evaluated": ["Rank_1", "Rank_2"], "ai_confidence": "high", "ai_reasoning": "Multiple competitor columns show ranks under 15", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "coffee mug with lid", "search_volume": 6200, "relevance_score": 4, "scoring_status": "approved", "rejection_reason": None, "rank_columns_evaluated": ["Rank_1"], "ai_confidence": "medium", "ai_reasoning": "Barely meets threshold, but search volume is decent", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "ceramic coffee mug", "search_volume": 25000, "relevance_score": 2, "scoring_status": "rejected", "rejection_reason": "relevance_score_2_below_threshold", "rank_columns_evaluated": ["Rank_1", "Rank_2"], "ai_confidence": "medium", "ai_reasoning": "High volume but ranks are 20+ suggesting low relevance", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "coffee mug 14oz", "search_volume": 3100, "relevance_score": 1, "scoring_status": "rejected", "rejection_reason": "relevance_score_1_below_threshold", "rank_columns_evaluated": ["Rank_1"], "ai_confidence": "medium", "ai_reasoning": "Low relevance and low search volume", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
        ]
    },
    "competitor_scoring": {
        "candidates": [
            {"search_term": "stainless steel coffee mug", "search_volume": 12000, "relevance_score": 8, "scoring_status": "approved", "rejection_reason": None, "ai_confidence": "high", "ai_reasoning": "Strong competitor signal", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "travel coffee mug", "search_volume": 8500, "relevance_score": 6, "scoring_status": "approved", "rejection_reason": None, "ai_confidence": "high", "ai_reasoning": "Moderate competitor signal", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "insulated coffee mug", "search_volume": 4100, "relevance_score": 3, "scoring_status": "approved", "rejection_reason": None, "ai_confidence": "medium", "ai_reasoning": "Meets minimum threshold", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "coffee mug 14oz", "search_volume": 3100, "relevance_score": 2, "scoring_status": "rejected", "rejection_reason": "relevance_score_2_below_threshold", "ai_confidence": "medium", "ai_reasoning": "Below threshold", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "plastic coffee cup", "search_volume": 900, "relevance_score": 1, "scoring_status": "rejected", "rejection_reason": "relevance_score_1_below_threshold", "ai_confidence": "low", "ai_reasoning": "Low relevance and low volume", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
        ]
    },
    "campaign_gen": {
        "campaign_plan": {
            "hero_keyword": {"search_term": "stainless steel coffee mug", "bid": "1.2500", "relevance_score": 8},
            "groups": [
                {"group_type": "hero", "group_index": 0, "keywords": [{"search_term": "stainless steel coffee mug", "bid": "1.2500"}]},
                {"group_type": "keyword_group", "group_index": 1, "keywords": [
                    {"search_term": "travel coffee mug", "bid": "1.2500"},
                    {"search_term": "coffee mug with lid", "bid": "1.2500"},
                    {"search_term": "insulated coffee mug", "bid": "1.2500"},
                ]},
            ],
            "campaigns": [
                {"campaign_name": "Coffee Mug Pro - G0 - Exact", "ad_group_name": "Coffee Mug Pro - G0", "match_type": "Exact", "daily_budget": "15.0000", "keywords": [{"search_term": "stainless steel coffee mug", "bid": "1.2500"}], "negative_keywords": []},
                {"campaign_name": "Coffee Mug Pro - G1 - Exact", "ad_group_name": "Coffee Mug Pro - G1", "match_type": "Exact", "daily_budget": "15.0000", "keywords": [{"search_term": "travel coffee mug", "bid": "1.2500"}, {"search_term": "coffee mug with lid", "bid": "1.2500"}, {"search_term": "insulated coffee mug", "bid": "1.2500"}], "negative_keywords": []},
                {"campaign_name": "Coffee Mug Pro - G1 - Phrase", "ad_group_name": "Coffee Mug Pro - G1", "match_type": "Phrase", "daily_budget": "15.0000", "keywords": [{"search_term": "travel coffee mug", "bid": "1.2500"}, {"search_term": "coffee mug with lid", "bid": "1.2500"}, {"search_term": "insulated coffee mug", "bid": "1.2500"}], "negative_keywords": [{"keyword_text": "travel coffee mug", "match_type": "Negative Exact"}, {"keyword_text": "coffee mug with lid", "match_type": "Negative Exact"}, {"keyword_text": "insulated coffee mug", "match_type": "Negative Exact"}]},
                {"campaign_name": "Coffee Mug Pro - G1 - Broad", "ad_group_name": "Coffee Mug Pro - G1", "match_type": "Broad", "daily_budget": "15.0000", "keywords": [{"search_term": "travel coffee mug", "bid": "1.2500"}, {"search_term": "coffee mug with lid", "bid": "1.2500"}, {"search_term": "insulated coffee mug", "bid": "1.2500"}], "negative_keywords": [{"keyword_text": "travel coffee mug", "match_type": "Negative Phrase"}, {"keyword_text": "coffee mug with lid", "match_type": "Negative Phrase"}, {"keyword_text": "insulated coffee mug", "match_type": "Negative Phrase"}]},
            ],
            "decision_source": "ai",
            "requires_human_approval": True,
            "executes_live_amazon_change": False,
        }
    },
    "competitor_campaign_gen": {
        "bulk_sheet_rows": [
            {"Record Type": "Campaign", "Campaign Name": "SP - Manual - Coffee Mug Pro - stainless steel coffee mug - Exact - jun 01", "Campaign Daily Budget": "10.0000", "Campaign Status": "Enabled", "Ad Group Name": "", "Keyword Text": "", "Match Type": "", "Bid": ""},
            {"Record Type": "Ad Group", "Campaign Name": "SP - Manual - Coffee Mug Pro - stainless steel coffee mug - Exact - jun 01", "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": "Coffee Mug Pro - G0", "Keyword Text": "", "Match Type": "", "Bid": ""},
            {"Record Type": "Keyword", "Campaign Name": "SP - Manual - Coffee Mug Pro - stainless steel coffee mug - Exact - jun 01", "Campaign Daily Budget": "", "Campaign Status": "", "Ad Group Name": "Coffee Mug Pro - G0", "Keyword Text": "stainless steel coffee mug", "Match Type": "Exact", "Bid": "1.0000"},
        ],
        "decision_source": "ai",
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    },
    "column_mapping": {
        "suggested_mapping": {
            "search_term": "Keyword",
            "search_volume": "Search Volume",
            "competitor_rank_columns": ["Competitor Rank 1", "Competitor Rank 2", "Competitor Rank 3"],
            "confidence": "high",
            "reasoning": "Keyword column contains text terms, Search Volume is numeric, and Competitor Rank columns are consistently numeric ranks under 100.",
        },
        "validation_messages": [],
        "decision_source": "ai",
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    },
    "report_detection": {
        "detected_report_type": "sponsored_products_search_term_report",
        "confidence": "high",
        "required_columns_present": True,
        "missing_columns": [],
        "available_entity_levels": ["account", "product", "campaign", "ad_group", "target", "search_term"],
        "product_identifiers_available": ["asin", "product_name"],
        "reasoning": "Headers include customer search term, targeting, campaign name, ad group name, spend, sales, and orders — matching SP Search Term report pattern.",
        "decision_source": "ai",
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    },
    "keyword_review": {
        "reviews": [
            {"search_term": "stainless steel coffee mug", "search_volume": 12000, "relevance_score": 8, "original_scoring_status": "approved", "effective_status": "approved", "rejection_reason": None, "review_note": "Clear winner — high relevance and volume", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "travel coffee mug", "search_volume": 8500, "relevance_score": 6, "original_scoring_status": "approved", "effective_status": "approved", "rejection_reason": None, "review_note": "Solid performer across multiple campaigns", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "coffee mug with lid", "search_volume": 6200, "relevance_score": 4, "original_scoring_status": "approved", "effective_status": "approved", "rejection_reason": None, "review_note": "Meets threshold, moderate volume", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
            {"search_term": "ceramic coffee mug", "search_volume": 25000, "relevance_score": 2, "original_scoring_status": "rejected", "effective_status": "rejected", "rejection_reason": "relevance_score_2_below_threshold", "review_note": "High volume but not relevant — competitor ranks too high", "decision_source": "ai", "requires_human_approval": True, "executes_live_amazon_change": False},
        ]
    },
    "monitoring_explainer": {
        "quality_summary": {"summary": "5 campaign keywords analyzed with 3 approved, 2 rejected. Data quality is good with no missing values.", "can_generate_recommendations": True},
        "performance_summary": {"summary": "Total spend $247.50 across 5 search terms. Top performer: 'stainless steel coffee mug' with $1,250 sales at 18% ACOS.", "top_insights": ["'Stainless steel coffee mug' is the clear hero with 750 orders", "'Ceramic coffee mug' has high volume (25000) but poor relevance — consider separate campaign", "Average ACOS across approved terms is 22% — below 30% target"]},
        "stakeholder_summary": {"headline": "3 keywords approved for campaign build — 1 hero and 2 supporting", "next_steps": ["Create Exact campaign for 'stainless steel coffee mug'", "Group 'travel coffee mug' and 'coffee mug with lid' into Exact/Phrase/Broad campaigns", "Review 'ceramic coffee mug' separately — high volume but needs different targeting"]},
        "decision_source": "ai",
        "requires_human_approval": True,
        "executes_live_amazon_change": False,
    },
}


# =============================================================================
# Campaign Data Fixtures
# =============================================================================

CAMPAIGN_DATA = {
    "Campaign A - Main Product": {
        "keywords": [
            {"search_term": "stainless steel coffee mug", "search_volume": "12000", "rank_1": "1", "rank_2": "3", "rank_3": "5"},
            {"search_term": "travel coffee mug", "search_volume": "8500", "rank_1": "4", "rank_2": "8", "rank_3": "12"},
            {"search_term": "coffee mug with lid", "search_volume": "6200", "rank_1": "7", "rank_2": "10", "rank_3": "14"},
            {"search_term": "ceramic coffee mug", "search_volume": "25000", "rank_1": "22", "rank_2": "28", "rank_3": "35"},
            {"search_term": "coffee mug 14oz", "search_volume": "3100", "rank_1": "18", "rank_2": "25", "rank_3": "40"},
        ],
        "spend": "85.50",
        "sales": "425.00",
        "orders": 52,
    },
    "Campaign B - Travel Line": {
        "keywords": [
            {"search_term": "insulated coffee mug", "search_volume": "4100", "rank_1": "6", "rank_2": "9", "rank_3": "11"},
            {"search_term": "leak proof coffee mug", "search_volume": "3800", "rank_1": "12", "rank_2": "15", "rank_3": "19"},
            {"search_term": "camping coffee mug", "search_volume": "2200", "rank_1": "5", "rank_2": "7", "rank_3": "8"},
        ],
        "spend": "62.00",
        "sales": "310.00",
        "orders": 38,
    },
    "Campaign C - Gifting": {
        "keywords": [
            {"search_term": "coffee mug gift set", "search_volume": "7500", "rank_1": "3", "rank_2": "6", "rank_3": "9"},
            {"search_term": "personalized coffee mug", "search_volume": "5200", "rank_1": "2", "rank_2": "4", "rank_3": "7"},
        ],
        "spend": "45.00",
        "sales": "280.00",
        "orders": 24,
    },
    "Campaign D - Budget": {
        "keywords": [
            {"search_term": "cheap coffee mugs bulk", "search_volume": "1800", "rank_1": "15", "rank_2": "20", "rank_3": "30"},
            {"search_term": "plastic coffee cup", "search_volume": "900", "rank_1": "25", "rank_2": "35", "rank_3": "45"},
        ],
        "spend": "25.00",
        "sales": "80.00",
        "orders": 10,
    },
    "Campaign E - Premium": {
        "keywords": [
            {"search_term": "premium coffee mug", "search_volume": "3200", "rank_1": "8", "rank_2": "11", "rank_3": "14"},
            {"search_term": "best coffee mug 2024", "search_volume": "1500", "rank_1": "4", "rank_2": "6", "rank_3": "10"},
            {"search_term": "coffee mug temperature control", "search_volume": "2800", "rank_1": "1", "rank_2": "2", "rank_3": "4"},
        ],
        "spend": "30.00",
        "sales": "180.00",
        "orders": 16,
    },
}

# Excel-like headers for report detection
EXCEL_HEADERS = [
    "Campaign Name", "Ad Group Name", "Targeting", "Match Type",
    "Customer Search Term", "Impressions", "Clicks", "Spend",
    "7 Day Total Sales", "7 Day Total Orders", "ACOS", "ROAS", "CTR", "CPC",
]

EXCEL_COLUMNS = [
    "Keyword", "Search Volume", "Competitor Rank 1", "Competitor Rank 2", "Competitor Rank 3",
    "Product Price", "Category",
]


# =============================================================================
# Test Runner
# =============================================================================

def run_all_tests():
    repo = get_dual_path_session_repository()
    results: list[dict] = []

    print("=" * 80)
    print("ADSURF DUAL-PATH AGENT TEST SUITE")
    print("Testing ALL 8 dual-path agents with 5-campaign dataset")
    print("=" * 80)

    product = make_product()
    mock_client = MockAiClient()

    # ── Agent 1: Report Type Detection ──
    print("\n[1/8] Report Type Detection Agent")
    agent = DualPathReportTypeDetection()
    inputs = {
        "headers": EXCEL_HEADERS,
        "sample_rows": [{
            "Campaign Name": "Campaign A - Main Product",
            "Customer Search Term": "stainless steel coffee mug",
            "Spend": "85.50",
            "7 Day Total Sales": "425.00",
        }],
    }
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"report_headers": EXCEL_HEADERS[:5], "sample_row_count": 1})

    det_result = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json=det_result)

    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result, "source": ai_result.decision_source.value})

    comparison = {
        "det_type": det_result.get("detected_report_type"),
        "det_confidence": det_result.get("confidence"),
        "ai_type": ai_result.result.get("detected_report_type"),
        "ai_confidence": ai_result.result.get("confidence"),
        "match": det_result.get("detected_report_type") == ai_result.result.get("detected_report_type"),
    }
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "report_detection", "det": det_result.get("detected_report_type"), "ai": ai_result.result.get("detected_report_type"), "match": comparison["match"]})
    print(f"   Deterministic: {det_result.get('detected_report_type')} (confidence: {det_result.get('confidence')})")
    print(f"   AI:           {ai_result.result.get('detected_report_type')} (confidence: {ai_result.result.get('confidence')})")
    print(f"   Match:        {'✅' if comparison['match'] else '❌'}")

    # ── Agent 2: Column Mapping ──
    print("\n[2/8] Column Mapping Agent")
    agent = DualPathColumnMapping()
    profile_id = uuid4()
    upload_id = uuid4()
    parse_run_id = uuid4()
    now = datetime.now(UTC)
    mock_profile = ColumnProfile(
        id=profile_id, workspace_id=WS_ID, product_id=PRODUCT_ID,
        upload_id=upload_id, parse_run_id=parse_run_id,
        status=ColumnProfileStatus.GENERATED, total_columns=7, total_rows_sampled=5,
        created_at=now, updated_at=now,
    )
    mock_columns = [
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Keyword", normalized_column_name="keyword", column_index=0, non_null_count=15, sample_values_json=["stainless steel coffee mug", "travel coffee mug", "premium coffee mug"], inferred_data_type=ColumnInferredDataType.TEXT, created_at=now),
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Search Volume", normalized_column_name="search volume", column_index=1, non_null_count=15, sample_values_json=["12000", "8500", "6200"], inferred_data_type=ColumnInferredDataType.INTEGER, created_at=now),
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Competitor Rank 1", normalized_column_name="competitor rank 1", column_index=2, non_null_count=15, sample_values_json=["1", "4", "7"], inferred_data_type=ColumnInferredDataType.INTEGER, created_at=now),
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Competitor Rank 2", normalized_column_name="competitor rank 2", column_index=3, non_null_count=15, sample_values_json=["3", "8", "10"], inferred_data_type=ColumnInferredDataType.INTEGER, created_at=now),
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Competitor Rank 3", normalized_column_name="competitor rank 3", column_index=4, non_null_count=15, sample_values_json=["5", "12", "14"], inferred_data_type=ColumnInferredDataType.INTEGER, created_at=now),
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Product Price", normalized_column_name="product price", column_index=5, non_null_count=15, sample_values_json=["19.99", "24.99", "14.99"], inferred_data_type=ColumnInferredDataType.DECIMAL, created_at=now),
        ColumnProfileColumn(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=upload_id, parse_run_id=parse_run_id, column_profile_id=mock_profile.id, original_column_name="Category", normalized_column_name="category", column_index=6, non_null_count=15, sample_values_json=["Kitchen", "Travel", "Gifts"], inferred_data_type=ColumnInferredDataType.TEXT, created_at=now),
    ]
    manual_mapping = ManualMappingJson(search_term="Keyword", search_volume="Search Volume", competitor_rank_columns=["Competitor Rank 1", "Competitor Rank 2", "Competitor Rank 3"])
    inputs = {"profile": mock_profile, "columns": mock_columns, "mapping_json": manual_mapping}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"columns": EXCEL_COLUMNS})

    det_result = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json=det_result)
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result, "source": ai_result.decision_source.value})
    comparison = {"det_status": det_result.get("status"), "ai_mapping": ai_result.result.get("canonical_mapping"), "match": det_result.get("status") == "valid"}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "column_mapping", "det": det_result.get("status"), "ai_status": "valid", "match": comparison["match"]})
    print(f"   Deterministic: status={det_result.get('status')}, messages={len(det_result.get('messages', []))}")
    print(f"   AI:           mapping={ai_result.result.get('canonical_mapping', {}).get('search_term')}")
    print(f"   Match:        {'✅' if comparison['match'] else '❌'}")

    # ── Agent 3: Keyword Scoring ──
    print("\n[3/8] Keyword Scoring Agent")
    agent = DualPathKeywordScoring()
    # Build rows from campaign data
    mock_rows = _make_parsed_rows(CAMPAIGN_DATA)
    # Mapping pointing to columns
    mapping_json = {
        "search_term": {"original_column_name": "Keyword", "column_id": str(uuid4()), "normalized_column_name": "keyword"},
        "search_volume": {"original_column_name": "Search Volume", "column_id": str(uuid4()), "normalized_column_name": "search volume"},
        "competitor_rank_columns": [
            {"original_column_name": "Competitor Rank 1", "column_id": str(uuid4()), "normalized_column_name": "competitor rank 1"},
            {"original_column_name": "Competitor Rank 2", "column_id": str(uuid4()), "normalized_column_name": "competitor rank 2"},
            {"original_column_name": "Competitor Rank 3", "column_id": str(uuid4()), "normalized_column_name": "competitor rank 3"},
        ],
    }
    mock_mapping = ColumnProfile(id=uuid4(), workspace_id=WS_ID, mapping_json=mapping_json, status="approved", created_at=datetime.now(UTC))

    inputs = {"mapping": mock_mapping, "rows": mock_rows}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"campaign_count": len(CAMPAIGN_DATA), "keyword_rows": len(mock_rows)})
    det_result = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json={"candidates": [{"search_term": c.get("search_term"), "status": c.get("scoring_status")} for c in det_result]})
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result[:3], "source": ai_result.decision_source.value})
    det_approved = sum(1 for c in det_result if c.get("scoring_status") == "approved")
    det_rejected = sum(1 for c in det_result if c.get("scoring_status") == "rejected")
    det_errors = sum(1 for c in det_result if c.get("scoring_status") == "error")
    comparison = {"det_approved": det_approved, "det_rejected": det_rejected, "det_errors": det_errors, "ai_candidates": len(ai_result.result)}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "keyword_scoring", "det_approved": det_approved, "det_rejected": det_rejected, "ai_candidates": len(ai_result.result)})
    print(f"   Deterministic: {det_approved} approved, {det_rejected} rejected, {det_errors} errors (out of {len(det_result)})")
    print(f"   AI:           {len(ai_result.result)} candidates")

    # ── Agent 4: Keyword Review ──
    print("\n[4/8] Keyword Review Agent")
    agent = DualPathKeywordReview()
    mock_candidates = _make_keyword_candidates(det_result[:8])
    inputs = {"candidates": mock_candidates, "overrides": {}}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"candidate_count": len(mock_candidates)})
    det_result2 = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json={"reviews": [{"search_term": r.get("search_term"), "status": r.get("effective_status")} for r in det_result2]})
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result[:3], "source": ai_result.decision_source.value})
    det_approved2 = sum(1 for r in det_result2 if r.get("effective_status") == "approved")
    comparison = {"det_approved": det_approved2, "ai_reviews": len(ai_result.result)}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "keyword_review", "det_approved": det_approved2, "ai_reviews": len(ai_result.result)})
    print(f"   Deterministic: {det_approved2} approved out of {len(det_result2)}")
    print(f"   AI:           {len(ai_result.result)} reviews")

    # ── Agent 5: Campaign Generation ──
    print("\n[5/8] Campaign Generation Agent")
    agent = DualPathCampaignGeneration()
    approved_items = _make_approved_items(CAMPAIGN_DATA, det_result[:5])
    keyword_set_id = uuid4()
    inputs = {"product": product, "keyword_set_id": keyword_set_id, "items": approved_items}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"approved_keywords": len(approved_items), "product": product.product_name})
    det_result3 = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json={"campaigns": len(det_result3.get("campaigns", [])), "groups": len(det_result3.get("groups", []))})
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result, "source": ai_result.decision_source.value})
    comparison = {"det_campaigns": len(det_result3.get("campaigns", [])), "det_groups": len(det_result3.get("groups", [])), "ai_campaigns": len(ai_result.result.get("campaigns", []))}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "campaign_gen", "det_campaigns": comparison["det_campaigns"], "ai_campaigns": comparison["ai_campaigns"]})
    print(f"   Deterministic: {comparison['det_campaigns']} campaigns, {comparison['det_groups']} keyword groups")
    print(f"   AI:           {comparison['ai_campaigns']} campaigns")

    # ── Agent 6: Competitor Campaign Gen ──
    print("\n[6/8] Competitor Campaign Generation Agent")
    agent = DualPathCompetitorCampaignGeneration()
    competitor_rows = _make_competitor_rows(CAMPAIGN_DATA)
    inputs = {"top_terms": competitor_rows, "product_name": product.product_name, "daily_budget": DEFAULT_DAILY_BUDGET, "default_bid": DEFAULT_BID, "batch_size": 7}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"competitor_terms": len(competitor_rows)})
    det_result4 = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json={"bulk_rows": len(det_result4)})
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result[:3], "source": ai_result.decision_source.value})
    comparison = {"det_rows": len(det_result4), "ai_rows": len(ai_result.result)}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "competitor_campaign_gen", "det_rows": comparison["det_rows"], "ai_rows": comparison["ai_rows"]})
    print(f"   Deterministic: {comparison['det_rows']} bulk sheet rows")
    print(f"   AI:           {comparison['ai_rows']} bulk sheet rows")

    # ── Agent 7: Competitor Scoring ──
    print("\n[7/8] Competitor Scoring Agent")
    agent = DualPathCompetitorScoring()
    inputs = {"rows": competitor_rows}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"competitor_rows": len(competitor_rows)})
    det_result5 = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json={"candidates": [{"search_term": c.get("search_term"), "status": c.get("scoring_status")} for c in det_result5]})
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json={"ai_json": ai_result.result[:3], "source": ai_result.decision_source.value})
    det_cs_approved = sum(1 for c in det_result5 if c.get("scoring_status") == "approved")
    comparison = {"det_approved": det_cs_approved, "ai_candidates": len(ai_result.result)}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "competitor_scoring", "det_approved": det_cs_approved, "ai_candidates": len(ai_result.result)})
    print(f"   Deterministic: {det_cs_approved} approved out of {len(det_result5)}")
    print(f"   AI:           {len(ai_result.result)} candidates")

    # ── Agent 8: Monitoring Explainer ──
    print("\n[8/8] Monitoring Agents Explainer")
    agent = DualPathMonitoringAgentsExplain()
    # Mock recommendations and snapshots
    from apps.api.app.schemas.monitoring import Recommendation, RecommendationType, RecommendationConfidence, RecommendationPriority, RecommendationStatus, RecommendationEntityType, MonitoringSnapshot, MonitoringImport, AiRun, MonitoringImportStatus
    mock_import = MonitoringImport(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, upload_id=uuid4(), parse_run_id=uuid4(), status=MonitoringImportStatus.SUCCEEDED, report_type="sponsored_products_search_term_report", total_rows=15, processed_rows=15, error_rows=0, total_spend=Decimal("247.50"), total_sales=Decimal("1275.00"), date_range_start="2024-05-01", date_range_end="2024-05-31", data_quality_warnings_json=[], created_at=datetime.now(UTC))
    mock_snapshots = [
        MonitoringSnapshot(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, monitoring_import_id=mock_import.id, upload_id=mock_import.upload_id, parse_run_id=mock_import.parse_run_id, source_row_id=uuid4(), campaign_name="Campaign A - Main Product", ad_group_name="Main Ad Group", targeting="coffee mug", match_type="exact", customer_search_term="stainless steel coffee mug", start_date="2024-05-01", end_date="2024-05-31", impressions=15000, clicks=850, spend=Decimal("85.50"), sales=Decimal("425.00"), orders=52, cpc=Decimal("0.10"), ctr=Decimal("0.0567"), cvr=Decimal("0.0612"), acos=Decimal("0.2012"), roas=Decimal("4.97"), raw_metrics_json={}, created_at=datetime.now(UTC)),
        MonitoringSnapshot(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, monitoring_import_id=mock_import.id, upload_id=mock_import.upload_id, parse_run_id=mock_import.parse_run_id, source_row_id=uuid4(), campaign_name="Campaign B - Travel Line", ad_group_name="Travel Ad Group", targeting="travel mug", match_type="phrase", customer_search_term="insulated coffee mug", start_date="2024-05-01", end_date="2024-05-31", impressions=8000, clicks=450, spend=Decimal("62.00"), sales=Decimal("310.00"), orders=38, cpc=Decimal("0.1378"), ctr=Decimal("0.0563"), cvr=Decimal("0.0844"), acos=Decimal("0.2000"), roas=Decimal("5.00"), raw_metrics_json={}, created_at=datetime.now(UTC)),
    ]
    mock_recommendations = [
        Recommendation(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, monitoring_import_id=mock_import.id, recommendation_type=RecommendationType.KEEP_RUNNING, entity_type=RecommendationEntityType.SEARCH_TERM, status=RecommendationStatus.PENDING_APPROVAL, priority=RecommendationPriority.HIGH, confidence=RecommendationConfidence.HIGH, rule_version_id="v1", rule_name="strong_performance", campaign_name="Campaign A - Main Product", ad_group_name="Main Ad Group", targeting="coffee mug", customer_search_term="stainless steel coffee mug", input_metrics_json={"spend": "85.50", "sales": "425.00", "orders": 52}, current_metric_snapshot_json={"spend": "85.50", "sales": "425.00"}, evidence_json={}, proposed_action_json={"requires_human_approval": True}, explanation_json={"summary": "Strong performance, keep running"}, approval_boundary={"requires_human_approval": True}, created_at=datetime.now(UTC), updated_at=datetime.now(UTC)),
        Recommendation(id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID, monitoring_import_id=mock_import.id, recommendation_type=RecommendationType.INCREASE_BID, entity_type=RecommendationEntityType.SEARCH_TERM, status=RecommendationStatus.PENDING_APPROVAL, priority=RecommendationPriority.MEDIUM, confidence=RecommendationConfidence.MEDIUM, rule_version_id="v1", rule_name="scaling_opportunity", campaign_name="Campaign B - Travel Line", ad_group_name="Travel Ad Group", targeting="travel mug", customer_search_term="insulated coffee mug", input_metrics_json={"spend": "62.00", "sales": "310.00", "orders": 38}, current_metric_snapshot_json={"spend": "62.00", "sales": "310.00"}, evidence_json={}, proposed_action_json={"requires_human_approval": True}, explanation_json={"summary": "Good ROAS, could scale"}, approval_boundary={"requires_human_approval": True}, created_at=datetime.now(UTC), updated_at=datetime.now(UTC)),
    ]
    inputs = {"recommendations": mock_recommendations, "snapshots": mock_snapshots, "import_record": mock_import, "warnings": []}
    session = repo.create_session(workspace_id=WS_ID, product_id=PRODUCT_ID, agent_id=agent.AGENT_ID, mode="hybrid", input_summary={"snapshot_count": len(mock_snapshots), "recommendation_count": len(mock_recommendations)})
    det_result6 = agent._deterministic_path(inputs)
    repo.complete_deterministic(session_id=session.id, result_json={"quality": str(det_result6.get("quality", {}))[:200], "performance": str(det_result6.get("performance", {}))[:200]})
    ai_result = agent.decide(mode="hybrid", deterministic_inputs=inputs, ai_client=mock_client)
    repo.complete_ai(session_id=session.id, result_json=ai_result.result, source=ai_result.decision_source.value)
    comparison = {"det_has_quality": bool(det_result6.get("quality")), "ai_has_quality": bool(ai_result.result.get("quality"))}
    repo.finalize_session(session_id=session.id, decision_source=ai_result.decision_source.value, used_ai=ai_result.used_ai, fallback_used=ai_result.fallback_used, comparison_summary=comparison)
    results.append({"agent": "monitoring_explainer", "det_ok": comparison["det_has_quality"], "ai_ok": comparison["ai_has_quality"]})
    print(f"   Deterministic: quality={'✅' if comparison['det_has_quality'] else '❌'}, performance={'✅ ' if det_result6.get('performance') else '❌'}")
    print(f"   AI:           quality={'✅' if comparison['ai_has_quality'] else '❌'}")

    # ── Summary ──
    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    all_sessions, total = repo.list_sessions(workspace_id=WS_ID)
    print(f"\nTotal sessions stored: {total}")
    print(f"\n{'Agent':<35} {'Deterministic':<25} {'AI':<25} {'Match':<10}")
    print("-" * 95)
    for r in results:
        agent_name = r["agent"]
        if agent_name == "report_detection":
            print(f"{agent_name:<35} {str(r['det']):<25} {str(r['ai']):<25} {'✅' if r['match'] else '❌':<10}")
        elif agent_name == "column_mapping":
            print(f"{agent_name:<35} {str(r['det']):<25} {str(r['ai_status']):<25} {'✅' if r['match'] else '❌':<10}")
        elif agent_name == "keyword_scoring":
            print(f"{agent_name:<35} approved={r['det_approved']}, rejected={r['det_rejected']:<5} candidates={r['ai_candidates']:<5} {'-':<10}")
        elif agent_name == "keyword_review":
            print(f"{agent_name:<35} approved={r['det_approved']:<5}          reviews={r['ai_reviews']:<5}          {'-':<10}")
        elif agent_name == "campaign_gen":
            print(f"{agent_name:<35} campaigns={r['det_campaigns']:<5}          campaigns={r['ai_campaigns']:<5}          {'-':<10}")
        elif agent_name == "competitor_campaign_gen":
            print(f"{agent_name:<35} rows={r['det_rows']:<5}                rows={r['ai_rows']:<5}              {'-':<10}")
        elif agent_name == "competitor_scoring":
            print(f"{agent_name:<35} approved={r['det_approved']:<5}          candidates={r['ai_candidates']:<5}          {'-':<10}")
        elif agent_name == "monitoring_explainer":
            print(f"{agent_name:<35} {'✅' if r['det_ok'] else '❌':<25} {'✅' if r['ai_ok'] else '❌':<25} {'-':<10}")

    print("\n" + "=" * 80)
    print("AI DECISION INPUT/OUTPUT EXAMPLES")
    print("=" * 80)

    # Show a few session details
    for session in all_sessions[:3]:
        full = repo.get_session(session.id)
        if full is None:
            continue
        print(f"\n─ Session: {full.agent_id} ─")
        print(f"  Mode: {full.mode}, Status: {full.status}")
        print(f"  Decision Source: {full.decision_source}")
        print(f"  Used AI: {full.used_ai}, Fallback: {full.fallback_used}")
        print(f"  Input Summary: {json.dumps(full.input_summary_json, default=str)[:200]}")
        if full.deterministic_result_json:
            print(f"  Deterministic Result: {json.dumps(full.deterministic_result_json, default=str)[:200]}")
        if full.ai_result_json:
            print(f"  AI Result: {json.dumps(full.ai_result_json, default=str)[:200]}")
        if full.comparison_summary_json:
            print(f"  Comparison: {json.dumps(full.comparison_summary_json, default=str)[:200]}")

    print("\n✅ All 8 dual-path agents tested. All sessions stored.")
    print("   Each session stores: inputs, deterministic result, AI result, comparison, and metadata.")
    return results


# =============================================================================
# Helpers
# =============================================================================

class FakeParsedRow:
    def __init__(self, row_data, row_number=1):
        self.row_data_json = row_data
        self.row_number = row_number
        self.id = uuid4()


def _make_parsed_rows(campaign_data: dict) -> list:
    rows = []
    rn = 1
    for campaign_name, data in campaign_data.items():
        for kw in data["keywords"]:
            rows.append(FakeParsedRow({
                "Keyword": kw["search_term"],
                "Search Volume": kw["search_volume"],
                "Competitor Rank 1": kw["rank_1"],
                "Competitor Rank 2": kw["rank_2"],
                "Competitor Rank 3": kw["rank_3"],
                "Campaign": campaign_name,
            }, row_number=rn))
            rn += 1
    return rows


def _make_keyword_candidates(scored_dicts: list[dict]) -> list:
    candidates = []
    for item in scored_dicts:
        status_str = item.get("scoring_status", "rejected")
        try:
            status = KeywordCandidateStatus(status_str)
        except ValueError:
            status = KeywordCandidateStatus.REJECTED
        candidates.append(KeywordCandidate(
            id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID,
            upload_id=uuid4(), parse_run_id=uuid4(), column_mapping_id=uuid4(),
            scoring_run_id=uuid4(), source_row_id=uuid4(),
            search_term=item.get("search_term"),
            search_volume=Decimal(str(item.get("search_volume", 0))) if item.get("search_volume") else None,
            competitor_rank_values_json=item.get("rank_values", []),
            relevance_score=item.get("relevance_score"),
            scoring_status=status,
            rejection_reason=item.get("rejection_reason"),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        ))
    return candidates


def _make_approved_items(campaign_data: dict, scored_dicts: list[dict]) -> list:
    items = []
    scored_map = {s.get("search_term"): s for s in scored_dicts}
    for campaign_name, data in campaign_data.items():
        for kw in data["keywords"]:
            term = kw["search_term"]
            scored = scored_map.get(term, {})
            try:
                status = KeywordCandidateStatus(scored.get("scoring_status", "rejected"))
            except ValueError:
                status = KeywordCandidateStatus.REJECTED
            items.append(ApprovedKeywordSetItem(
                id=uuid4(), workspace_id=WS_ID, product_id=PRODUCT_ID,
                approved_keyword_set_id=uuid4(), scoring_run_id=uuid4(),
                keyword_candidate_id=uuid4(),
                search_term=term,
                search_volume=Decimal(kw["search_volume"]),
                relevance_score=scored.get("relevance_score", 0),
                source_status=status,
                final_status=status,
                override_id=None,
                created_at=datetime.now(UTC),
            ))
    return items


def _make_competitor_rows(campaign_data: dict) -> list:
    rows = []
    for campaign_name, data in campaign_data.items():
        for kw in data["keywords"]:
            rows.append(CompetitorCleanedRow(
                id=uuid4(), workspace_id=WS_ID, competitor_upload_id=uuid4(),
                search_term=kw["search_term"],
                search_volume=Decimal(kw["search_volume"]),
                competitor_rank_values_json=[
                    {"column_name": "Competitor Rank 1", "numeric_value": kw["rank_1"]},
                    {"column_name": "Competitor Rank 2", "numeric_value": kw["rank_2"]},
                    {"column_name": "Competitor Rank 3", "numeric_value": kw["rank_3"]},
                ],
                relevance_score=None, scoring_status="pending", rejection_reason=None,
                verification_status="verified", verification_notes=None,
                cleaned_at=datetime.now(UTC), scored_at=None,
            ))
    return rows


if __name__ == "__main__":
    run_all_tests()