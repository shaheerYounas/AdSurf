import json

import pytest

from apps.api.app.core.config import get_settings
from apps.api.app.services.ai_client import AiConfigurationError, AiResponseError
from apps.api.app.services.deepseek_client import DeepSeekClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_deepseek_client_returns_parsed_json(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return _FakeResponse({"choices": [{"message": {"content": json.dumps({"recommendations": [], "dashboard_summary": {"headline": "ok"}})}}]})

    monkeypatch.setattr("apps.api.app.services.deepseek_client.urlopen", fake_urlopen)

    response = DeepSeekClient(retries=0).complete_json(messages=[{"role": "user", "content": "{}"}], timeout_seconds=7)

    assert response.provider == "deepseek"
    assert response.model == "deepseek-chat"
    assert response.content_json["dashboard_summary"]["headline"] == "ok"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["timeout"] == 7


def test_deepseek_client_rejects_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_urlopen(request, timeout):
        return _FakeResponse({"choices": [{"message": {"content": "not json"}}]})

    monkeypatch.setattr("apps.api.app.services.deepseek_client.urlopen", fake_urlopen)

    with pytest.raises(AiResponseError):
        DeepSeekClient(retries=0).complete_json(messages=[{"role": "user", "content": "{}"}])


def test_deepseek_client_missing_key_fails_safely(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(AiConfigurationError) as error:
        DeepSeekClient(retries=0).complete_json(messages=[{"role": "user", "content": "{}"}])

    assert "DEEPSEEK_API_KEY" in str(error.value)
    assert "test-key" not in str(error.value)
