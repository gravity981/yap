"""Anthropic (Claude) through the official SDK."""

import anthropic
import httpx2
from anthropic.types import (
    MessageParam,
    OutputConfigParam,
    ToolUnionParam,
    WebSearchTool20260209Param,
)

from yap.llm.base import (
    MAX_OUTPUT_TOKENS,
    REVIEW_TIMEOUT,
    TIMEOUT,
    LlmConfig,
    LlmError,
    LlmRequest,
    body_detail,
    log_provider_error,
    status_error,
)
from yap.messages import msg

# Web search with dynamic filtering (current models); runs on Anthropic's servers
WEB_SEARCH: WebSearchTool20260209Param = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 10,
}
# The server pauses a long search loop; it is resumed by sending the turn again
MAX_CONTINUATIONS = 5


class AnthropicAdapter:
    def __init__(self, config: LlmConfig, http_client: httpx2.Client | None = None) -> None:
        self.model = config.model
        self.api_key = config.api_key
        self.client = anthropic.Anthropic(
            api_key=config.api_key, timeout=TIMEOUT, max_retries=1, http_client=http_client
        )

    def check(self) -> None:
        with _errors(self.model, self.api_key):
            self.client.models.retrieve(self.model)

    def generate(self, request: LlmRequest) -> str:
        messages: list[MessageParam] = [{"role": "user", "content": request.prompt}]
        tools: list[ToolUnionParam] = [WEB_SEARCH] if request.web_search else []
        output: OutputConfigParam = {
            "format": {"type": "json_schema", "schema": request.json_schema}
        }
        with _errors(self.model, self.api_key):
            for _ in range(MAX_CONTINUATIONS + 1):
                response = self.client.with_options(timeout=REVIEW_TIMEOUT).messages.create(
                    model=self.model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=request.system,
                    messages=messages,
                    tools=tools,
                    output_config=output,
                )
                if response.stop_reason != "pause_turn":
                    break
                messages = [messages[0], {"role": "assistant", "content": response.content}]
            else:
                raise LlmError(msg("provider_search_unfinished", provider="Anthropic"))
        if response.stop_reason == "refusal":
            raise LlmError(msg("provider_declined", provider="Anthropic"))
        if response.stop_reason == "max_tokens":
            raise LlmError(msg("answer_too_long"))
        # The answer follows the last search; text blocks can be split around citations
        last_tool = max(
            (i for i, b in enumerate(response.content) if b.type not in ("text", "thinking")),
            default=-1,
        )
        texts: list[str] = [b.text for b in response.content[last_tool + 1 :] if b.type == "text"]
        if not "".join(texts).strip():
            raise LlmError(msg("provider_no_answer", provider="Anthropic"))
        return "".join(texts)


class _errors:
    """Turns SDK errors into LlmError with a message safe to show."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: object, error: BaseException | None, tb: object) -> None:
        if isinstance(error, anthropic.APIStatusError):
            log_provider_error(
                "Anthropic", self.model, self.api_key, error, error.status_code, error.body
            )
        elif isinstance(error, anthropic.APIError):  # timeout or connection
            log_provider_error("Anthropic", self.model, self.api_key, error)
        if isinstance(error, anthropic.AuthenticationError):
            raise LlmError(msg("provider_rejected_key", provider="Anthropic")) from None
        if isinstance(error, anthropic.NotFoundError):
            raise LlmError(
                msg("provider_no_model", provider="Anthropic", model=self.model)
            ) from None
        if isinstance(error, anthropic.APITimeoutError):
            raise LlmError(msg("provider_timeout", provider="Anthropic")) from None
        if isinstance(error, anthropic.APIConnectionError):
            raise LlmError(msg("provider_unreachable", provider="Anthropic")) from None
        if isinstance(error, anthropic.APIStatusError):
            raise status_error("Anthropic", error.status_code, body_detail(error.body)) from None
