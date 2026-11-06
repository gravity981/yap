"""Instructions for the LLM and validation of its answer (REV-02 to REV-07).

The instructions belong to the scoring version (REV-06): change SCORING_VERSION in
domain/reviews.py whenever they change. Requests contain only thesis text, asset names
and tickers, and the target structure; never amounts or who the investor is (NFR-01).
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from yap.db.models import PolicyVersion, ThesisRevision
from yap.domain.reviews import ASPECTS, ReviewKind, Verdict, to_half_points
from yap.llm import LlmError
from yap.llm.base import LlmRequest
from yap.messages import msg

SUGGESTION_KINDS = ("thesis_text", "thesis_status", "policy_position")

SCORING_RULES = (
    "Score each aspect from 0 to 10 in steps of 0.5 (e.g. 6.5); 10 is the best. "
    "Give each aspect a short reasoning of two to four sentences. Be critical and "
    "concrete; refer to the text you assess. Write in English."
)


# --- Answer format ---------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AspectAnswer(_Model):
    code: str
    score: float
    reasoning: str


class SourceAnswer(_Model):
    title: str
    published_on: str | None
    url: str


class SuggestionAnswer(_Model):
    kind: Literal["thesis_text", "thesis_status", "policy_position"]
    content: str


class ThesisAnswer(_Model):
    aspects: list[AspectAnswer]
    verdict: Verdict
    sources: list[SourceAnswer]
    suggestions: list[SuggestionAnswer]


class PolicyAnswer(_Model):
    aspects: list[AspectAnswer]
    suggestions: list[SuggestionAnswer]


def _schema(kind: ReviewKind) -> dict[str, Any]:
    """JSON Schema of the answer, in the subset all three providers accept in strict
    mode: every property required, no additional properties, no numeric bounds."""

    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    codes = [a.code for a in ASPECTS[kind]]
    aspect = obj(
        {
            "code": {"type": "string", "enum": codes},
            "score": {"type": "number", "description": "0 to 10 in steps of 0.5"},
            "reasoning": {"type": "string"},
        }
    )
    suggestion = obj(
        {
            "kind": {"type": "string", "enum": list(SUGGESTION_KINDS)},
            "content": {"type": "string", "description": "The suggested change, in markdown"},
        }
    )
    properties: dict[str, Any] = {"aspects": {"type": "array", "items": aspect}}
    if kind == ReviewKind.THESIS:
        properties["verdict"] = {"type": "string", "enum": [v.value for v in Verdict]}
        properties["sources"] = {
            "type": "array",
            "items": obj(
                {
                    "title": {"type": "string"},
                    "published_on": {
                        "type": ["string", "null"],
                        "description": "ISO date YYYY-MM-DD, null if unknown",
                    },
                    "url": {"type": "string"},
                }
            ),
        }
    properties["suggestions"] = {"type": "array", "items": suggestion}
    return obj(properties)


@dataclass(frozen=True)
class ParsedAspect:
    code: str
    half_points: int
    reasoning: str


@dataclass(frozen=True)
class ParsedReview:
    aspects: list[ParsedAspect]
    verdict: Verdict | None
    sources: list[SourceAnswer]
    suggestions: list[SuggestionAnswer]


def _valid_score(score: float) -> bool:
    try:
        to_half_points(score)
    except ValueError:
        return False
    return True


def parse_answer(kind: ReviewKind, text: str) -> ParsedReview:
    """Validates the answer strictly; an invalid answer fails the review (REV-08)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)  # tolerate a code fence around the JSON
    try:
        data = json.loads(match.group(0) if match else text)
        answer: ThesisAnswer | PolicyAnswer = (
            ThesisAnswer.model_validate(data)
            if kind == ReviewKind.THESIS
            else PolicyAnswer.model_validate(data)
        )
    except (json.JSONDecodeError, ValidationError) as e:
        raise LlmError(msg("answer_format_invalid", error=type(e).__name__)) from e
    expected = [a.code for a in ASPECTS[kind]]
    if sorted(a.code for a in answer.aspects) != expected:
        raise LlmError(msg("answer_aspects_wrong", aspects=", ".join(expected)))
    try:
        aspects = [
            ParsedAspect(a.code, to_half_points(a.score), a.reasoning.strip())
            for a in sorted(answer.aspects, key=lambda a: a.code)
        ]
    except ValueError:
        bad = next(a.score for a in answer.aspects if not _valid_score(a.score))
        raise LlmError(msg("score_invalid", score=bad)) from None
    if isinstance(answer, ThesisAnswer):
        return ParsedReview(aspects, answer.verdict, answer.sources, answer.suggestions)
    return ParsedReview(aspects, None, [], answer.suggestions)


# --- Requests --------------------------------------------------------------------------


def _aspect_list(kind: ReviewKind) -> str:
    return "\n".join(f"- {a.code} {a.name}: {a.guide}" for a in ASPECTS[kind])


def _thesis_text(revision: ThesisRevision) -> str:
    return (
        f"Title: {revision.title}\nStatus set by the investor: {revision.status}\n\n"
        f"<thesis>\n{revision.content_md}\n</thesis>"
    )


def thesis_request(revision: ThesisRevision, news_from: date, news_to: date) -> LlmRequest:
    """REV-02 to REV-04: aspects T1-T6 and a verdict, with current news."""
    system = f"""You review an investment thesis written by a private investor.
Today is {news_to.isoformat()}.

Aspects T1 to T5 judge the text itself. Aspect T6 and the verdict judge it against
current news: search the web for news from {news_from.isoformat()} to {news_to.isoformat()} on
the assets the thesis is about (take them from the thesis text), in particular on its
value drivers, risks, break conditions and warning signals.

Aspects:
{_aspect_list(ReviewKind.THESIS)}

{SCORING_RULES}

Verdict, independent of the scores:
- broken: the news shows that a break condition of the thesis is met.
- needs_adaptation: warning signals are observed, or parts of the thesis are outdated.
- intact: neither of the above.

List every news article you rely on under sources (title, publication date, link).
Every statement based on news refers to its source as [n], the position in that list
starting at 1. Do not invent sources.

Suggestions are optional: concrete changes to the thesis text (thesis_text) or its
status (thesis_status). Make none if nothing needs to change."""
    return LlmRequest(
        system=system,
        prompt=_thesis_text(revision),
        json_schema=_schema(ReviewKind.THESIS),
        web_search=True,
    )


def _structure(version: PolicyVersion) -> str:
    rows = ["| Ticker | Name | Type | Target % | Buy threshold % | Sell threshold % | Exit |"]
    rows.append("|---|---|---|---|---|---|---|")
    for p in version.positions:
        rows.append(
            f"| {p.asset.ticker} | {p.asset.name} | {p.asset.type} | {p.target_pct} | "
            f"{p.buy_threshold_pct} | {p.sell_threshold_pct} | {'yes' if p.exit else 'no'} |"
        )
    rationales = "\n\n".join(
        f"### {p.asset.ticker}\n{p.rationale_md.strip()}"
        for p in version.positions
        if p.rationale_md.strip()
    )
    return "\n".join(rows) + (f"\n\nRationales per position:\n\n{rationales}" if rationales else "")


def policy_request(version: PolicyVersion) -> LlmRequest:
    """REV-02, REV-05: aspects P1-P6 from thesis and target structure; no web search."""
    system = f"""You review the target structure of an investment policy written by a
private investor: does it match the investment thesis it is based on? 0 means the
structure does not match the thesis at all, 10 a perfect match. Judge only the thesis
and the structure given here; do not search for news.

Thresholds are relative to the target: absolute threshold = target x (1 + threshold/100).
Example: target 40 %, sell threshold +25 % -> sell above 50 %. Positions with exit = yes
are sold completely in the next rebalancing. Sell proceeds are always reinvested. A
position of type cash_buffer holds cash for buying dips.

Aspects:
{_aspect_list(ReviewKind.POLICY)}

{SCORING_RULES}

Suggestions are optional: concrete changes to target allocations, thresholds or exit
flags of positions (policy_position). Make none if nothing needs to change."""
    prompt = (
        f"{_thesis_text(version.thesis_revision)}\n\n"
        f"<target_structure>\n{_structure(version)}\n</target_structure>"
    )
    return LlmRequest(
        system=system,
        prompt=prompt,
        json_schema=_schema(ReviewKind.POLICY),
        web_search=False,
    )
