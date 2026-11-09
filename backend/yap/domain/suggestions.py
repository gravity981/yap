"""Suggestions and proposals of a review (REV-07, REV-22): what they change and the rules
they follow, without database or web.

A suggestion is one concrete change of a draft: the text of one thesis section, one field
of a position, a new position or the removal of one. A proposal is a whole target
structure for a thesis without positions. Changes are stored as JSON; decimals as strings,
so they stay exact.
"""

import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from yap.domain.types import (
    BUY_THRESHOLD_MAX,
    BUY_THRESHOLD_MIN,
    HUNDRED,
    SELL_THRESHOLD_MIN,
    TARGET_SUM_TOLERANCE,
    AssetType,
)

SECTION_COUNT = 8  # sections of the thesis template (THS-07)

# English names of the template's sections, for a section the thesis does not have yet
SECTION_NAMES = (
    "Belief — What do I think?",
    "Investor Fit — Is this appropriate for me?",
    "Implementation — Which assets express my thesis?",
    "Opportunity — What creates value?",
    "Downside — What can go wrong?",
    "Invalidation — When am I wrong?",
    "Early Warnings — What should make me reconsider?",
    "Monitoring — Is the thesis still valid?",
)

# The fields of a position a suggestion can change (REV-07)
POSITION_FIELDS = ("target_pct", "buy_threshold_pct", "sell_threshold_pct", "exit", "rationale_md")
DECIMAL_FIELDS = ("target_pct", "buy_threshold_pct", "sell_threshold_pct")


class SuggestionKind(StrEnum):
    THESIS_SECTION = "thesis_section"
    POSITION_CHANGE = "position_change"
    POSITION_ADD = "position_add"
    POSITION_REMOVE = "position_remove"
    PROPOSAL = "proposal"  # REV-22

    @property
    def is_suggestion(self) -> bool:
        return self != SuggestionKind.PROPOSAL


class SuggestionState(StrEnum):
    OPEN = "open"
    TAKEN_OVER = "taken_over"


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation, ValueError:
        return None


def position_problems(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Range problems of the given fields of a position (POL-04), as (field, error)."""
    problems: list[tuple[str, str]] = []
    for name in DECIMAL_FIELDS:
        if name not in row:
            continue
        value = _decimal(row[name])
        if value is None or not value.is_finite():
            problems.append((name, "is not a number"))
        elif name == "target_pct" and not 0 <= value <= HUNDRED:
            problems.append((name, "must be 0 to 100"))
        elif name == "buy_threshold_pct" and not BUY_THRESHOLD_MIN <= value <= BUY_THRESHOLD_MAX:
            problems.append((name, "must be -100 to 0"))
        elif name == "sell_threshold_pct" and value < SELL_THRESHOLD_MIN:
            problems.append((name, "must be 0 or more"))
    if "type" in row and row["type"] not in {t.value for t in AssetType}:
        problems.append(("type", "is not an asset type"))
    return problems


def structure_problems(rows: list[dict[str, Any]]) -> list[str]:
    """POL-05: a proposal could be activated as it is."""
    problems: list[str] = []
    if not rows:
        return ["has no positions"]
    tickers = [r["ticker"] for r in rows]
    if len(set(tickers)) != len(tickers):
        problems.append("has a ticker twice")
    total = sum((_decimal(r["target_pct"]) or Decimal(0) for r in rows), Decimal(0))
    if abs(total - HUNDRED) > TARGET_SUM_TOLERANCE:
        problems.append(f"targets sum to {total}, not 100")
    if sum(1 for r in rows if r["type"] == AssetType.CASH_BUFFER.value) > 1:
        problems.append("has more than one cash buffer")
    return problems


# --- Thesis sections -------------------------------------------------------------------

_HEADING = re.compile(r"^##\s+(\d+)\.", re.MULTILINE)
_ANY_HEADING = re.compile(r"^#{1,2}\s", re.MULTILINE)


def _section_span(markdown: str, section: int) -> tuple[int, int] | None:
    """Start and end of the body of section `section` (after its heading line)."""
    for match in _HEADING.finditer(markdown):
        if int(match.group(1)) != section:
            continue
        line_end = markdown.find("\n", match.end())
        start = len(markdown) if line_end == -1 else line_end + 1
        following = _ANY_HEADING.search(markdown, start)
        return start, following.start() if following else len(markdown)
    return None


def section_text(markdown: str, section: int) -> str | None:
    """The body of a section of the thesis template, or None if the thesis lacks it."""
    span = _section_span(markdown, section)
    return markdown[span[0] : span[1]].strip() if span else None


def replace_section(markdown: str, section: int, text: str | None) -> str:
    """The thesis with the body of `section` replaced; a missing section is added at the
    end with its template heading. `text` None removes a section that was added so."""
    span = _section_span(markdown, section)
    if span is None:
        if text is None:
            return markdown
        heading = f"## {section}. {SECTION_NAMES[section - 1]}"
        return f"{markdown.rstrip()}\n\n{heading}\n{text.strip()}\n"
    start, end = span
    if text is None:  # undo of an added section: drop heading and body
        heading_start = markdown.rfind("\n", 0, max(start - 1, 0)) + 1
        return (markdown[:heading_start].rstrip() + "\n" + markdown[end:]).rstrip() + "\n"
    tail = markdown[end:]
    return f"{markdown[:start]}{text.strip()}\n" + ("\n" + tail if tail else "")
