from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class AiClientError(Exception):
    """Base error for AI provider failures. Messages must not contain secrets."""


class AiConfigurationError(AiClientError):
    pass


class AiProviderError(AiClientError):
    pass


class AiResponseError(AiClientError):
    pass


@dataclass(frozen=True)
class AiJsonResponse:
    provider: str
    model: str
    content_json: dict[str, Any]
    latency_ms: int


class AiJsonClient(ABC):
    provider: str
    model: str

    @abstractmethod
    def complete_json(self, *, messages: list[dict[str, str]], timeout_seconds: int | None = None) -> AiJsonResponse:
        raise NotImplementedError
