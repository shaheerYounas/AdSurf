"""Customizable prompt template system for AdSurf dual-path agents.

Provides template rendering with variable substitution, custom system
instructions injection, and model parameter overrides per agent/service.

Pattern matches agentic system controllers where users can customize:
- System prompt templates
- User prompt templates  
- Custom business instructions (injected into system prompt)
- Model parameters (temperature, max_tokens, model selection)
- Deterministic rule thresholds
- Bulk data input limits
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
import re


# =============================================================================
# Template Engine
# =============================================================================


@dataclass
class PromptTemplate:
    """A configurable prompt template with variable substitution."""
    name: str
    description: str = ""
    system_template: str = ""  # {variables} supported
    user_template: str = ""    # {variables} supported
    variables: dict[str, str] = field(default_factory=dict)  # description of each variable

    def render_system(self, inputs: dict[str, Any]) -> str:
        """Render system prompt with variable substitution."""
        return self._render(self.system_template, inputs)

    def render_user(self, inputs: dict[str, Any]) -> str:
        """Render user prompt with variable substitution."""
        return self._render(self.user_template, inputs)

    def _render(self, template: str, inputs: dict[str, Any]) -> str:
        """Simple {variable} substitution from inputs dict."""
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            value = inputs.get(key, "")
            if isinstance(value, (dict, list)):
                import json
                return json.dumps(value, default=str, sort_keys=True)
            return str(value)
        return re.sub(r"\{(\w+)\}", replacer, template)


@dataclass
class AgentPromptConfig:
    """Complete prompt configuration for a single agent/service.

    This is the core customization object — users can override every aspect
    of how an agent prompts the AI model.
    """
    # Prompt templates
    custom_system_instruction: str | None = None   # additional instructions appended to system prompt
    custom_business_goal: str | None = None        # business context for the agent
    custom_role_description: str | None = None     # overrides the agent's role description
    custom_output_format: str | None = None        # overrides the expected output format
    custom_examples: list[dict] | None = None      # few-shot examples to include

    # Model parameters
    temperature: float | None = None        # 0.0 - 2.0
    max_tokens: int | None = None           # max output tokens
    top_p: float | None = None             # nucleus sampling
    frequency_penalty: float | None = None # -2.0 - 2.0
    presence_penalty: float | None = None  # -2.0 - 2.0

    # Data limits
    max_rows_per_ai_call: int | None = None        # row limit for bulk data
    max_groups_per_ai_call: int | None = None      # group limit
    include_sample_data: bool = True               # whether to include sample rows in prompt
    sample_row_count: int = 5                      # how many sample rows to include
    include_deterministic_baseline: bool = True    # whether AI sees deterministic results for comparison

    # Safety overrides (can only be made MORE restrictive)
    require_high_confidence: bool | None = None
    additional_safety_notes: str | None = None     # appended to safety prompt snippet


@dataclass
class DeterministicRuleConfig:
    """Customizable deterministic rule thresholds per service.

    Users can adjust these to match their business needs while the
    deterministic path remains the safety fallback.
    """
    # Keyword Scoring rules
    relevance_score_threshold: int = 3       # approve if relevance >= this value
    max_rank_value: int = 15                 # rank values below this count toward relevance
    max_competitor_rank_columns: int = 10    # max competitor rank columns to evaluate
    min_search_volume: int = 0               # minimum search volume to consider

    # Campaign Generation rules
    keyword_batch_size: int = 7              # keywords per ad group
    default_daily_budget: Decimal | str = "10.0000"
    default_bid: Decimal | str = "1.0000"
    max_keywords_per_ai_call: int = 100      # max keywords sent to AI

    # Report Detection rules
    min_required_column_match_pct: float = 0.8  # percentage of columns that must match

    # General scoring rules
    error_on_empty_row: bool = True
    error_on_missing_search_term: bool = True
    error_on_invalid_volume: bool = True

    def to_dict(self) -> dict:
        return {
            "relevance_score_threshold": self.relevance_score_threshold,
            "max_rank_value": self.max_rank_value,
            "max_competitor_rank_columns": self.max_competitor_rank_columns,
            "min_search_volume": self.min_search_volume,
            "keyword_batch_size": self.keyword_batch_size,
            "default_daily_budget": str(self.default_daily_budget),
            "default_bid": str(self.default_bid),
            "max_keywords_per_ai_call": self.max_keywords_per_ai_call,
            "min_required_column_match_pct": self.min_required_column_match_pct,
            "error_on_empty_row": self.error_on_empty_row,
            "error_on_missing_search_term": self.error_on_missing_search_term,
            "error_on_invalid_volume": self.error_on_invalid_volume,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeterministicRuleConfig":
        defaults = cls()
        return cls(
            relevance_score_threshold=data.get("relevance_score_threshold", defaults.relevance_score_threshold),
            max_rank_value=data.get("max_rank_value", defaults.max_rank_value),
            max_competitor_rank_columns=data.get("max_competitor_rank_columns", defaults.max_competitor_rank_columns),
            min_search_volume=data.get("min_search_volume", defaults.min_search_volume),
            keyword_batch_size=data.get("keyword_batch_size", defaults.keyword_batch_size),
            default_daily_budget=data.get("default_daily_budget", defaults.default_daily_budget),
            default_bid=data.get("default_bid", defaults.default_bid),
            max_keywords_per_ai_call=data.get("max_keywords_per_ai_call", defaults.max_keywords_per_ai_call),
            min_required_column_match_pct=data.get("min_required_column_match_pct", defaults.min_required_column_match_pct),
            error_on_empty_row=data.get("error_on_empty_row", defaults.error_on_empty_row),
            error_on_missing_search_term=data.get("error_on_missing_search_term", defaults.error_on_missing_search_term),
            error_on_invalid_volume=data.get("error_on_invalid_volume", defaults.error_on_invalid_volume),
        )


# =============================================================================
# Pre-built System Prompts for Each Service
# =============================================================================

# These are the default prompts — users can override via AgentPromptConfig

KEYWORD_SCORING_SYSTEM_PROMPT = (
    "You are the AdSurf Keyword Scoring Agent for Amazon competitor keyword analysis. "
    "Your job is to review parsed competitor keyword rows and assign relevance scores "
    "based on competitor rank data. "
    "Return JSON only. Do not recalculate metrics that are already provided. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

COMPETITOR_SCORING_SYSTEM_PROMPT = (
    "You are the AdSurf Competitor Scoring Agent for Amazon competitor keyword analysis. "
    "Your job is to review competitor keyword rows and assign relevance scores "
    "based on competitor rank values across multiple columns. "
    "Return JSON only. Do not recalculate metrics. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

CAMPAIGN_GENERATION_SYSTEM_PROMPT = (
    "You are the AdSurf Campaign Generation Agent for Amazon Ads. "
    "Your job is to propose campaign structures from approved keywords, "
    "including campaign naming, ad group creation, match type selection, "
    "and negative keyword strategy. "
    "You propose campaign plans only — they must be reviewed by a human before any bulk sheet export. "
    "Return JSON only. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

COMPETITOR_CAMPAIGN_GEN_SYSTEM_PROMPT = (
    "You are the AdSurf Competitor Campaign Generation Agent. "
    "Your job is to propose Amazon Ads bulk sheet campaign rows from verified competitor keywords. "
    "Include campaign, ad group, keyword, and negative keyword rows. "
    "You propose bulk sheet rows only — they must be reviewed by a human before any export. "
    "Return JSON only. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

COLUMN_MAPPING_SYSTEM_PROMPT = (
    "You are the AdSurf Column Mapping Agent. "
    "Your job is to suggest column mappings for Amazon competitor keyword files, "
    "identifying search term columns, search volume columns, and competitor rank columns "
    "from CSV/Excel column headers and sample data. "
    "You suggest mappings only — they must be reviewed by a human before approval. "
    "Return JSON only. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

REPORT_DETECTION_SYSTEM_PROMPT = (
    "You are the AdSurf Report Detection Agent for Amazon Ads reports. "
    "Your job is to detect the type of an uploaded Amazon Ads report from its headers and sample data. "
    "Known types: bulk_sheet, sponsored_products_search_term_report, "
    "sponsored_products_targeting_report, sponsored_products_campaign_report. "
    "You detect report types only — you do not modify or approve anything. "
    "Return JSON only. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

KEYWORD_REVIEW_SYSTEM_PROMPT = (
    "You are the AdSurf Keyword Review Agent for Amazon Ads keyword review. "
    "Your job is to review scored keyword candidates and suggest approval/rejection decisions "
    "based on relevance scores, search volumes, and competitor data. "
    "You suggest review decisions only — they must be approved by a human. "
    "Return JSON only. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

MONITORING_AGENTS_SYSTEM_PROMPT = (
    "You are the AdSurf Monitoring Agents Explainer. "
    "Your job is to generate human-readable explanations for Amazon Ads monitoring outputs, "
    "including performance summaries, quality assessments, and stakeholder reports. "
    "You generate explanations only — you do not approve, reject, or execute any ad changes. "
    "Return JSON only. "
    "Every output must include decision_source='ai', requires_human_approval=true, "
    "and executes_live_amazon_change=false."
    "{custom_instruction}"
    "{business_goal}"
    "{safety_notes}"
)

# Map agent_id -> default system prompt
DEFAULT_SYSTEM_PROMPTS: dict[str, str] = {
    "keyword_scoring_agent": KEYWORD_SCORING_SYSTEM_PROMPT,
    "competitor_scoring_agent": COMPETITOR_SCORING_SYSTEM_PROMPT,
    "campaign_generation_agent": CAMPAIGN_GENERATION_SYSTEM_PROMPT,
    "competitor_campaign_generation_agent": COMPETITOR_CAMPAIGN_GEN_SYSTEM_PROMPT,
    "column_mapping_agent": COLUMN_MAPPING_SYSTEM_PROMPT,
    "report_detection_agent": REPORT_DETECTION_SYSTEM_PROMPT,
    "keyword_review_agent": KEYWORD_REVIEW_SYSTEM_PROMPT,
    "monitoring_agents_explainer": MONITORING_AGENTS_SYSTEM_PROMPT,
    "ai_recommendation_brain_agent": (
        "You are AdSurf's AI Recommendation Brain for Amazon Ads account reports. "
        "Return strict JSON only. You may create recommendation decisions, but you must not approve, reject, "
        "execute, export, or claim live Amazon Ads changes. Every recommendation must require human approval "
        "and executes_live_amazon_change must be false."
        "{custom_instruction}"
        "{business_goal}"
        "{safety_notes}"
    ),
}


# =============================================================================
# Prompt Builder
# =============================================================================


def build_system_prompt(
    *,
    agent_id: str,
    prompt_config: AgentPromptConfig | None = None,
    safety_prompt: str = "",
    custom_instruction: str | None = None,
    business_goal: str | None = None,
) -> str:
    """Build a system prompt from agent defaults + user customization.

    Args:
        agent_id: The agent identifier (e.g., 'keyword_scoring_agent')
        prompt_config: Full AgentPromptConfig for customization
        safety_prompt: The safety_prompt_snippet() string
        custom_instruction: Override custom system instruction
        business_goal: Override custom business goal

    Returns:
        Complete rendered system prompt string
    """
    base_template = DEFAULT_SYSTEM_PROMPTS.get(agent_id, (
        "You are an AdSurf AI agent. Return JSON only. "
        "Every output must include decision_source='ai', requires_human_approval=true, "
        "and executes_live_amazon_change=false."
        "{custom_instruction}"
        "{business_goal}"
        "{safety_notes}"
    ))

    config = prompt_config or AgentPromptConfig()
    instruction = custom_instruction or config.custom_system_instruction or ""
    goal = business_goal or config.custom_business_goal or ""
    additional_safety = config.additional_safety_notes or ""

    variables = {
        "custom_instruction": f"\nCUSTOM INSTRUCTION: {instruction}" if instruction else "",
        "business_goal": f"\nBUSINESS GOAL: {goal}" if goal else "",
        "safety_notes": f"\nADDITIONAL SAFETY: {safety_prompt}\n{additional_safety}" if safety_prompt or additional_safety else f"\n{safety_prompt}",
    }

    template = PromptTemplate(
        name=agent_id,
        system_template=base_template,
        variables=variables,
    )

    return template.render_system(variables)


def build_user_prompt_with_bulk_data(
    *,
    task_description: str,
    bulk_data: dict[str, Any],
    output_shape: dict[str, Any],
    deterministic_baseline: dict | None = None,
    prompt_config: AgentPromptConfig | None = None,
    include_deterministic_baseline: bool = True,
) -> dict:
    """Build a user prompt that includes bulk data for AI analysis.

    Args:
        task_description: Description of the task
        bulk_data: The bulk data to send to the AI (rows, metrics, etc.)
        output_shape: Expected JSON output schema
        deterministic_baseline: Optional deterministic results for comparison
        prompt_config: AgentPromptConfig for customization
        include_deterministic_baseline: Whether to include deterministic baseline

    Returns:
        Dict ready to be serialized to JSON for the user message
    """
    config = prompt_config or AgentPromptConfig()
    payload: dict[str, Any] = {
        "task": task_description,
        "data": bulk_data,
        "required_output_shape": output_shape,
    }

    if include_deterministic_baseline and deterministic_baseline is not None and config.include_deterministic_baseline:
        payload["deterministic_baseline"] = deterministic_baseline
        payload["compare_note"] = "Compare AI output against the deterministic_baseline. Highlight differences with reasoning."

    if config.custom_examples:
        payload["few_shot_examples"] = config.custom_examples

    return payload


def get_model_params(prompt_config: AgentPromptConfig | None = None) -> dict:
    """Extract model parameters from prompt config for AI client calls.

    Returns dict with only non-None values (so defaults take over for None).
    """
    config = prompt_config or AgentPromptConfig()
    params: dict[str, Any] = {}
    if config.temperature is not None:
        params["temperature"] = config.temperature
    if config.max_tokens is not None:
        params["max_tokens"] = config.max_tokens
    if config.top_p is not None:
        params["top_p"] = config.top_p
    if config.frequency_penalty is not None:
        params["frequency_penalty"] = config.frequency_penalty
    if config.presence_penalty is not None:
        params["presence_penalty"] = config.presence_penalty
    return params