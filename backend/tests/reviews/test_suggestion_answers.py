"""Suggestions and proposals in the answer of a review (REV-07, REV-18, REV-22): each
kind is checked against the reviewed positions before anything is stored."""

import json
from typing import Any

import pytest

from tests.reviews.answers import PROMPT_ID, answer, position, proposal, suggestion
from yap.domain.suggestions import SuggestionKind
from yap.services import review_prompts

TICKERS = ["AAA", "BBB"]


def _check(
    suggestions: list[dict[str, Any]] | None = None,
    proposals: list[dict[str, Any]] | None = None,
    with_positions: bool = True,
) -> tuple[review_prompts.ParsedReview | None, list[str]]:
    text = answer(
        prompt_id=PROMPT_ID,
        structure=None if not with_positions else (8, 7, 6, 9, 7.5, 8),
        suggestions=suggestions or [],
        proposals=proposals or [],
    )
    parsed, problems = review_prompts.check_answer(
        text, PROMPT_ID, with_positions, TICKERS if with_positions else []
    )
    return parsed, [str(p) for p in problems]


@pytest.mark.req("REV-07")
def test_each_kind_of_suggestion_is_parsed_into_its_change() -> None:
    parsed, problems = _check(
        [
            suggestion("thesis_section", "Measurable.", section=7, text="  - GDP < 2 %  "),
            suggestion("position_change", "Wider.", ticker="aaa", sell_threshold_pct=30),
            suggestion("position_change", "Leave.", ticker="BBB", exit=True),
            suggestion("position_change", "Explain.", ticker="BBB", rationale="Because."),
            suggestion(
                "position_add",
                "Diversify.",
                ticker="ccc",
                name="C fund",
                type="ETF",
                target_pct=10,
                buy_threshold_pct=-20,
                sell_threshold_pct=20,
            ),
            suggestion("position_remove", "Not backed.", ticker="BBB"),
        ]
    )
    assert problems == []
    assert parsed is not None
    assert [(s.kind, s.content_md, s.change) for s in parsed.suggestions] == [
        (SuggestionKind.THESIS_SECTION, "Measurable.", {"section": 7, "text": "- GDP < 2 %"}),
        (
            SuggestionKind.POSITION_CHANGE,
            "Wider.",
            {"ticker": "AAA", "field": "sell_threshold_pct", "value": "30"},
        ),
        (
            SuggestionKind.POSITION_CHANGE,
            "Leave.",
            {"ticker": "BBB", "field": "exit", "value": True},
        ),
        (
            SuggestionKind.POSITION_CHANGE,
            "Explain.",
            {"ticker": "BBB", "field": "rationale_md", "value": "Because."},
        ),
        (
            SuggestionKind.POSITION_ADD,
            "Diversify.",
            {
                "position": {
                    "ticker": "CCC",
                    "name": "C fund",
                    "type": "ETF",
                    "target_pct": "10",
                    "buy_threshold_pct": "-20",
                    "sell_threshold_pct": "20",
                    "exit": False,
                    "rationale_md": "",
                }
            },
        ),
        (SuggestionKind.POSITION_REMOVE, "Not backed.", {"ticker": "BBB"}),
    ]


@pytest.mark.req("REV-07", "REV-18")
@pytest.mark.parametrize(
    ("item", "problem"),
    [
        (
            suggestion("thesis_section", section=0, text="x"),
            "suggestions.0.section: must be 1 to 8",
        ),
        (
            suggestion("thesis_section", section=9, text="x"),
            "suggestions.0.section: must be 1 to 8",
        ),
        (suggestion("thesis_section", text="x"), "suggestions.0.section: must be 1 to 8"),
        (
            suggestion("thesis_section", section=3, text=" "),
            "suggestions.0.text: the new text of the section is missing",
        ),
        (suggestion("position_remove"), "suggestions.0.ticker: is missing"),
        (
            suggestion("position_remove", ticker="ZZZ"),
            "suggestions.0.ticker: ZZZ is not a position",
        ),
        (
            suggestion("position_change", ticker="ZZZ", target_pct=10),
            "suggestions.0.ticker: ZZZ is not a position",
        ),
        (
            suggestion("position_change", ticker="AAA"),
            "suggestions.0: change exactly one field of the position",
        ),
        (
            suggestion("position_change", ticker="AAA", target_pct=10, exit=True),
            "suggestions.0: change exactly one field of the position",
        ),
        (
            suggestion("position_change", ticker="AAA", buy_threshold_pct=10),
            "suggestions.0.buy_threshold_pct: must be -100 to 0",
        ),
        (
            suggestion("position_add", **position("aaa", 10)),
            "suggestions.0.ticker: AAA is already a position",
        ),
        (
            suggestion("position_add", ticker="CCC", name="C", type="ETF", target_pct=10),
            "suggestions.0.buy_threshold_pct: is missing",
        ),
        (
            suggestion(
                "position_add",
                ticker="CCC",
                name="C",
                type="ETF",
                target_pct=120,
                buy_threshold_pct=-20,
                sell_threshold_pct=20,
            ),
            "suggestions.0.target_pct: must be 0 to 100",
        ),
    ],
)
def test_a_suggestion_that_does_not_fit_its_kind_or_the_draft_is_a_problem(
    item: dict[str, Any], problem: str
) -> None:
    parsed, problems = _check([item])
    assert parsed is None
    assert problem in problems


@pytest.mark.req("REV-07")
def test_every_problem_of_the_suggestions_is_listed() -> None:
    parsed, problems = _check(
        [
            suggestion("thesis_section", section=0, text="x"),
            suggestion("position_remove", ticker="ZZZ"),
        ]
    )
    assert parsed is None
    assert problems == [
        "suggestions.0.section: must be 1 to 8",
        "suggestions.1.ticker: ZZZ is not a position",
    ]


@pytest.mark.req("REV-07")
def test_without_known_positions_the_tickers_are_not_checked() -> None:
    text = answer(
        prompt_id=PROMPT_ID,
        suggestions=[suggestion("position_remove", ticker="ZZZ")],
        proposals=[],
    )
    parsed, problems = review_prompts.check_answer(text, PROMPT_ID, True)
    assert problems == [] and parsed is not None
    assert parsed.suggestions[0].change == {"ticker": "ZZZ"}


@pytest.mark.req("REV-22")
def test_without_positions_the_review_proposes_target_structures() -> None:
    parsed, problems = _check(
        proposals=[
            proposal(),
            proposal(
                "Broader",
                position("vwrl", 90, rationale=" Core. "),
                position("CASH", 10, "cash_buffer"),
            ),
        ],
        with_positions=False,
    )
    assert problems == []
    assert parsed is not None
    proposals = [s for s in parsed.suggestions if s.kind == SuggestionKind.PROPOSAL]
    assert [(p.content_md, p.change["name"]) for p in proposals] == [
        ("Focused structure.", "Focused"),
        ("Broader structure.", "Broader"),
    ]
    assert proposals[1].change["positions"][0] == {
        "ticker": "VWRL",
        "name": "vwrl fund",
        "type": "ETF",
        "target_pct": "90",
        "buy_threshold_pct": "-20",
        "sell_threshold_pct": "20",
        "exit": False,
        "rationale_md": "Core.",
    }


@pytest.mark.req("REV-22")
def test_proposals_of_a_policy_with_positions_are_ignored() -> None:
    parsed, problems = _check(proposals=[proposal(), proposal("Other", position("X", 50))])
    assert problems == [] and parsed is not None
    assert all(s.kind != SuggestionKind.PROPOSAL for s in parsed.suggestions)


@pytest.mark.req("REV-22", "REV-18")
@pytest.mark.parametrize(
    ("proposals", "problem"),
    [
        ([proposal(str(i)) for i in range(4)], "proposals: at most 3"),
        ([proposal("A", position("X", 90))], "proposals.0.positions: targets sum to 90, not 100"),
        (
            [proposal("A", position("C1", 50, "cash_buffer"), position("C2", 50, "cash_buffer"))],
            "proposals.0.positions: has more than one cash buffer",
        ),
        (
            [proposal("A", position("X", 100, sell_threshold_pct=-5))],
            "proposals.0.positions.0.sell_threshold_pct: must be 0 or more",
        ),
    ],
)
def test_a_proposal_that_cannot_be_activated_is_a_problem(
    proposals: list[dict[str, Any]], problem: str
) -> None:
    parsed, problems = _check(proposals=proposals, with_positions=False)
    assert parsed is None
    assert problem in problems


@pytest.mark.req("REV-07", "REV-22", "REV-19")
def test_the_answer_format_lists_the_suggestion_kinds_and_proposals() -> None:
    schema = review_prompts._schema(False, PROMPT_ID)
    item = schema["properties"]["suggestions"]["items"]
    assert item["properties"]["kind"]["enum"] == [
        "thesis_section",
        "position_change",
        "position_add",
        "position_remove",
    ]
    # Every field is required and nullable where a kind may leave it out
    assert item["properties"]["target_pct"]["type"] == ["number", "null"]
    assert item["properties"]["section"]["type"] == ["integer", "null"]
    proposal_item = schema["properties"]["proposals"]["items"]
    assert proposal_item["required"] == ["name", "description", "positions"]
    row = proposal_item["properties"]["positions"]["items"]
    assert row["properties"]["target_pct"]["type"] == "number"
    assert json.dumps(schema)  # serializable for the providers


@pytest.mark.req("REV-07", "REV-18")
def test_a_suggestion_may_leave_out_the_fields_it_does_not_use() -> None:
    """An AI outside the app often writes only the fields of the kind (REV-18)."""
    text = json.loads(answer(prompt_id=PROMPT_ID, structure=None, suggestions=[]))
    text["suggestions"] = [
        {"kind": "thesis_section", "reason": "Measurable.", "section": 1, "text": "- GDP < 2 %"}
    ]
    parsed, problems = review_prompts.check_answer(json.dumps(text), PROMPT_ID, False, [])
    assert problems == []
    assert parsed is not None and len(parsed.suggestions) == 1
