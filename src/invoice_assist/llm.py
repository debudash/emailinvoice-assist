"""The LLM seam: one place that knows how we call Claude.

Uses the Anthropic SDK directly (see ADR-0008): native structured outputs via
messages.parse, and the SDK tool runner for the context agent. Opus 5.5 rejects
temperature and forced tool_choice, so neither is ever sent; depth is set with effort.
Server-side refusal fallbacks are on, so a policy decline is re-run on Anthropic's
recommended fallback model instead of failing the Stage.
"""
import os
from contextvars import ContextVar
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import settings

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Models that actually served this Stage's calls; differs from settings.model only when a
# refusal fallback ran. The Pipeline records it on the Stage Run so evals can attribute results.
served_by: ContextVar[list[str] | None] = ContextVar("served_by", default=None)


def record_served(model: str) -> None:
    models = served_by.get()
    if models is not None and model not in models:
        models.append(model)


class LLMRefusal(RuntimeError):
    """The model (and its fallback) declined; the Stage fails rather than guessing."""


def _wrap(client):
    if os.getenv("LANGSMITH_API_KEY"):
        from langsmith.wrappers import wrap_anthropic
        return wrap_anthropic(client)
    return client


def client() -> anthropic.Anthropic:
    return _wrap(anthropic.Anthropic())


def async_client() -> anthropic.AsyncAnthropic:
    return _wrap(anthropic.AsyncAnthropic())


def parse(output: type[T], system: str, content: list[dict], effort: str = "medium",
          max_tokens: int = 16000) -> T:
    """One structured call: returns a validated instance of `output`."""
    response = client().beta.messages.parse(
        model=settings.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=output,
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise LLMRefusal(str(response.stop_details))
    record_served(response.model)
    return response.parsed_output
