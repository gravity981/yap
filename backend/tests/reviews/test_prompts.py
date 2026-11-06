"""Instructions sent to the LLM and validation of its answer."""

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from tests.reviews.answers import policy_answer, thesis_answer
from yap.domain.reviews import ReviewKind, Verdict
from yap.llm import LlmError
from yap.services import review_prompts, snapshots
from yap.services.snapshots import ValueSpec


def _walk(schema: object) -> list[dict[str, object]]:
    found = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            found.append(schema)
        for value in schema.values():
            found.extend(_walk(value))
    elif isinstance(schema, list):
        for value in schema:
            found.extend(_walk(value))
    return found


@pytest.mark.req("REV-14")
@pytest.mark.parametrize("kind", list(ReviewKind))
def test_answer_schema_is_strict_for_all_providers(kind: ReviewKind) -> None:
    schema = review_prompts._schema(kind)
    for obj in _walk(schema):
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])  # type: ignore[call-overload]
    assert ("verdict" in schema["properties"]) == (kind == ReviewKind.THESIS)


@pytest.mark.req("REV-02", "REV-03", "REV-04")
def test_a_thesis_answer_is_parsed() -> None:
    parsed = review_prompts.parse_answer(ReviewKind.THESIS, f"```json\n{thesis_answer()}\n```")
    assert [(a.code, a.half_points) for a in parsed.aspects][:2] == [("T1", 14), ("T2", 12)]
    assert parsed.verdict == Verdict.NEEDS_ADAPTATION
    assert parsed.sources[0].url == "https://news.example/etf"
    assert parsed.suggestions[0].kind == "thesis_text"


@pytest.mark.req("REV-08")
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "expected format"),
        (thesis_answer(verdict="soft"), "expected format"),
        (thesis_answer(scores=(7, 6, 8, 5, 7)), "exactly the aspects"),
        (thesis_answer(scores=(7, 6, 8, 5, 7, 6.3)), "steps of 0.5"),
        (thesis_answer(scores=(7, 6, 8, 5, 7, 11)), "between 0 and 10"),
        (thesis_answer(extra_field=1), "expected format"),
        (policy_answer(), "expected format"),  # a policy answer to a thesis review
    ],
)
def test_invalid_answers_are_rejected(text: str, message: str) -> None:
    with pytest.raises(LlmError, match=message):
        review_prompts.parse_answer(ReviewKind.THESIS, text)


@pytest.mark.req("REV-04", "NFR-01")
def test_thesis_request_searches_news_of_the_period(session: Session, factory: Factory) -> None:
    owner = factory.investor("alice")
    revision = factory.thesis(owner, title="Growth").revisions[0]
    request = review_prompts.thesis_request(revision, date(2025, 10, 17), date(2026, 1, 15))
    assert request.web_search is True
    assert "2025-10-17" in request.system and "2026-01-15" in request.system
    assert "Title: Growth" in request.prompt and "# Thesis" in request.prompt
    assert "alice" not in request.system + request.prompt


@pytest.mark.req("REV-05", "NFR-01")
def test_policy_request_has_thesis_and_structure_but_no_amounts(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor("alice")
    policy = factory.active_policy(owner, [spec("XUS", 60), spec("ETH", 40)], name="Retirement")
    portfolio = factory.portfolio(owner, policy)
    snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, [ValueSpec("XUS", Decimal("12345.67"))]
    )
    request = review_prompts.policy_request(policy.versions[0])
    text = request.system + request.prompt
    assert request.web_search is False
    assert "| XUS | XUS name | ETF | 60 | -20 | 20 | no |" in text
    assert "# Thesis" in text
    for private in ("12345", "alice", portfolio.name, "Retirement"):
        assert private not in text
    json.dumps(request.json_schema)  # serializable for every provider
