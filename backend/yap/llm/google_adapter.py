"""Google (Gemini) through the official SDK."""

import json

import httpx
import httpx2
from google import genai
from google.genai import errors, types

from yap.llm.base import (
    MAX_OUTPUT_TOKENS,
    REVIEW_TIMEOUT,
    TIMEOUT,
    LlmConfig,
    LlmError,
    LlmRequest,
    error_detail,
    log_provider_error,
    status_error,
)
from yap.messages import msg


class GoogleAdapter:
    def __init__(self, config: LlmConfig, http_client: httpx2.Client | None = None) -> None:
        self.model = config.model
        self.api_key = config.api_key
        self.http_client = http_client
        self.client = self._client(TIMEOUT)

    def _client(self, timeout: float) -> genai.Client:
        return genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout * 1000), httpx_client=self.http_client
            ),
        )

    def check(self) -> None:
        with _errors(self.model, self.api_key):
            self.client.models.get(model=self.model)

    def generate(self, request: LlmRequest) -> str:
        if request.web_search:
            # Google Search grounding and a response schema cannot be combined on every
            # model, so the schema goes into the prompt; the answer is validated afterwards.
            config = types.GenerateContentConfig(
                system_instruction=request.system,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
            prompt = (
                f"{request.prompt}\n\nAnswer with exactly one JSON object, without any "
                f"other text, that follows this JSON Schema:\n{json.dumps(request.json_schema)}"
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=request.system,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
                response_json_schema=request.json_schema,
            )
            prompt = request.prompt
        # Kept in a with block: an unreferenced client closes its HTTP client when it is
        # garbage-collected, before the request is sent
        with _errors(self.model, self.api_key), self._client(REVIEW_TIMEOUT) as client:
            response = client.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
        candidate = response.candidates[0] if response.candidates else None
        reason = candidate.finish_reason if candidate else None
        if reason == types.FinishReason.MAX_TOKENS:
            raise LlmError(msg("answer_too_long"))
        if reason is not None and reason != types.FinishReason.STOP:
            raise LlmError(msg("provider_stopped", provider="Google", reason=str(reason.value)))
        if not response.text:
            raise LlmError(msg("provider_no_answer", provider="Google"))
        return response.text


class _errors:
    """Turns SDK errors into LlmError with a message safe to show."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: object, error: BaseException | None, tb: object) -> None:
        if isinstance(error, errors.APIError):
            log_provider_error("Google", self.model, self.api_key, error, error.code, error.details)
            # An invalid key is a 400 at Google, a missing permission a 401 or 403
            if error.code in (401, 403) or "API key" in (error.message or ""):
                raise LlmError(msg("provider_rejected_key", provider="Google")) from None
            if error.code == 404:
                raise LlmError(
                    msg("provider_no_model", provider="Google", model=self.model)
                ) from None
            detail = error_detail(error.status, error.message)
            raise status_error("Google", error.code, detail) from None
        # The SDK uses httpx or httpx2, depending on the request path
        if isinstance(error, httpx.TransportError | httpx2.TransportError):
            log_provider_error("Google", self.model, self.api_key, error)
        if isinstance(error, httpx.TimeoutException | httpx2.TimeoutException):
            raise LlmError(msg("provider_timeout", provider="Google")) from None
        if isinstance(error, httpx.TransportError | httpx2.TransportError):
            raise LlmError(msg("provider_unreachable", provider="Google")) from None
