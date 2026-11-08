"""Instructions sent to the LLM and validation of its answer."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from tests.reviews.answers import PROMPT_ID, policy_answer, thesis_answer
from yap.domain.reviews import ReviewKind, Verdict
from yap.llm import LlmError
from yap.services import review_prompts, snapshots
from yap.services.snapshots import ValueSpec


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 10, 0, tzinfo=UTC)


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
    schema = review_prompts._schema(kind, PROMPT_ID)
    assert schema["properties"]["prompt_id"] == {"type": "string", "enum": [PROMPT_ID]}
    for obj in _walk(schema):
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])  # type: ignore[call-overload]
    assert ("verdict" in schema["properties"]) == (kind == ReviewKind.THESIS)


@pytest.mark.req("REV-02", "REV-03", "REV-04")
def test_a_thesis_answer_is_parsed() -> None:
    answer = thesis_answer(prompt_id=PROMPT_ID)
    parsed = review_prompts.parse_answer(ReviewKind.THESIS, f"```json\n{answer}\n```", PROMPT_ID)
    assert [(a.code, a.half_points) for a in parsed.aspects][:2] == [("T1", 14), ("T2", 12)]
    assert parsed.verdict == Verdict.NEEDS_ADAPTATION
    assert parsed.sources[0].url == "https://news.example/etf"
    assert parsed.suggestions[0].kind == "thesis_text"


@pytest.mark.req("REV-08")
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "no JSON object"),
        ('{"prompt_id": "x",}', "no valid JSON: Illegal trailing comma"),
        (thesis_answer(verdict="soft", prompt_id=PROMPT_ID), "verdict: Input should be"),
        (thesis_answer(scores=(7, 6, 8, 5, 7), prompt_id=PROMPT_ID), "exactly the aspects"),
        (thesis_answer(scores=(7, 6, 8, 5, 7, 6.3), prompt_id=PROMPT_ID), "steps of 0.5"),
        (thesis_answer(scores=(7, 6, 8, 5, 7, 11), prompt_id=PROMPT_ID), "between 0 and 10"),
        (thesis_answer(extra_field=1, prompt_id=PROMPT_ID), "extra_field: Extra inputs"),
        # a policy answer to a thesis review
        (policy_answer(prompt_id=PROMPT_ID), "verdict: Field required"),
        (thesis_answer(), "prompt_id: Field required"),
        (thesis_answer(prompt_id="T1-20260115T100000Z-90-ffffff"), "prompt ID " + PROMPT_ID),
    ],
)
def test_invalid_answers_are_rejected(text: str, message: str) -> None:
    with pytest.raises(LlmError, match=message):
        review_prompts.parse_answer(ReviewKind.THESIS, text, PROMPT_ID)


@pytest.mark.req("REV-04", "NFR-01")
def test_thesis_request_searches_news_of_the_period(session: Session, factory: Factory) -> None:
    owner = factory.investor("alice")
    revision = factory.policy_draft(owner, thesis_title="Growth").versions[0]
    ref = review_prompts.PromptRef(ReviewKind.THESIS, revision.id, _at(2026, 1, 15), 90)
    request = review_prompts.thesis_prompt(revision, ref).llm_request()
    assert request.web_search is True
    assert "2025-10-17" in request.system and "2026-01-15" in request.system
    assert "Title: Growth" in request.prompt and "# Thesis" in request.prompt
    assert "alice" not in request.system + request.prompt


@pytest.mark.req("REV-02", "REV-06", "THS-07")
def test_thesis_request_judges_the_sections_of_the_template(
    session: Session, factory: Factory
) -> None:
    revision = factory.policy_draft(factory.investor()).versions[0]
    ref = review_prompts.PromptRef(ReviewKind.THESIS, revision.id, _at(2026, 1, 15), 14)
    system = review_prompts.thesis_prompt(revision, ref).instructions
    assert "1 Belief, 2 Investor Fit" in system and "8 Monitoring" in system
    assert "- T1 Belief: Section 1 of the template." in system
    assert "- T5 Invalidation, warnings and monitoring: Sections 6 to 8." in system


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
    version = policy.versions[0]
    ref = review_prompts.PromptRef(ReviewKind.POLICY, version.id, _at(2026, 1, 15), 0)
    prompt = review_prompts.policy_prompt(version, ref)
    request = prompt.llm_request()
    text = prompt.text()
    assert request.system + request.prompt in text.replace("\n\n---\n\n", "")
    assert request.web_search is False
    assert "| XUS | XUS name | ETF | 60 | -20 | 20 | no |" in text
    assert "# Thesis" in text
    for private in ("12345", "alice", portfolio.name, "Retirement"):
        assert private not in text
    json.dumps(request.json_schema)  # serializable for every provider


@pytest.mark.req("REV-19", "REV-09")
def test_a_prompt_id_names_the_draft_its_state_and_the_news_period() -> None:
    issued = datetime(2026, 11, 7, 10, 15, 30, 123456, tzinfo=UTC)
    ref = review_prompts.PromptRef(ReviewKind.THESIS, 12, issued, 90)
    assert ref.prompt_id.startswith("T12-20261107T101530Z-90-")
    back = review_prompts.parse_prompt_id(f"  {ref.prompt_id}\n")
    assert back == review_prompts.PromptRef(
        ReviewKind.THESIS, 12, issued.replace(microsecond=0), 90
    )
    assert (back.news_from, back.news_to) == (date(2026, 8, 9), date(2026, 11, 7))
    policy = review_prompts.PromptRef(ReviewKind.POLICY, 3, issued, 0).prompt_id
    assert review_prompts.parse_prompt_id(policy).kind == ReviewKind.POLICY  # type: ignore[union-attr]
    # Changed or mistyped IDs are not accepted
    for wrong in ("", "T12", ref.prompt_id.replace("T12", "T13"), ref.prompt_id[:-1] + "x"):
        assert review_prompts.parse_prompt_id(wrong) is None


@pytest.mark.req("REV-19", "REV-04", "NFR-01")
def test_the_prompt_text_holds_instructions_content_and_answer_format(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor("alice")
    revision = factory.policy_draft(owner, thesis_title="Growth").versions[0]
    ref = review_prompts.PromptRef(ReviewKind.THESIS, revision.id, _at(2026, 1, 15), 30)
    prompt = review_prompts.thesis_prompt(revision, ref)
    text = prompt.text()
    # The same instructions and content an AI reviewer receives
    assert prompt.instructions in text and prompt.content in text
    assert f"Repeat this prompt ID exactly in the field prompt_id: {ref.prompt_id}" in text
    assert "If you cannot search the web, say so in the reasoning of" in text
    assert "2025-12-16" in text and "2026-01-15" in text
    assert json.dumps(prompt.json_schema, indent=2) in text
    assert "alice" not in text


@pytest.mark.req("REV-18")
def test_every_problem_of_an_answer_is_listed() -> None:
    answer = thesis_answer(scores=(7, 6, 8, 5, 11), prompt_id="other")
    parsed, problems = review_prompts.check_answer(ReviewKind.THESIS, answer, PROMPT_ID)
    assert parsed is None
    assert [p.code for p in problems] == [
        "answer_prompt_id_wrong",
        "answer_aspects_wrong",
        "score_invalid",
    ]
    _, problems = review_prompts.check_answer(
        ReviewKind.THESIS, '{"prompt_id": 1, "aspects": "none"}', PROMPT_ID
    )
    assert {str(p).split(":")[0] for p in problems} >= {
        "prompt_id",
        "aspects",
        "verdict",
        "sources",
        "suggestions",
    }
    assert (
        review_prompts.answer_prompt_id(f"Here:\n```json\n{thesis_answer(prompt_id=' a ')}```")
        == "a"
    )
    assert review_prompts.answer_prompt_id("[1, 2]") is None
