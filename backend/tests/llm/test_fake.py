"""The stand-in provider of the end-to-end tests (test strategy §2, §6)."""

import json

from yap.llm.base import LlmConfig, LlmRequest, Provider
from yap.llm.fake import BROKEN_MARKER, FakeAdapter


def _answer(prompt: str) -> dict[str, object]:
    schema = {
        "properties": {
            "prompt_id": {"enum": ["p1"]},
            "aspects": {"items": {"properties": {"code": {"enum": ["T1", "T2"]}}}},
        }
    }
    config = LlmConfig(Provider.ANTHROPIC, "fake", "k")
    request = LlmRequest(system="", prompt=prompt, json_schema=schema, web_search=True)
    answer: dict[str, object] = json.loads(FakeAdapter(config).generate(request))
    return answer


def test_the_fake_reviewer_finds_a_marked_thesis_broken() -> None:
    assert _answer("A thesis")["verdict"] == "good"
    broken = _answer(f"A thesis {BROKEN_MARKER}")
    assert broken["verdict"] == "broken"
    assert "break condition" in str(broken["verdict_reason"])
