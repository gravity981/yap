"""Provider-neutral interface of the LLM adapters."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from yap.messages import Message, msg

log = logging.getLogger(__name__)

# Network timeout for the connection test, in seconds
TIMEOUT = 30.0
# Reviews search the web and reason for a while; one provider request may take minutes
REVIEW_TIMEOUT = 600.0
MAX_OUTPUT_TOKENS = 16000


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


@dataclass(frozen=True)
class LlmConfig:
    """The complete LLM access of an AI reviewer; the key is decrypted only for the request."""

    provider: Provider
    model: str
    api_key: str = field(repr=False)


class LlmError(Exception):
    """A provider request failed; the message is safe to show to the user (no key) and has
    a code, so it can be shown in the user's language (NFR-10)."""

    def __init__(self, message: Message) -> None:
        super().__init__(str(message))
        self.message = message


MAX_DETAIL = 300  # characters of a provider's own error text shown to the user


def error_detail(*parts: object) -> str:
    """Joins the given parts of a provider's error text, on one line and shortened."""
    text = " ".join(" ".join(str(p) for p in parts if p not in (None, "")).split())
    return text if len(text) <= MAX_DETAIL else text[: MAX_DETAIL - 1] + "…"


def status_error(provider: str, status: int, detail: str) -> LlmError:
    """An error status with the provider's own text, e.g. for an overloaded model."""
    if detail:
        return LlmError(
            msg("provider_status_detail", provider=provider, status=status, detail=detail)
        )
    return LlmError(msg("provider_status", provider=provider, status=status))


def unexpected_detail(error: BaseException, secret: str) -> str:
    """Type and text of an error no adapter turned into an LlmError, so the user sees
    what happened; the key is removed in case the text contains it."""
    text = f"{type(error).__name__}: {error}"
    if secret:
        text = text.replace(secret, "***")
    return error_detail(text)


MAX_LOG = 4000  # characters of a provider's answer written to the server log


def log_provider_error(
    provider: str,
    model: str,
    secret: str,
    error: BaseException,
    status: int | None = None,
    body: object = None,
) -> None:
    """Logs a failed provider request with the provider's complete answer, e.g. which
    quota was exceeded; the user only sees a short message. The key is removed."""
    if body is not None:
        text = json.dumps(body, ensure_ascii=False, default=str)
    else:
        text = f"{type(error).__name__}: {error}"
    if secret:
        text = text.replace(secret, "***")
    if len(text) > MAX_LOG:
        text = text[: MAX_LOG - 1] + "…"
    log.warning(
        "LLM request to %s (model %s) failed%s: %s",
        provider,
        model,
        f" with status {status}" if status is not None else "",
        text,
    )


def body_detail(body: object) -> str:
    """Type and message from an error body like {"error": {"type": ..., "message": ...}}
    (Anthropic) or {"type": ..., "message": ...} (OpenAI)."""
    inner = body.get("error", body) if isinstance(body, dict) else None
    if not isinstance(inner, dict):
        return ""
    return error_detail(inner.get("type") or inner.get("status"), inner.get("message"))


@dataclass(frozen=True)
class LlmRequest:
    """One review request, the same for every provider (REV-14)."""

    system: str
    prompt: str
    json_schema: dict[str, Any]  # the answer must be one JSON object of this schema
    web_search: bool  # thesis reviews search the news (REV-04); policy reviews do not


class LlmAdapter(Protocol):
    def check(self) -> None:
        """Verifies that the key is accepted and the model exists; raises LlmError."""
        ...

    def generate(self, request: LlmRequest) -> str:
        """Runs the request, searching the web if asked, and returns the JSON answer
        as text; raises LlmError."""
        ...


AdapterFactory = Callable[[LlmConfig], LlmAdapter]


def adapter_for(config: LlmConfig) -> LlmAdapter:
    # Imported here, so only the SDK of the configured provider is loaded
    if config.provider == Provider.ANTHROPIC:
        from yap.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(config)
    if config.provider == Provider.OPENAI:
        from yap.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(config)
    from yap.llm.google_adapter import GoogleAdapter

    return GoogleAdapter(config)
