"""AdSurf Observability Layer — OpenTelemetry tracing + structured logging.

This module provides workspace-scoped tracing across all agent runs,
AI provider calls, and LangGraph workflow nodes. It is designed to be
provider-agnostic: the Tracer interface can back OpenTelemetry, LangSmith,
Braintrust, or a no-op stub with the same API surface.

Instrumentation points:
- complete_json on every AI provider client
- Every LangGraph node entry/exit
- DualPathDecisionService.decide
- Risk validator bulk runs
- Learning feedback cycles

Resource attributes on every span:
- service.name = "adsurf-api"
- workspace_id (UUID)
- agent_id (where applicable)
- decision_source (deterministic | ai | hybrid)

LangSmith Integration:
    Set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY=ls__...
    Set LANGCHAIN_PROJECT=adsurf-{env} to route traces per environment.

Braintrust Integration:
    Set BRAINTRUST_API_KEY=... and OBSERVABILITY_TRACING_MODE=braintrust.

Usage:
    from apps.api.app.core.observability import get_tracer, trace_ai_call

    tracer = get_tracer()
    with tracer.span("agent.run", workspace_id=str(ws_id), agent_id="bid_optimization_agent"):
        result = agent.decide(...)
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generator, Protocol

from apps.api.app.core.config import get_settings


# ── Context variables for implicit propagation ──────────────────────────
_current_workspace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_workspace_id", default=None
)
_current_agent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_agent_id", default=None
)
_current_workflow_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_workflow_id", default=None
)


def set_workspace_context(workspace_id: str | None) -> None:
    _current_workspace_id.set(workspace_id)


def get_workspace_context() -> str | None:
    return _current_workspace_id.get()


def set_agent_context(agent_id: str | None) -> None:
    _current_agent_id.set(agent_id)


def get_agent_context() -> str | None:
    return _current_agent_id.get()


def set_workflow_context(workflow_id: str | None) -> None:
    _current_workflow_id.set(workflow_id)


def get_workflow_context() -> str | None:
    return _current_workflow_id.get()


# ── Data types ──────────────────────────────────────────────────────────
class SpanKind(StrEnum):
    AGENT = "agent"
    LLM = "llm"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    FEEDBACK = "feedback"
    TOOL = "tool"


@dataclass
class SpanEvent:
    name: str
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """A single unit of traced work."""

    name: str
    kind: SpanKind
    workspace_id: str | None = None
    agent_id: str | None = None
    decision_source: str | None = None
    provider: str | None = None
    model: str | None = None
    start_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    end_ms: int | None = None
    status: str = "ok"
    events: list[SpanEvent] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    parent_span: "Span | None" = None
    # Token usage tracking
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def latency_ms(self) -> int:
        if self.end_ms is None:
            return int(time.time() * 1000) - self.start_ms
        return self.end_ms - self.start_ms

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append(SpanEvent(name=name, attributes=attrs))

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_token_usage(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        model: str = "",
    ) -> None:
        """Record token usage for cost attribution."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens or (input_tokens + output_tokens)
        self.set_attribute("input_tokens", input_tokens)
        self.set_attribute("output_tokens", output_tokens)
        self.set_attribute("total_tokens", self.total_tokens)
        self.set_attribute("model", model or self.model or "unknown")
        # Estimate cost based on model pricing
        self.cost_usd = _estimate_cost(
            model=model or self.model or "unknown",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.set_attribute("cost_usd", self.cost_usd)

    def finish(self, status: str = "ok") -> None:
        self.end_ms = int(time.time() * 1000)
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value if hasattr(self.kind, "value") else str(self.kind),
            "workspace_id": self.workspace_id,
            "agent_id": self.agent_id,
            "decision_source": self.decision_source,
            "provider": self.provider,
            "model": self.model,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "events": [
                {"name": e.name, "timestamp_ms": e.timestamp_ms, "attributes": e.attributes}
                for e in self.events
            ],
            "attributes": self.attributes,
        }


# ── Cost estimation per model ───────────────────────────────────────────
# Pricing in USD per 1M tokens (input, output)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "claude-3.5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    "FRE-5.5": (0.0, 0.0),  # Free tier
}


def _estimate_cost(*, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for token usage based on model pricing."""
    model_lower = model.lower()
    # Try exact match first, then partial
    pricing = _MODEL_PRICING.get(model_lower)
    if pricing is None:
        for key, val in _MODEL_PRICING.items():
            if key in model_lower or model_lower in key:
                pricing = val
                break
    if pricing is None:
        pricing = (0.5, 2.0)  # Conservative default

    input_price_per_m, output_price_per_m = pricing
    cost = (input_tokens / 1_000_000) * input_price_per_m + (
        output_tokens / 1_000_000
    ) * output_price_per_m
    return round(cost, 6)


class Tracer(Protocol):
    """Minimal tracer interface. Backed by OpenTelemetry, LangSmith, Braintrust,
    or the NoopTracer stub. All work the same way."""

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.AGENT,
        workspace_id: str | None = None,
        agent_id: str | None = None,
        decision_source: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Generator[Span, None, None]:
        ...

    def create_span(self, **kwargs: Any) -> Span:
        ...

    def flush(self) -> None:
        """Export pending spans to the backend."""
        ...


# ── Concrete implementations ────────────────────────────────────────────


class NoopTracer:
    """No-op tracer for local dev / testing. Spans are collected in memory
    for the last N spans (useful for debugging)."""

    MAX_STORED = 500

    def __init__(self) -> None:
        self._spans: list[Span] = []

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.AGENT,
        workspace_id: str | None = None,
        agent_id: str | None = None,
        decision_source: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Generator[Span, None, None]:
        ws = workspace_id or get_workspace_context()
        ag = agent_id or get_agent_context()
        s = Span(
            name=name,
            kind=kind,
            workspace_id=ws,
            agent_id=ag,
            decision_source=decision_source,
            provider=provider,
            model=model,
        )
        try:
            yield s
        finally:
            s.finish(status="ok")
            self._spans.append(s)
            if len(self._spans) > self.MAX_STORED:
                self._spans = self._spans[-self.MAX_STORED:]

    def create_span(self, **kwargs: Any) -> Span:
        return Span(**kwargs)

    def recent_spans(self, n: int = 20) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._spans[-n:]]

    def flush(self) -> None:
        """No-op in memory mode."""


class ConsoleTracer(NoopTracer):
    """Prints span summaries to stdout for development visibility."""

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.AGENT,
        workspace_id: str | None = None,
        agent_id: str | None = None,
        decision_source: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Generator[Span, None, None]:
        import sys

        ws = workspace_id or get_workspace_context()
        ag = agent_id or get_agent_context()
        tag = f"[{kind.value}] ws={ws} agent={ag} {name}"
        print(f"▶ {tag}", file=sys.stderr)
        t0 = time.time()
        s = Span(
            name=name,
            kind=kind,
            workspace_id=ws,
            agent_id=ag,
            decision_source=decision_source,
            provider=provider,
            model=model,
        )
        try:
            yield s
        except Exception:
            s.finish(status="error")
            elapsed = (s.end_ms or 0) - s.start_ms
            print(
                f"✗ {tag} ERROR {elapsed}ms tokens={s.total_tokens} cost=${s.cost_usd:.4f}",
                file=sys.stderr,
            )
            self._spans.append(s)
            raise
        else:
            s.finish(status="ok")
            elapsed = s.latency_ms
            print(
                f"✓ {tag} ok {elapsed}ms tokens={s.total_tokens} cost=${s.cost_usd:.4f}",
                file=sys.stderr,
            )
            self._spans.append(s)
            if len(self._spans) > self.MAX_STORED:
                self._spans = self._spans[-self.MAX_STORED:]


class LangSmithTracer(NoopTracer):
    """LangSmith-compatible tracer via the LangSmith SDK.

    Install: pip install langsmith
    Configure: LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY=ls__...
               LANGCHAIN_PROJECT=adsurf-{env}

    Falls back to ConsoleTracer if langsmith is not installed.
    """

    def __init__(self) -> None:
        super().__init__()
        self._ls_client = None
        self._enabled = False
        try:
            import langsmith as ls

            if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true" and os.getenv(
                "LANGCHAIN_API_KEY"
            ):
                self._ls_client = ls.Client()
                self._enabled = True
        except ImportError:
            pass

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.AGENT,
        workspace_id: str | None = None,
        agent_id: str | None = None,
        decision_source: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Generator[Span, None, None]:
        ws = workspace_id or get_workspace_context()
        ag = agent_id or get_agent_context()

        if self._enabled and self._ls_client:
            try:
                import langsmith as ls

                run = self._ls_client.create_run(
                    name=name,
                    run_type={
                        SpanKind.LLM: "llm",
                        SpanKind.AGENT: "chain",
                        SpanKind.WORKFLOW: "chain",
                        SpanKind.VALIDATION: "tool",
                        SpanKind.FEEDBACK: "tool",
                        SpanKind.TOOL: "tool",
                    }.get(kind, "chain"),
                    inputs={},
                    tags=[kind.value],
                    metadata={
                        "workspace_id": ws or "unknown",
                        "agent_id": ag or "unknown",
                        "decision_source": decision_source or "unknown",
                    },
                )
            except Exception:
                run = None
        else:
            run = None

        s = Span(
            name=name,
            kind=kind,
            workspace_id=ws,
            agent_id=ag,
            decision_source=decision_source,
            provider=provider,
            model=model,
        )
        try:
            yield s
        except Exception:
            s.finish(status="error")
            if run and self._ls_client:
                try:
                    self._ls_client.update_run(
                        run.id,
                        outputs={"error": str(s.status)},
                        end_time=int(time.time() * 1000),
                        error=str(s.status),
                    )
                except Exception:
                    pass
            self._spans.append(s)
            raise
        else:
            s.finish(status="ok")
            if run and self._ls_client:
                try:
                    self._ls_client.update_run(
                        run.id,
                        outputs=s.to_dict(),
                        end_time=int(time.time() * 1000),
                    )
                except Exception:
                    pass
            self._spans.append(s)
            if len(self._spans) > self.MAX_STORED:
                self._spans = self._spans[-self.MAX_STORED:]


class BraintrustTracer(NoopTracer):
    """Braintrust-compatible tracer.

    Install: pip install braintrust
    Configure: BRAINTRUST_API_KEY=...

    Falls back to ConsoleTracer if braintrust is not installed.
    """

    def __init__(self) -> None:
        super().__init__()
        self._bt_logger = None
        self._enabled = False
        try:
            import braintrust

            if os.getenv("BRAINTRUST_API_KEY"):
                self._bt_logger = braintrust.init_logger(
                    project=os.getenv("BRAINTRUST_PROJECT", "adsurf")
                )
                self._enabled = True
        except ImportError:
            pass

    @contextmanager
    def span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.AGENT,
        workspace_id: str | None = None,
        agent_id: str | None = None,
        decision_source: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> Generator[Span, None, None]:
        ws = workspace_id or get_workspace_context()
        ag = agent_id or get_agent_context()
        s = Span(
            name=name,
            kind=kind,
            workspace_id=ws,
            agent_id=ag,
            decision_source=decision_source,
            provider=provider,
            model=model,
        )
        bt_span = None
        if self._enabled and self._bt_logger:
            try:
                bt_span = self._bt_logger.start_span(
                    name=name,
                    metadata={
                        "kind": kind.value,
                        "workspace_id": ws,
                        "agent_id": ag,
                    },
                )
            except Exception:
                bt_span = None

        try:
            yield s
        except Exception:
            s.finish(status="error")
            if bt_span:
                try:
                    bt_span.log(
                        output={"error": True},
                        metrics={"latency_ms": s.latency_ms},
                    )
                except Exception:
                    pass
            self._spans.append(s)
            raise
        else:
            s.finish(status="ok")
            if bt_span:
                try:
                    bt_span.log(
                        output=s.to_dict(),
                        metrics={
                            "latency_ms": s.latency_ms,
                            "input_tokens": s.input_tokens,
                            "output_tokens": s.output_tokens,
                            "total_tokens": s.total_tokens,
                            "cost_usd": s.cost_usd,
                        },
                    )
                except Exception:
                    pass
            self._spans.append(s)
            if len(self._spans) > self.MAX_STORED:
                self._spans = self._spans[-self.MAX_STORED:]


# ── Singleton ────────────────────────────────────────────────────────────
_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    """Return the configured tracer. Supports langsmith, braintrust, console,
    and silent (noop) modes.

    Environment variables:
        OBSERVABILITY_TRACING_MODE: langsmith | braintrust | console | silent
        LANGCHAIN_TRACING_V2: true
        LANGCHAIN_API_KEY: ls__...
        LANGCHAIN_PROJECT: adsurf-{env}
        BRAINTRUST_API_KEY: ...
    """
    global _tracer
    if _tracer is not None:
        return _tracer

    settings = get_settings()
    tracing_mode = settings.observability_tracing_mode or "console"

    # Auto-detect LangSmith if env vars are set
    if tracing_mode == "langsmith" or (
        os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
        and os.getenv("LANGCHAIN_API_KEY")
    ):
        _tracer = LangSmithTracer()
        return _tracer

    if tracing_mode == "braintrust":
        _tracer = BraintrustTracer()
        return _tracer

    if tracing_mode == "console":
        _tracer = ConsoleTracer()
        return _tracer

    if tracing_mode == "silent":
        _tracer = NoopTracer()
        return _tracer

    # Default to console for dev visibility
    _tracer = ConsoleTracer()
    return _tracer


def reset_tracer(t: Tracer | None = None) -> None:
    global _tracer
    _tracer = t


# ── Convenience decorator / context helpers ─────────────────────────────


def trace_agent_node(node_name: str):
    """Decorator for LangGraph node functions to automatically trace
    entry/exit with workspace and agent context."""

    def decorator(func):
        def wrapper(state, context, *args, **kwargs):
            tracer = get_tracer()
            ws = None
            ag = None
            if hasattr(state, "get"):
                ws = state.get("workspace_id")
                ag = state.get("current_agent_id")
            with tracer.span(
                f"node.{node_name}",
                kind=SpanKind.WORKFLOW,
                workspace_id=str(ws) if ws else None,
                agent_id=str(ag) if ag else None,
            ) as span:
                try:
                    result = func(state, context, *args, **kwargs)
                    if hasattr(result, "get"):
                        span.set_attribute("status", result.get("status", "unknown"))
                        recs = result.get("recommendations", [])
                        span.set_attribute("recommendations_count", len(recs) if recs else 0)
                    span.add_event("node_completed")
                    return result
                except Exception as exc:
                    span.add_event("node_failed", error=str(exc))
                    span.finish(status="error")
                    raise

        return wrapper

    return decorator


@contextmanager
def trace_llm_call(
    *,
    provider: str,
    model: str,
    workspace_id: str | None = None,
    agent_id: str | None = None,
    prompt_hash: str | None = None,
    messages_count: int = 0,
) -> Generator[Span, None, None]:
    """Trace a single LLM API call with workspace attribution and token tracking."""
    tracer = get_tracer()
    ws = workspace_id or get_workspace_context()
    ag = agent_id or get_agent_context()
    with tracer.span(
        f"llm.{provider}.complete_json",
        kind=SpanKind.LLM,
        workspace_id=ws,
        agent_id=ag,
        provider=provider,
        model=model,
    ) as span:
        span.set_attribute("provider", provider)
        span.set_attribute("model", model)
        span.set_attribute("messages_count", messages_count)
        if prompt_hash:
            span.set_attribute("prompt_hash", prompt_hash)
        span.add_event("llm_call_started")
        try:
            yield span
        except Exception as exc:
            span.add_event("llm_call_failed", error=str(exc))
            span.finish(status="error")
            raise
        else:
            span.add_event("llm_call_completed")


def trace_risk_validation(
    *,
    workspace_id: str | None = None,
    total_recommendations: int = 0,
) -> Generator[Span, None, None]:
    """Trace a bulk risk validation run."""
    tracer = get_tracer()
    ws = workspace_id or get_workspace_context()
    with tracer.span(
        "risk_validator.validate_bulk",
        kind=SpanKind.VALIDATION,
        workspace_id=ws,
    ) as span:
        span.set_attribute("total_input", total_recommendations)
        yield span


def trace_learning_feedback(
    *,
    workspace_id: str | None = None,
    product_id: str | None = None,
    total_recommendations: int = 0,
) -> Generator[Span, None, None]:
    """Trace a learning feedback cycle."""
    tracer = get_tracer()
    ws = workspace_id or get_workspace_context()
    with tracer.span(
        "learning_feedback.analyze_outcomes",
        kind=SpanKind.FEEDBACK,
        workspace_id=ws,
    ) as span:
        span.set_attribute("product_id", product_id or "unknown")
        span.set_attribute("total_input", total_recommendations)
        yield span


# ── Token usage tracking ────────────────────────────────────────────────
# Per-workspace token accumulator for cost attribution

_workspace_token_usage: dict[str, dict[str, Any]] = {}


def record_workspace_token_usage(
    *,
    workspace_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = "unknown",
    cost_usd: float = 0.0,
) -> None:
    """Record token usage for a workspace for cost attribution."""
    if not workspace_id:
        return

    ws_stats = _workspace_token_usage.setdefault(
        workspace_id,
        {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "calls": 0,
            "models": {},
        },
    )
    ws_stats["total_input_tokens"] += input_tokens
    ws_stats["total_output_tokens"] += output_tokens
    ws_stats["total_cost_usd"] += cost_usd
    ws_stats["calls"] += 1

    model_stats = ws_stats["models"].setdefault(
        model,
        {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0},
    )
    model_stats["input_tokens"] += input_tokens
    model_stats["output_tokens"] += output_tokens
    model_stats["cost_usd"] += cost_usd
    model_stats["calls"] += 1


def get_workspace_token_usage(workspace_id: str) -> dict[str, Any]:
    """Get token usage stats for a specific workspace."""
    return _workspace_token_usage.get(workspace_id, {})


def get_all_token_usage() -> dict[str, Any]:
    """Get token usage across all workspaces."""
    return {
        "workspaces": dict(_workspace_token_usage),
        "total_workspaces": len(_workspace_token_usage),
        "total_cost_usd": sum(
            ws.get("total_cost_usd", 0.0)
            for ws in _workspace_token_usage.values()
        ),
        "total_calls": sum(
            ws.get("calls", 0) for ws in _workspace_token_usage.values()
        ),
    }


def reset_token_usage(workspace_id: str | None = None) -> None:
    """Reset token usage stats, optionally for a single workspace."""
    global _workspace_token_usage
    if workspace_id:
        _workspace_token_usage.pop(workspace_id, None)
    else:
        _workspace_token_usage = {}


# ── Prompt hashing for regression detection ─────────────────────────────


def hash_prompt(system_prompt: str, user_prompt: str = "") -> str:
    """Create a stable hash of a prompt for regression testing."""
    content = system_prompt + "\n---\n" + user_prompt
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def hash_messages(messages: list[dict[str, str]]) -> str:
    """Create a stable hash of a full messages array."""
    content = json.dumps(messages, sort_keys=True, default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]