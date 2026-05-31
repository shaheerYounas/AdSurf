"""Shared dual-path decision base for all AdSurf services.

Every service that makes decisions must support BOTH paths:
- Deterministic: rule-based calculation (always available)
- AI: LLM-powered reasoning (configurable, with deterministic fallback)

Safety invariants (enforced regardless of path):
- AI may recommend, explain, and map — but never silently act
- Human approval required before any customer-impacting action
- No live Amazon Ads API mutation from any decision path
- Deterministic fallback on AI failure (hybrid/ai modes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Generic, TypeVar

from apps.api.app.schemas.agent_control import AgentMode
from apps.api.app.services.prompt_template import (
    AgentPromptConfig,
    DeterministicRuleConfig,
    build_system_prompt,
    build_user_prompt_with_bulk_data,
    get_model_params,
)


T = TypeVar("T")


class DualPathDecisionSource(StrEnum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    HYBRID_AI = "hybrid_ai"
    HYBRID_FALLBACK = "hybrid_fallback"


@dataclass
class DualPathResult(Generic[T]):
    """Result from a dual-path decision service.

    - result: the final output (always populated — deterministic fallback if needed)
    - decision_source: which path produced the result
    - ai_run_id: ID of the AI run if AI was used
    - ai_provider: provider name if AI was used
    - ai_model: model name if AI was used
    - used_ai: whether AI was used (successfully)
    - fallback_used: whether deterministic fallback was used (due to AI failure)
    - validation_errors: any validation errors from the AI path
    """
    result: T
    decision_source: DualPathDecisionSource
    ai_run_id: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    used_ai: bool = False
    fallback_used: bool = False
    validation_errors: list[str] = field(default_factory=list)
    prompt_used: str | None = None  # the final system prompt sent
    model_params: dict[str, Any] = field(default_factory=dict)  # temperature, max_tokens, etc.


class DualPathDecisionService(Generic[T]):
    """Base class for services that must support both deterministic and AI paths.

    Subclasses provide:
    - _deterministic_path(inputs) -> T
    - _ai_prompt(inputs) -> list[dict] (system + user messages)
    - _validate_ai_output(ai_result, inputs) -> list[str] (empty = valid)
    - _parse_ai_output(ai_json: dict, inputs) -> T
    """

    # Override in subclasses
    AGENT_ID: str = "dual_path_decision"
    AGENT_DISPLAY_NAME: str = "Dual-Path Decision"

    def decide(
        self,
        *,
        mode: AgentMode | str = AgentMode.HYBRID,
        deterministic_inputs: dict[str, Any],
        ai_client: Any | None = None,
        agent_config: dict | None = None,
    ) -> DualPathResult[T]:
        """Execute the dual-path decision.

        Args:
            mode: "deterministic", "ai", or "hybrid"
            deterministic_inputs: data needed for deterministic path
            ai_client: optional AI client (required for ai/hybrid modes)
            agent_config: optional agent configuration dict

        Returns:
            DualPathResult with the final result and metadata
        """
        mode_str = str(mode) if not isinstance(mode, AgentMode) else mode.value
        config = agent_config or {}

        # Deterministic path — always available
        if mode_str == AgentMode.DETERMINISTIC.value:
            result = self._deterministic_path(deterministic_inputs)
            return DualPathResult(
                result=result,
                decision_source=DualPathDecisionSource.DETERMINISTIC,
                used_ai=False,
                fallback_used=False,
            )

        # AI path — needs client
        if ai_client is None:
            # Fall back to deterministic if no AI client configured
            result = self._deterministic_path(deterministic_inputs)
            return DualPathResult(
                result=result,
                decision_source=DualPathDecisionSource.DETERMINISTIC,
                used_ai=False,
                fallback_used=True,
                validation_errors=["No AI client configured; used deterministic fallback."],
            )

        # Try AI path
        try:
            messages = self._ai_prompt(deterministic_inputs)
            provider = getattr(ai_client, "provider", "unknown")
            model = getattr(ai_client, "model", "unknown")

            response = ai_client.complete_json(messages=messages)
            ai_json = response.content_json if hasattr(response, "content_json") else response
            provider = getattr(response, "provider", provider)
            model = getattr(response, "model", model)
            used_ai = True

            validation_errors = self._validate_ai_output(ai_json, deterministic_inputs)

            if validation_errors:
                if mode_str == AgentMode.AI.value:
                    # Pure AI mode — return empty with errors
                    return DualPathResult(
                        result=self._empty_result(),
                        decision_source=DualPathDecisionSource.AI,
                        used_ai=False,
                        fallback_used=False,
                        validation_errors=validation_errors,
                    )
                # Hybrid mode — fall back to deterministic
                result = self._deterministic_path(deterministic_inputs)
                return DualPathResult(
                    result=result,
                    decision_source=DualPathDecisionSource.HYBRID_FALLBACK,
                    ai_provider=provider,
                    ai_model=model,
                    used_ai=False,
                    fallback_used=True,
                    validation_errors=validation_errors,
                )

            # AI success
            result = self._parse_ai_output(ai_json, deterministic_inputs)
            return DualPathResult(
                result=result,
                decision_source=DualPathDecisionSource.AI if mode_str == AgentMode.AI.value else DualPathDecisionSource.HYBRID_AI,
                ai_provider=provider,
                ai_model=model,
                used_ai=True,
                fallback_used=False,
            )

        except Exception as exc:
            error_msg = str(exc)
            if mode_str == AgentMode.AI.value:
                return DualPathResult(
                    result=self._empty_result(),
                    decision_source=DualPathDecisionSource.AI,
                    used_ai=False,
                    fallback_used=False,
                    validation_errors=[f"AI provider failed: {error_msg}"],
                )
            # Hybrid — fall back to deterministic
            result = self._deterministic_path(deterministic_inputs)
            return DualPathResult(
                result=result,
                decision_source=DualPathDecisionSource.HYBRID_FALLBACK,
                used_ai=False,
                fallback_used=True,
                validation_errors=[f"AI provider failed (deterministic fallback used): {error_msg}"],
            )

    # ------- Subclass overrides -------

    def _deterministic_path(self, inputs: dict[str, Any]) -> T:
        """Pure deterministic rule-based calculation. Must be implemented."""
        raise NotImplementedError

    def _ai_prompt(self, inputs: dict[str, Any]) -> list[dict[str, str]]:
        """Build system + user messages for the AI path. Must be implemented."""
        raise NotImplementedError

    def _validate_ai_output(self, ai_json: dict, inputs: dict[str, Any]) -> list[str]:
        """Validate AI output. Return empty list if valid."""
        return []

    def _parse_ai_output(self, ai_json: dict, inputs: dict[str, Any]) -> T:
        """Parse AI JSON output into the result type. Must be implemented."""
        raise NotImplementedError

    def _empty_result(self) -> T:
        """Return a safe empty/zero result for pure AI mode failure."""
        raise NotImplementedError


# Shared safety prompt snippet used by all AI paths
def safety_prompt_snippet() -> str:
    return (
        "SAFETY BOUNDARY: You are an assistant to a human operator. "
        "You may recommend, explain, and summarize — but you must NOT approve, "
        "reject, execute, export, or claim that any live Amazon Ads change has been made. "
        "Every output must include 'requires_human_approval': true and "
        "'executes_live_amazon_change': false. "
        "Do not bypass approval. Do not call Amazon Ads APIs. "
        "Do not claim the system has applied any change."
    )