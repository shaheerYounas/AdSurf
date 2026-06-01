from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.api.app.core.config import get_settings
from apps.api.app.core.observability import trace_llm_call
from apps.api.app.services.ai_client import AiConfigurationError, AiJsonClient, AiJsonResponse, AiProviderError, AiResponseError


class DeepSeekClient(AiJsonClient):
    provider = "deepseek"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, model: str | None = None, retries: int = 2) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.deepseek_api_key
        self._base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        self._retries = max(0, retries)

    def complete_json(self, *, messages: list[dict[str, str]], timeout_seconds: int | None = None) -> AiJsonResponse:
        if not self._api_key:
            raise AiConfigurationError("DEEPSEEK_API_KEY is not configured.")

        settings = get_settings()
        timeout = timeout_seconds or settings.ai_request_timeout_seconds
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        start = time.monotonic()
        last_error: Exception | None = None
        with trace_llm_call(
            provider=self.provider,
            model=self.model,
            messages_count=len(messages),
        ) as trace_span:
            for attempt in range(self._retries + 1):
                try:
                    request = Request(f"{self._base_url}/chat/completions", data=body, headers=headers, method="POST")
                    with urlopen(request, timeout=timeout) as response:
                        response_body = response.read().decode("utf-8")
                    content = self._extract_content(response_body)
                    parsed = self._parse_content_json(content)
                    result = AiJsonResponse(provider=self.provider, model=self.model, content_json=parsed, latency_ms=int((time.monotonic() - start) * 1000))
                    trace_span.set_attribute("latency_ms", result.latency_ms)
                    trace_span.set_attribute("attempts", attempt + 1)
                    trace_span.add_event("llm_response_received", latency_ms=result.latency_ms)
                    return result
                except HTTPError as exc:
                    last_error = exc
                    trace_span.add_event("llm_http_error", code=exc.code, attempt=attempt + 1)
                    if exc.code not in {408, 409, 425, 429, 500, 502, 503, 504} or attempt >= self._retries:
                        raise AiProviderError(f"DeepSeek request failed with status {exc.code}.") from exc
                except URLError as exc:
                    last_error = exc
                    trace_span.add_event("llm_network_error", attempt=attempt + 1)
                    if attempt >= self._retries:
                        raise AiProviderError("DeepSeek request failed due to a network error.") from exc
                except TimeoutError as exc:
                    last_error = exc
                    trace_span.add_event("llm_timeout", attempt=attempt + 1)
                    if attempt >= self._retries:
                        raise AiProviderError("DeepSeek request timed out.") from exc
                if attempt < self._retries:
                    time.sleep(min(2**attempt, 4))
            raise AiProviderError("DeepSeek request failed.") from last_error

    def _extract_content(self, response_body: str) -> str:
        try:
            data: dict[str, Any] = json.loads(response_body)
            return str(data["choices"][0]["message"]["content"])
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AiResponseError("DeepSeek response did not match the expected chat completion shape.") from exc

    def _parse_content_json(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(_json_object_text(content))
        except json.JSONDecodeError as exc:
            raise AiResponseError("DeepSeek response content was not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise AiResponseError("DeepSeek JSON response must be an object.")
        return parsed


def _json_object_text(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text
