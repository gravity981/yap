"""Instructions sent to the LLM and validation of its answer."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from tests.reviews.answers import PROMPT_ID, answer, thesis_answer
from yap.domain.reviews import Verdict
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
@pytest.mark.parametrize("with_positions", [True, False])
def test_answer_schema_is_strict_for_all_providers(with_positions: bool) -> None:
    schema = review_prompts._schema(with_positions, PROMPT_ID)
    assert schema["properties"]["prompt_id"] == {"type": "string", "enum": [PROMPT_ID]}
    for obj in _walk(schema):
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])  # type: ignore[call-overload]
    codes = schema["properties"]["aspects"]["items"]["properties"]["code"]["enum"]
    assert len(codes) == (12 if with_positions else 6)
    assert schema["properties"]["verdict"]["enum"] == ["good", "warning", "broken"]
    assert "verdict_reason" in schema["properties"]


@pytest.mark.req("REV-02", "REV-03", "REV-04")
def test_an_answer_is_parsed() -> None:
    text = answer(prompt_id=PROMPT_ID)
    parsed = review_prompts.parse_answer(f"```json\n{text}\n```", PROMPT_ID, True)
    codes = [a.code for a in parsed.aspects]
    assert codes == [f"T{i}" for i in range(1, 7)] + [f"P{i}" for i in range(1, 7)]
    assert [a.half_points for a in parsed.aspects][:2] == [14, 12]
    assert parsed.verdict == Verdict.WARNING
    assert parsed.verdict_reason == "Warning signals are observed [1]."
    assert parsed.sources[0].url == "https://news.example/etf"
    assert parsed.suggestions[0].kind == "thesis_section"
    assert parsed.suggestions[0].change == {"section": 1, "text": "Within 15 years."}
    # Without positions only the thesis is scored
    parsed = review_prompts.parse_answer(thesis_answer(prompt_id=PROMPT_ID), PROMPT_ID, False)
    assert len(parsed.aspects) == 6


@pytest.mark.req("REV-08", "REV-02", "REV-03")
@pytest.mark.parametrize(
    ("text", "with_positions", "message"),
    [
        ("not json", True, "no JSON object"),
        ('{"prompt_id": "x",}', True, "no valid JSON: Illegal trailing comma"),
        (answer(verdict="intact", prompt_id=PROMPT_ID), True, "verdict: Input should be"),
        (answer(scores=(7, 6, 8, 5, 7), prompt_id=PROMPT_ID), True, "exactly the aspects"),
        (thesis_answer(prompt_id=PROMPT_ID), True, "exactly the aspects"),
        (answer(prompt_id=PROMPT_ID), False, "exactly the aspects"),
        (answer(scores=(7, 6, 8, 5, 7, 6.3), prompt_id=PROMPT_ID), True, "steps of 0.5"),
        (answer(scores=(7, 6, 8, 5, 7, 11), prompt_id=PROMPT_ID), True, "between 0 and 10"),
        (answer(extra_field=1, prompt_id=PROMPT_ID), True, "extra_field: Extra inputs"),
        (
            answer(suggestions=[{"kind": "thesis_status", "content": "x"}], prompt_id=PROMPT_ID),
            True,
            "suggestions.0.kind",
        ),
        (answer(), True, "prompt_id: Field required"),
        (answer(prompt_id="R1-20260115T100000Z-90-ffffff"), True, "prompt ID " + PROMPT_ID),
    ],
)
def test_invalid_answers_are_rejected(text: str, with_positions: bool, message: str) -> None:
    with pytest.raises(LlmError, match=message):
        review_prompts.parse_answer(text, PROMPT_ID, with_positions)


@pytest.mark.req("REV-03")
def test_an_answer_without_verdict_or_reason_is_rejected() -> None:
    data = json.loads(answer(prompt_id=PROMPT_ID))
    del data["verdict_reason"]
    with pytest.raises(LlmError, match="verdict_reason: Field required"):
        review_prompts.parse_answer(json.dumps(data), PROMPT_ID, True)


@pytest.mark.req("REV-04", "NFR-01")
def test_the_request_searches_news_of_the_period(session: Session, factory: Factory) -> None:
    owner = factory.investor("alice")
    draft = factory.policy_draft(owner, thesis_title="Growth").versions[0]
    ref = review_prompts.PromptRef(draft.id, _at(2026, 1, 15), 90)
    request = review_prompts.review_prompt(draft, ref).llm_request()
    assert request.web_search is True
    assert "2025-10-17" in request.system and "2026-01-15" in request.system
    assert "Title: Growth" in request.prompt and "# Thesis" in request.prompt
    assert "alice" not in request.system + request.prompt


@pytest.mark.req("REV-02", "REV-06", "THS-07")
def test_the_request_judges_the_sections_of_the_template(
    session: Session, factory: Factory
) -> None:
    draft = factory.policy_draft(factory.investor()).versions[0]
    ref = review_prompts.PromptRef(draft.id, _at(2026, 1, 15), 14)
    system = review_prompts.review_prompt(draft, ref).instructions
    assert "1 Belief, 2 Investor Fit" in system and "8 Monitoring" in system
    assert "- T1 Belief: Section 1 of the template." in system
    assert "- T5 Invalidation, warnings and monitoring: Sections 6 to 8." in system


@pytest.mark.req("REV-02", "REV-19")
def test_without_positions_only_the_thesis_is_asked_for(session: Session, factory: Factory) -> None:
    draft = factory.policy_draft(factory.investor()).versions[0]
    prompt = review_prompts.review_prompt(
        draft, review_prompts.PromptRef(draft.id, _at(2026, 1, 15), 90)
    )
    assert prompt.with_positions is False
    assert "score\nonly T1 to T6" in prompt.instructions
    assert "- P1 Coverage" not in prompt.instructions
    assert "(no positions yet)" in prompt.content
    codes = prompt.json_schema["properties"]["aspects"]["items"]["properties"]["code"]["enum"]
    assert codes == ["T1", "T2", "T3", "T4", "T5", "T6"]


@pytest.mark.req("REV-05", "REV-02", "NFR-01")
def test_the_request_has_title_thesis_and_structure_but_no_amounts(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor("alice")
    policy = factory.active_policy(owner, [spec("XUS", 60), spec("ETH", 40)], name="Retirement")
    portfolio = factory.portfolio(owner, policy)
    snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, [ValueSpec("XUS", Decimal("12345.67"))]
    )
    version = policy.versions[0]
    prompt = review_prompts.review_prompt(
        version, review_prompts.PromptRef(version.id, _at(2026, 1, 15), 90)
    )
    request = prompt.llm_request()
    text = prompt.text()
    assert request.system + request.prompt in text.replace("\n\n---\n\n", "")
    assert prompt.with_positions is True
    assert "Title: Core thesis" in prompt.content and "# Thesis" in prompt.content
    assert "| XUS | XUS name | ETF | 60 | -20 | 20 | no |" in prompt.content
    # The target-structure aspects judge only thesis and structure, not the news
    assert "They judge only the thesis and\nthe target structure given here, not the news." in (
        prompt.instructions
    )
    assert "- P4 Exits: Exit flags match the break conditions" in prompt.instructions
    assert "Only T6 and the verdict use news." in prompt.instructions
    for private in ("12345", "alice", portfolio.name, "Retirement"):
        assert private not in text
    json.dumps(request.json_schema)  # serializable for every provider


@pytest.mark.req("REV-19", "REV-09")
def test_a_prompt_id_names_the_draft_its_state_and_the_news_period() -> None:
    issued = datetime(2026, 11, 7, 10, 15, 30, 123456, tzinfo=UTC)
    ref = review_prompts.PromptRef(12, issued, 90)
    assert ref.prompt_id.startswith("R12-20261107T101530Z-90-")
    back = review_prompts.parse_prompt_id(f"  {ref.prompt_id}\n")
    assert back == review_prompts.PromptRef(12, issued.replace(microsecond=0), 90)
    assert (back.news_from, back.news_to) == (date(2026, 8, 9), date(2026, 11, 7))
    # Changed or mistyped IDs are not accepted, nor those of separate thesis reviews
    old = "T12-20261107T101530Z-90-" + ref.prompt_id[-6:]
    for wrong in ("", "R12", ref.prompt_id.replace("R12", "R13"), ref.prompt_id[:-1] + "x", old):
        assert review_prompts.parse_prompt_id(wrong) is None


@pytest.mark.req("REV-19", "REV-04", "NFR-01")
def test_the_prompt_text_holds_instructions_content_and_answer_format(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor("alice")
    draft = factory.policy_draft(owner, thesis_title="Growth", positions=[spec("XUS", 100)])
    version = draft.versions[0]
    ref = review_prompts.PromptRef(version.id, _at(2026, 1, 15), 30)
    prompt = review_prompts.review_prompt(version, ref)
    text = prompt.text()
    # The same instructions and content an AI reviewer receives
    assert prompt.instructions in text and prompt.content in text
    assert f"Repeat this prompt ID exactly in the field prompt_id: {ref.prompt_id}" in text
    assert "If you cannot search the web, say so in the reasoning of" in text
    assert "Today is\n2026-01-15" in text and "2025-12-16" in text
    assert "- T1 Belief" in text and "- P6 Rationales" in text
    assert "- warning: warning signals are observed" in text
    assert "<target_structure>" in text and "| XUS |" in text
    assert json.dumps(prompt.json_schema, indent=2) in text
    assert "alice" not in text


@pytest.mark.req("REV-18")
def test_every_problem_of_an_answer_is_listed() -> None:
    text = answer(scores=(7, 6, 8, 5, 11), prompt_id="other")
    parsed, problems = review_prompts.check_answer(text, PROMPT_ID, True)
    assert parsed is None
    assert [p.code for p in problems] == [
        "answer_prompt_id_wrong",
        "answer_aspects_wrong",
        "score_invalid",
    ]
    _, problems = review_prompts.check_answer(
        '{"prompt_id": 1, "aspects": "none"}', PROMPT_ID, True
    )
    assert {str(p).split(":")[0] for p in problems} >= {
        "prompt_id",
        "aspects",
        "verdict",
        "verdict_reason",
        "sources",
        "suggestions",
    }
    assert review_prompts.answer_prompt_id(f"Here:\n```json\n{answer(prompt_id=' a ')}```") == "a"
    assert review_prompts.answer_prompt_id("[1, 2]") is None
