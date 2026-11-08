"""Suggestions and proposals without database (REV-07, REV-22): thesis sections and the
rules of changed positions and proposed target structures."""

from typing import Any

import pytest

from yap.domain.suggestions import (
    SuggestionKind,
    position_problems,
    replace_section,
    section_text,
    structure_problems,
)

THESIS = """# Investment Thesis

## 1. Belief — What do I think?
The world grows.

### Details
Over 15 years.

## 2. Investor Fit — Is this appropriate for me?
Balanced.
"""


@pytest.mark.req("REV-07")
def test_the_text_of_a_section_is_read_with_its_subheadings() -> None:
    assert section_text(THESIS, 1) == "The world grows.\n\n### Details\nOver 15 years."
    assert section_text(THESIS, 2) == "Balanced."
    assert section_text(THESIS, 7) is None


@pytest.mark.req("REV-07")
def test_replacing_a_section_keeps_its_heading_and_the_other_sections() -> None:
    changed = replace_section(THESIS, 1, "The world grows by 3 % a year.")
    assert section_text(changed, 1) == "The world grows by 3 % a year."
    assert "## 1. Belief — What do I think?\n" in changed
    assert section_text(changed, 2) == "Balanced."
    # Undo puts the old text back
    restored = replace_section(changed, 1, section_text(THESIS, 1))
    assert section_text(restored, 1) == section_text(THESIS, 1)
    assert section_text(replace_section(THESIS, 2, "Growth."), 2) == "Growth."


@pytest.mark.req("REV-07")
def test_a_missing_section_is_added_with_its_template_heading_and_removed_on_undo() -> None:
    added = replace_section(THESIS, 7, "- GDP below 2 %")
    assert "## 7. Early Warnings — What should make me reconsider?\n- GDP below 2 %" in added
    assert section_text(added, 7) == "- GDP below 2 %"
    undone = replace_section(added, 7, None)
    assert section_text(undone, 7) is None
    assert undone.rstrip() == THESIS.rstrip()
    # Nothing to remove: the thesis stays as it is
    assert replace_section(THESIS, 7, None) == THESIS


@pytest.mark.req("REV-07", "THS-07")
def test_sections_of_the_german_template_are_found_by_their_number() -> None:
    german = "# Anlagethese\n\n## 1. Überzeugung — Was denke ich?\nDie Welt wächst.\n"
    assert section_text(german, 1) == "Die Welt wächst."
    changed = replace_section(german, 1, "Die Welt wächst stark.")
    assert "## 1. Überzeugung — Was denke ich?\nDie Welt wächst stark." in changed


@pytest.mark.req("REV-07")
@pytest.mark.parametrize(
    ("row", "problems"),
    [
        ({"target_pct": "40", "buy_threshold_pct": "-20", "sell_threshold_pct": "25"}, []),
        ({"target_pct": "101"}, [("target_pct", "must be 0 to 100")]),
        ({"target_pct": "-1"}, [("target_pct", "must be 0 to 100")]),
        ({"target_pct": "abc"}, [("target_pct", "is not a number")]),
        ({"target_pct": "NaN"}, [("target_pct", "is not a number")]),
        ({"buy_threshold_pct": "5"}, [("buy_threshold_pct", "must be -100 to 0")]),
        ({"buy_threshold_pct": "-101"}, [("buy_threshold_pct", "must be -100 to 0")]),
        ({"sell_threshold_pct": "-1"}, [("sell_threshold_pct", "must be 0 or more")]),
        ({"type": "bond"}, [("type", "is not an asset type")]),
        ({"type": "cash_buffer", "exit": True, "rationale_md": "x"}, []),
    ],
)
def test_position_values_follow_the_threshold_rules(
    row: dict[str, Any], problems: list[tuple[str, str]]
) -> None:
    assert position_problems(row) == problems


def _row(ticker: str, target: str, kind: str = "ETF") -> dict[str, Any]:
    return {"ticker": ticker, "target_pct": target, "type": kind}


@pytest.mark.req("REV-22", "POL-05")
@pytest.mark.parametrize(
    ("rows", "problems"),
    [
        ([_row("A", "85"), _row("CASH", "15", "cash_buffer")], []),
        ([_row("A", "99.995"), _row("B", "0.005")], []),
        ([], ["has no positions"]),
        ([_row("A", "50"), _row("A", "50")], ["has a ticker twice"]),
        ([_row("A", "90")], ["targets sum to 90, not 100"]),
        (
            [_row("C1", "50", "cash_buffer"), _row("C2", "50", "cash_buffer")],
            ["has more than one cash buffer"],
        ),
    ],
)
def test_a_proposal_could_be_activated_as_it_is(
    rows: list[dict[str, Any]], problems: list[str]
) -> None:
    assert structure_problems(rows) == problems


@pytest.mark.req("REV-07", "REV-22")
def test_proposals_are_no_suggestions_of_the_answer_format() -> None:
    assert [k.value for k in SuggestionKind if k.is_suggestion] == [
        "thesis_section",
        "position_change",
        "position_add",
        "position_remove",
    ]
