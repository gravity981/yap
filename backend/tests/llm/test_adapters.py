"""Provider adapters against recorded HTTP responses (test strategy §6); no provider is
called."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from yap.llm import LlmConfig, LlmError, Provider, adapter_for
from yap.llm.anthropic_adapter import AnthropicAdapter
from yap.llm.base import LlmRequest
from yap.llm.google_adapter import GoogleAdapter
from yap.llm.openai_adapter import OpenAIAdapter

KEY = "sk-test-1234"

# Successful model lookups, as the providers answer them (shortened)
MODELS: dict[Provider, dict[str, Any]] = {
    Provider.ANTHROPIC: {
        "type": "model",
        "id": "claude-x",
        "display_name": "Claude X",
        "created_at": "2026-01-01T00:00:00Z",
    },
    Provider.OPENAI: {"id": "gpt-x", "object": "model", "created": 1, "owned_by": "openai"},
    Provider.GOOGLE: {"name": "models/gemini-x", "displayName": "Gemini X"},
}
ERRORS: dict[Provider, Callable[[int], dict[str, Any]]] = {
    Provider.ANTHROPIC: lambda status: {
        "type": "error",
        "error": {"type": "error", "message": f"status {status}"},
    },
    Provider.OPENAI: lambda status: {"error": {"message": f"status {status}", "type": "x"}},
    Provider.GOOGLE: lambda status: {"error": {"code": status, "message": "x", "status": "X"}},
}
ADAPTERS = {
    Provider.ANTHROPIC: AnthropicAdapter,
    Provider.OPENAI: OpenAIAdapter,
    Provider.GOOGLE: GoogleAdapter,
}


def adapter(provider: Provider, status: int, requests: list[httpx2.Request] | None = None) -> Any:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        body = MODELS[provider] if status == 200 else ERRORS[provider](status)
        return httpx2.Response(status, json=body)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return ADAPTERS[provider](LlmConfig(provider, "model-x", KEY), http_client=client)


@pytest.mark.req("REV-14")
@pytest.mark.parametrize("provider", list(Provider))
def test_check_looks_up_the_model_with_the_key(provider: Provider) -> None:
    requests: list[httpx2.Request] = []
    adapter(provider, 200, requests).check()
    assert len(requests) == 1
    request = requests[0]
    assert "model-x" in str(request.url)
    sent = " ".join(request.headers.values()) + str(request.url)
    assert KEY in sent


@pytest.mark.req("REV-14")
@pytest.mark.parametrize("provider", list(Provider))
@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "rejected the API key"), (404, "has no model model-x"), (500, "error 500")],
)
def test_check_reports_errors_without_the_key(
    provider: Provider, status: int, message: str
) -> None:
    with pytest.raises(LlmError, match=message) as err:
        adapter(provider, status).check()
    assert KEY not in str(err.value)


# Error answers as the providers send them when a model is overloaded
OVERLOADED: dict[Provider, tuple[int, dict[str, Any], str]] = {
    Provider.ANTHROPIC: (
        529,
        {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
        "Anthropic answered with error 529: overloaded_error Overloaded",
    ),
    Provider.OPENAI: (
        503,
        {"error": {"message": "The server is overloaded.", "type": "server_error"}},
        "OpenAI answered with error 503: server_error The server is overloaded.",
    ),
    Provider.GOOGLE: (
        503,
        {
            "error": {
                "code": 503,
                "message": "This model is currently experiencing high demand.\n"
                "Please try again later.",
                "status": "UNAVAILABLE",
            }
        },
        "Google answered with error 503: UNAVAILABLE This model is currently experiencing"
        " high demand. Please try again later.",
    ),
}


@pytest.mark.req("REV-08", "REV-14")
@pytest.mark.parametrize("provider", list(Provider))
def test_error_answers_show_the_providers_own_text(provider: Provider) -> None:
    status, body, message = OVERLOADED[provider]
    client = httpx2.Client(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(status, json=body))
    )
    instance = ADAPTERS[provider](LlmConfig(provider, "model-x", KEY), http_client=client)
    for call in (instance.check, lambda: instance.generate(request())):
        with pytest.raises(LlmError) as err:
            call()
        assert str(err.value) == message


# Quota answers with details the user does not see; the key in the text is made up so the
# test can check that it is removed
QUOTA: dict[Provider, dict[str, Any]] = {
    Provider.ANTHROPIC: {
        "type": "error",
        "error": {"type": "rate_limit_error", "message": f"Limit reached for key {KEY}"},
    },
    Provider.OPENAI: {
        "error": {
            "message": f"You exceeded your current quota (key {KEY})",
            "type": "insufficient_quota",
        }
    },
    Provider.GOOGLE: {
        "error": {
            "code": 429,
            "message": f"You exceeded your current quota (key {KEY})",
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}],
                }
            ],
        }
    },
}


@pytest.mark.req("REV-08", "REV-14")
@pytest.mark.parametrize("provider", list(Provider))
def test_error_answers_are_logged_completely_without_the_key(
    provider: Provider, caplog: pytest.LogCaptureFixture
) -> None:
    body = QUOTA[provider]
    client = httpx2.Client(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(429, json=body))
    )
    instance = ADAPTERS[provider](LlmConfig(provider, "model-x", KEY), http_client=client)
    with pytest.raises(LlmError):
        instance.check()
    [record] = [r for r in caplog.records if r.name == "yap.llm.base"]
    text = record.getMessage()
    assert record.levelname == "WARNING"
    assert "model-x" in text and "status 429" in text
    assert json.loads(text.split(": ", 1)[1])  # the complete answer
    assert KEY not in text
    if provider == Provider.GOOGLE:
        assert "GenerateRequestsPerDayPerProjectPerModel" in text


def test_long_provider_texts_are_shortened() -> None:
    from yap.llm.base import MAX_DETAIL, error_detail

    detail = error_detail("x" * 1000)
    assert len(detail) == MAX_DETAIL and detail.endswith("…")


@pytest.mark.req("REV-14")
@pytest.mark.parametrize("provider", list(Provider))
def test_unreachable_provider(provider: Provider, caplog: pytest.LogCaptureFixture) -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    client = httpx2.Client(transport=httpx2.MockTransport(fail))
    instance = ADAPTERS[provider](LlmConfig(provider, "model-x", KEY), http_client=client)
    with pytest.raises(LlmError, match="could not be reached"):
        instance.check()
    [record] = [r for r in caplog.records if r.name == "yap.llm.base"]
    assert "model-x" in record.getMessage()


@pytest.mark.req("REV-14")
@pytest.mark.parametrize("provider", list(Provider))
def test_adapter_for_picks_the_provider(provider: Provider) -> None:
    assert isinstance(adapter_for(LlmConfig(provider, "m", KEY)), ADAPTERS[provider])


def test_config_does_not_show_the_key() -> None:
    assert KEY not in repr(LlmConfig(Provider.OPENAI, "m", KEY))


# --- Review requests (REV-04, REV-05, REV-14) ------------------------------------------

ANSWER = '{"aspects": [], "suggestions": []}'
SCHEMA = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def request(web_search: bool = True) -> LlmRequest:
    return LlmRequest(system="system", prompt="prompt", json_schema=SCHEMA, web_search=web_search)


def replay(provider: Provider, *responses: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """An adapter whose provider answers with `responses` in turn; returns the sent bodies."""
    sent: list[dict[str, Any]] = []
    queue = list(responses)

    def handler(req: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(req.content))
        return httpx2.Response(200, json=queue.pop(0))

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return ADAPTERS[provider](LlmConfig(provider, "model-x", KEY), http_client=client), sent


def anthropic_message(stop_reason: str, *content: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "model-x",
        "content": list(content),
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


SEARCH = (
    {"type": "server_tool_use", "id": "srv_1", "name": "web_search", "input": {"query": "ETF"}},
    {
        "type": "web_search_tool_result",
        "tool_use_id": "srv_1",
        "content": [
            {
                "type": "web_search_result",
                "url": "https://news.example/etf",
                "title": "ETF inflows rise",
                "encrypted_content": "x",
                "page_age": None,
            }
        ],
    },
)


@pytest.mark.req("REV-04")
def test_anthropic_searches_and_returns_the_answer_after_the_search() -> None:
    adapter, sent = replay(
        Provider.ANTHROPIC,
        anthropic_message("pause_turn", *SEARCH),  # the server paused its search loop
        anthropic_message(
            "end_turn",
            {"type": "text", "text": "Let me look this up."},
            *SEARCH,
            {"type": "text", "text": ANSWER[:10]},
            {"type": "text", "text": ANSWER[10:]},
        ),
    )
    assert adapter.generate(request()) == ANSWER
    assert sent[0]["tools"][0]["type"] == "web_search_20260209"
    assert sent[0]["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    # The paused turn is sent again so the server continues it
    assert [m["role"] for m in sent[1]["messages"]] == ["user", "assistant"]


@pytest.mark.req("REV-05")
def test_anthropic_policy_review_has_no_tools() -> None:
    adapter, sent = replay(
        Provider.ANTHROPIC, anthropic_message("end_turn", {"type": "text", "text": ANSWER})
    )
    assert adapter.generate(request(web_search=False)) == ANSWER
    assert sent[0].get("tools", []) == []


@pytest.mark.req("REV-08")
@pytest.mark.parametrize(
    ("stop_reason", "message"), [("refusal", "declined"), ("max_tokens", "cut off")]
)
def test_anthropic_unusable_answers(stop_reason: str, message: str) -> None:
    adapter, _ = replay(
        Provider.ANTHROPIC, anthropic_message(stop_reason, {"type": "text", "text": "{"})
    )
    with pytest.raises(LlmError, match=message):
        adapter.generate(request())


def openai_response(status: str, text: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "model": "model-x",
        "status": status,
        "incomplete_details": {"reason": reason} if reason else None,
        "output": [
            {
                "type": "web_search_call",
                "id": "ws_1",
                "status": "completed",
                "action": {"type": "search", "query": "ETF"},
            },
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            },
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


@pytest.mark.req("REV-04")
def test_openai_searches_with_a_strict_schema() -> None:
    adapter, sent = replay(Provider.OPENAI, openai_response("completed", ANSWER))
    assert adapter.generate(request()) == ANSWER
    assert sent[0]["tools"] == [{"type": "web_search"}]
    assert sent[0]["text"]["format"]["strict"] is True
    assert sent[0]["instructions"] == "system"


@pytest.mark.req("REV-08")
@pytest.mark.parametrize(
    ("reason", "message"), [("content_filter", "declined"), ("max_output_tokens", "cut off")]
)
def test_openai_incomplete_answers(reason: str, message: str) -> None:
    adapter, _ = replay(Provider.OPENAI, openai_response("incomplete", "{", reason))
    with pytest.raises(LlmError, match=message):
        adapter.generate(request())


def gemini_response(text: str, finish: str = "STOP") -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish}
        ]
    }


@pytest.mark.req("REV-04")
def test_google_searches_with_the_schema_in_the_prompt() -> None:
    adapter, sent = replay(Provider.GOOGLE, gemini_response(ANSWER))
    assert adapter.generate(request()) == ANSWER
    body = sent[0]
    assert body["tools"] == [{"googleSearch": {}}]
    assert "responseJsonSchema" not in body.get("generationConfig", {})
    assert "JSON Schema" in body["contents"][0]["parts"][0]["text"]


@pytest.mark.req("REV-05")
def test_google_policy_review_uses_the_response_schema() -> None:
    adapter, sent = replay(Provider.GOOGLE, gemini_response(ANSWER))
    assert adapter.generate(request(web_search=False)) == ANSWER
    config = sent[0]["generationConfig"]
    assert (config["responseMimeType"], config["responseJsonSchema"]) == (
        "application/json",
        SCHEMA,
    )
    assert "tools" not in sent[0]


@pytest.mark.req("REV-04")
def test_google_review_with_the_sdk_own_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an injected client the SDK closes its own one when the genai client is
    garbage-collected; the review must still be sent ("client has been closed")."""
    import httpx
    from google.genai import _api_client

    sent: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(req)
        return httpx.Response(200, json=gemini_response(ANSWER))

    class MockedClient(_api_client.SyncHttpxClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(_api_client, "SyncHttpxClient", MockedClient)
    adapter = GoogleAdapter(LlmConfig(Provider.GOOGLE, "model-x", KEY))
    assert adapter.generate(request()) == ANSWER
    assert len(sent) == 1


@pytest.mark.req("REV-08")
def test_google_cut_off_answer() -> None:
    adapter, _ = replay(Provider.GOOGLE, gemini_response("{", "MAX_TOKENS"))
    with pytest.raises(LlmError, match="cut off"):
        adapter.generate(request())


@pytest.mark.req("REV-14")
def test_fake_provider_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from yap.api.app import create_app_from_env

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("LLM_FAKE", "1")
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError, match="LLM_FAKE"):
        create_app_from_env()


def test_fake_provider_answers_in_the_expected_format() -> None:
    from yap.domain.reviews import ReviewKind
    from yap.llm.fake import FakeAdapter
    from yap.services.review_prompts import _schema, parse_answer

    fake = FakeAdapter(LlmConfig(Provider.ANTHROPIC, "m", KEY))
    for kind in ReviewKind:
        schema = _schema(kind, "ID-1")
        request = LlmRequest("s", "p", schema, web_search=kind == ReviewKind.THESIS)
        assert len(parse_answer(kind, fake.generate(request), "ID-1").aspects) == 6
