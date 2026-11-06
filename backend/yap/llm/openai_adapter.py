"""OpenAI through the official SDK (Responses API)."""

import httpx2
import openai

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


class OpenAIAdapter:
    def __init__(self, config: LlmConfig, http_client: httpx2.Client | None = None) -> None:
        self.model = config.model
        self.api_key = config.api_key
        self.client = openai.OpenAI(
            api_key=config.api_key, timeout=TIMEOUT, max_retries=1, http_client=http_client
        )

    def check(self) -> None:
        with _errors(self.model, self.api_key):
            self.client.models.retrieve(self.model)

    def generate(self, request: LlmRequest) -> str:
        with _errors(self.model, self.api_key):
            response = self.client.with_options(timeout=REVIEW_TIMEOUT).responses.create(
                model=self.model,
                instructions=request.system,
                input=request.prompt,
                tools=[{"type": "web_search"}] if request.web_search else [],
                max_output_tokens=MAX_OUTPUT_TOKENS,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "review",
                        "schema": request.json_schema,
                        "strict": True,
                    }
                },
            )
        if response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else None
            if reason == "content_filter":
                raise LlmError(msg("provider_declined", provider="OpenAI"))
            raise LlmError(msg("answer_too_long"))
        if not response.output_text:
            raise LlmError(msg("provider_no_answer", provider="OpenAI"))
        return response.output_text


class _errors:
    """Turns SDK errors into LlmError with a message safe to show."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: object, error: BaseException | None, tb: object) -> None:
        if isinstance(error, openai.APIStatusError):
            log_provider_error(
                "OpenAI", self.model, self.api_key, error, error.status_code, error.body
            )
        elif isinstance(error, openai.APIError):  # timeout or connection
            log_provider_error("OpenAI", self.model, self.api_key, error)
        if isinstance(error, openai.AuthenticationError):
            raise LlmError(msg("provider_rejected_key", provider="OpenAI")) from None
        if isinstance(error, openai.NotFoundError):
            raise LlmError(msg("provider_no_model", provider="OpenAI", model=self.model)) from None
        if isinstance(error, openai.APITimeoutError):
            raise LlmError(msg("provider_timeout", provider="OpenAI")) from None
        if isinstance(error, openai.APIConnectionError):
            raise LlmError(msg("provider_unreachable", provider="OpenAI")) from None
        if isinstance(error, openai.APIStatusError):
            raise status_error("OpenAI", error.status_code, body_detail(error.body)) from None
