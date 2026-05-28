from __future__ import annotations

import json
from typing import Any

from apps.api.app.core.config import get_settings
from apps.api.app.schemas.agent_control import AgentConfig
from apps.api.app.services.ai_client import AiConfigurationError, AiJsonClient
from apps.api.app.services.deepseek_client import DeepSeekClient
from apps.api.app.services.openai_compatible_client import OpenAICompatibleJsonClient


def build_agent_ai_client(*, agent_id: str, agent_config: AgentConfig | dict | None = None) -> AiJsonClient:
    settings = get_settings()
    config = _config_dict(agent_config)
    override = _agent_override(agent_id)
    provider = str(override.get("provider") or config.get("provider") or settings.ai_provider or "deepseek")
    model = override.get("model") or config.get("model")

    if provider == "deterministic":
        raise AiConfigurationError("deterministic provider does not call an AI API.")
    if provider == "deepseek":
        return DeepSeekClient(
            api_key=override.get("api_key") or settings.deepseek_api_key or (settings.ai_api_key if settings.ai_provider == "deepseek" else None),
            base_url=override.get("base_url") or settings.deepseek_base_url,
            model=model or override.get("model") or settings.deepseek_model,
        )
    if provider == "fallback":
        return OpenAICompatibleJsonClient(
            provider=settings.ai_fallback_provider or "fallback",
            api_key=override.get("api_key") or settings.ai_fallback_api_key,
            base_url=override.get("base_url") or settings.ai_fallback_base_url,
            model=model or override.get("model") or settings.ai_fallback_model,
        )
    if provider == "primary":
        return OpenAICompatibleJsonClient(
            provider=settings.ai_provider or "primary",
            api_key=override.get("api_key") or settings.ai_api_key,
            base_url=override.get("base_url") or _primary_base_url(),
            model=model or override.get("model") or settings.ai_default_model,
        )
    return OpenAICompatibleJsonClient(
        provider=provider,
        api_key=override.get("api_key") or settings.ai_api_key,
        base_url=override.get("base_url") or _primary_base_url(),
        model=model or override.get("model") or settings.ai_default_model,
    )


def available_backend_ai_providers() -> list[dict[str, Any]]:
    settings = get_settings()
    providers = [
        {"provider": "primary", "configured": bool(settings.ai_api_key and _primary_base_url()), "model": settings.ai_default_model},
        {"provider": "deepseek", "configured": bool(settings.deepseek_api_key or (settings.ai_provider == "deepseek" and settings.ai_api_key)), "model": settings.deepseek_model},
        {"provider": "fallback", "configured": bool(settings.ai_fallback_api_key and settings.ai_fallback_base_url), "model": settings.ai_fallback_model},
        {"provider": "deterministic", "configured": True, "model": "deterministic-rules"},
    ]
    for agent_id, override in _agent_overrides().items():
        providers.append(
            {
                "provider": override.get("provider", "custom"),
                "agent_id": agent_id,
                "configured": bool(override.get("api_key") and override.get("base_url")),
                "model": override.get("model"),
            }
        )
    return providers


def _config_dict(agent_config: AgentConfig | dict | None) -> dict:
    if agent_config is None:
        return {}
    if hasattr(agent_config, "model_dump"):
        return agent_config.model_dump(mode="json")
    return dict(agent_config)


def _agent_override(agent_id: str) -> dict:
    return _agent_overrides().get(agent_id, {})


def _agent_overrides() -> dict[str, dict]:
    raw = get_settings().agent_ai_config_json
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _primary_base_url() -> str | None:
    settings = get_settings()
    if settings.ai_base_url:
        return settings.ai_base_url
    if settings.ai_provider == "deepseek":
        return settings.deepseek_base_url
    return None
