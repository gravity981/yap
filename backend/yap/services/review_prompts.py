"""The review prompt and validation of its answer (REV-02 to REV-07, REV-19).

One prompt per review: AI reviewers receive it as a request, a manual review gets the same
text to copy into an AI outside the app. The instructions belong to the scoring version
(REV-06): change SCORING_VERSION in domain/reviews.py whenever they change. Prompts contain
only thesis text, asset names and tickers, and the target structure; never amounts or who
the investor is (NFR-01).
"""

import hashlib
import json
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from yap.db.models import PolicyVersion
from yap.domain.reviews import POLICY_ASPECTS, THESIS_ASPECTS, Aspect, Verdict, to_half_points
from yap.domain.suggestions import (
    POSITION_FIELDS,
    SECTION_COUNT,
    SuggestionKind,
    position_problems,
    structure_problems,
)
from yap.llm import LlmError
from yap.llm.base import LlmRequest
from yap.messages import Message, msg

MAX_PROPOSALS = 3  # REV-22

SCORING_RULES = (
    "Score each aspect from 0 to 10 in steps of 0.5 (e.g. 6.5); 10 is the best. "
    "Give each aspect a short reasoning of two to four sentences. Be critical and "
    "concrete; refer to the text you assess. Write in English."
)


def aspects(with_positions: bool) -> tuple[Aspect, ...]:
    """T1-T6, and P1-P6 if there is a target structure to judge (REV-02)."""
    return THESIS_ASPECTS + POLICY_ASPECTS if with_positions else THESIS_ASPECTS


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


AssetTypeAnswer = Literal["ETF", "stock", "crypto", "cash_buffer"]


class SuggestionAnswer(_Model):
    """REV-07: one concrete change. Only the fields of its kind are set, the others null:
    thesis_section: section, text; position_change: ticker and exactly one of the
    position fields; position_add: ticker and all position fields; position_remove:
    ticker."""

    kind: Literal["thesis_section", "position_change", "position_add", "position_remove"]
    reason: str
    # The providers' schema requires every field (null when unused); an answer pasted from an
    # AI outside the app often leaves the unused ones out, which is just as good
    section: int | None = None
    text: str | None = None
    ticker: str | None = None
    name: str | None = None
    type: AssetTypeAnswer | None = None
    target_pct: Decimal | None = None
    buy_threshold_pct: Decimal | None = None
    sell_threshold_pct: Decimal | None = None
    exit: bool | None = None
    rationale: str | None = None


class PositionAnswer(_Model):
    ticker: str
    name: str
    type: AssetTypeAnswer
    target_pct: Decimal
    buy_threshold_pct: Decimal
    sell_threshold_pct: Decimal
    exit: bool
    rationale: str


class ProposalAnswer(_Model):
    """REV-22: a target structure that follows from a thesis without positions."""

    name: str
    description: str
    positions: list[PositionAnswer]


class Answer(_Model):
    prompt_id: str
    aspects: list[AspectAnswer]
    verdict: Verdict
    verdict_reason: str
    sources: list[SourceAnswer]
    suggestions: list[SuggestionAnswer]
    proposals: list[ProposalAnswer]


def _schema(with_positions: bool, prompt_id: str) -> dict[str, Any]:
    """JSON Schema of the answer, in the subset all three providers accept in strict
    mode: every property required, no additional properties, no numeric bounds."""

    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    codes = [a.code for a in aspects(with_positions)]
    position: dict[str, Any] = {
        "name": {"type": "string"},
        "type": {"type": "string", "enum": ["ETF", "stock", "crypto", "cash_buffer"]},
        "target_pct": {"type": "number", "description": "Target allocation in %"},
        "buy_threshold_pct": {"type": "number", "description": "Relative, -100 to 0"},
        "sell_threshold_pct": {"type": "number", "description": "Relative, 0 or more"},
        "exit": {"type": "boolean"},
        "rationale": {"type": "string", "description": "Why the position, in markdown"},
    }
    return obj(
        {
            "prompt_id": {"type": "string", "enum": [prompt_id]},
            "aspects": {
                "type": "array",
                "items": obj(
                    {
                        "code": {"type": "string", "enum": codes},
                        "score": {"type": "number", "description": "0 to 10 in steps of 0.5"},
                        "reasoning": {"type": "string"},
                    }
                ),
            },
            "verdict": {"type": "string", "enum": [v.value for v in Verdict]},
            "verdict_reason": {
                "type": "string",
                "description": "Why this verdict, in one to three sentences",
            },
            "sources": {
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
            },
            "suggestions": {
                "type": "array",
                "items": obj(
                    {
                        "kind": {
                            "type": "string",
                            "enum": [k.value for k in SuggestionKind if k.is_suggestion],
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why, in one or two sentences",
                        },
                        "section": {
                            "type": ["integer", "null"],
                            "description": f"thesis_section: 1 to {SECTION_COUNT}",
                        },
                        "text": {
                            "type": ["string", "null"],
                            "description": "thesis_section: the new text of the section in "
                            "markdown, without its heading",
                        },
                        "ticker": {"type": ["string", "null"]},
                        **{k: {**v, "type": [v["type"], "null"]} for k, v in position.items()},
                    }
                ),
            },
            "proposals": {
                "type": "array",
                "items": obj(
                    {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "positions": {
                            "type": "array",
                            "items": obj({"ticker": {"type": "string"}, **position}),
                        },
                    }
                ),
            },
        }
    )


@dataclass(frozen=True)
class ParsedAspect:
    code: str
    half_points: int
    reasoning: str


@dataclass(frozen=True)
class ParsedSuggestion:
    """A suggestion or proposal as stored (REV-07, REV-22): what Take over applies."""

    kind: SuggestionKind
    content_md: str
    change: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedReview:
    aspects: list[ParsedAspect]
    verdict: Verdict
    verdict_reason: str
    sources: list[SourceAnswer]
    suggestions: list[ParsedSuggestion]


def _position(p: PositionAnswer | SuggestionAnswer) -> dict[str, Any]:
    """A target-structure row as stored in a change; decimals as strings, so they stay
    exact."""
    assert p.ticker is not None
    return {
        "ticker": p.ticker.strip().upper(),
        "name": (p.name or "").strip(),
        "type": p.type,
        "target_pct": str(p.target_pct),
        "buy_threshold_pct": str(p.buy_threshold_pct),
        "sell_threshold_pct": str(p.sell_threshold_pct),
        "exit": bool(p.exit),
        "rationale_md": (p.rationale or "").strip(),
    }


def _invalid(where: str, error: str) -> Message:
    return msg("answer_field_invalid", field=where, error=error)


def _suggestion(
    i: int, s: SuggestionAnswer, tickers: Collection[str] | None
) -> tuple[ParsedSuggestion | None, list[Message]]:
    """Checks one suggestion against its kind and the reviewed positions (REV-07)."""
    where = f"suggestions.{i}"
    kind = SuggestionKind(s.kind)
    if kind == SuggestionKind.THESIS_SECTION:
        if s.section is None or not 1 <= s.section <= SECTION_COUNT:
            return None, [_invalid(f"{where}.section", f"must be 1 to {SECTION_COUNT}")]
        if not (s.text or "").strip():
            return None, [_invalid(f"{where}.text", "the new text of the section is missing")]
        change = {"section": s.section, "text": (s.text or "").strip()}
        return ParsedSuggestion(kind, s.reason.strip(), change), []
    ticker = (s.ticker or "").strip().upper()
    if not ticker:
        return None, [_invalid(f"{where}.ticker", "is missing")]
    known = tickers is None or ticker in tickers
    if kind == SuggestionKind.POSITION_ADD:
        if tickers is not None and ticker in tickers:
            return None, [_invalid(f"{where}.ticker", f"{ticker} is already a position")]
        missing = [
            f
            for f in ("name", "type", "target_pct", "buy_threshold_pct", "sell_threshold_pct")
            if getattr(s, f) is None
        ]
        if missing:
            return None, [_invalid(f"{where}.{f}", "is missing") for f in missing]
        row = _position(s)
        problems = [_invalid(f"{where}.{f}", e) for f, e in position_problems(row)]
        return (
            (None, problems)
            if problems
            else (
                ParsedSuggestion(kind, s.reason.strip(), {"position": row}),
                [],
            )
        )
    if not known:
        return None, [_invalid(f"{where}.ticker", f"{ticker} is not a position")]
    if kind == SuggestionKind.POSITION_REMOVE:
        return ParsedSuggestion(kind, s.reason.strip(), {"ticker": ticker}), []
    values = {f: getattr(s, "rationale" if f == "rationale_md" else f) for f in POSITION_FIELDS}
    given = {f: v for f, v in values.items() if v is not None}
    if len(given) != 1:
        return None, [_invalid(where, "change exactly one field of the position")]
    [(name, value)] = given.items()
    value = str(value) if isinstance(value, Decimal) else value
    problems = [_invalid(f"{where}.{f}", e) for f, e in position_problems({name: value})]
    if problems:
        return None, problems
    change = {"ticker": ticker, "field": name, "value": value}
    return ParsedSuggestion(kind, s.reason.strip(), change), []


def _proposal(i: int, p: ProposalAnswer) -> tuple[ParsedSuggestion | None, list[Message]]:
    """REV-22: a whole target structure that could be activated as it is (POL-05)."""
    where = f"proposals.{i}"
    rows = [_position(row) for row in p.positions]
    problems = [
        _invalid(f"{where}.positions.{k}.{f}", e)
        for k, row in enumerate(rows)
        for f, e in position_problems(row)
    ]
    problems += [_invalid(f"{where}.positions", e) for e in structure_problems(rows)]
    if problems:
        return None, problems
    change = {"name": p.name.strip(), "positions": rows}
    return ParsedSuggestion(SuggestionKind.PROPOSAL, p.description.strip(), change), []


def _suggestions(
    answer: Answer, tickers: Collection[str] | None, with_positions: bool
) -> tuple[list[ParsedSuggestion], list[Message]]:
    parsed: list[ParsedSuggestion] = []
    problems: list[Message] = []
    results = [_suggestion(i, s, tickers) for i, s in enumerate(answer.suggestions)]
    if not with_positions:  # proposals only for a thesis without positions (REV-22)
        if len(answer.proposals) > MAX_PROPOSALS:
            problems.append(_invalid("proposals", f"at most {MAX_PROPOSALS}"))
        results += [_proposal(i, p) for i, p in enumerate(answer.proposals)]
    for suggestion, found in results:
        problems += found
        if suggestion is not None:
            parsed.append(suggestion)
    return parsed, problems


def _valid_score(score: float) -> bool:
    try:
        to_half_points(score)
    except ValueError:
        return False
    return True


def _json_object(text: str) -> tuple[Any, Message | None]:
    """The JSON object in the text; text around it (e.g. a code fence) is ignored."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None, msg("answer_no_json")
    try:
        return json.loads(match.group(0)), None
    except json.JSONDecodeError as e:
        return None, msg("answer_json_invalid", error=f"{e.msg}, line {e.lineno} column {e.colno}")


def answer_prompt_id(text: str) -> str | None:
    """The prompt ID an answer repeats, if it has one (REV-19)."""
    data, _ = _json_object(text)
    value = data.get("prompt_id") if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) else None


def check_answer(
    text: str,
    prompt_id: str,
    with_positions: bool,
    tickers: Collection[str] | None = None,
) -> tuple[ParsedReview | None, list[Message]]:
    """The parsed answer, or every problem found in it, each saying where it is (REV-18).
    The answer must repeat the ID of its prompt (REV-19) and score P1-P6 exactly when the
    reviewed content has positions (REV-02). Suggestions must fit the reviewed positions
    (`tickers`, unchecked if None, REV-07); proposals count only without positions
    (REV-22)."""
    data, problem = _json_object(text)
    if problem:
        return None, [problem]
    try:
        answer = Answer.model_validate(data)
    except ValidationError as e:
        return None, [
            msg(
                "answer_field_invalid",
                field=".".join(str(part) for part in error["loc"]) or "answer",
                error=error["msg"],
            )
            for error in e.errors()
        ]
    problems: list[Message] = []
    if answer.prompt_id.strip() != prompt_id:
        problems.append(msg("answer_prompt_id_wrong", prompt_id=prompt_id))
    expected = [a.code for a in aspects(with_positions)]
    if sorted(a.code for a in answer.aspects) != sorted(expected):
        problems.append(msg("answer_aspects_wrong", aspects=", ".join(expected)))
    problems.extend(
        msg("score_invalid", score=a.score) for a in answer.aspects if not _valid_score(a.score)
    )
    suggestions, suggestion_problems = _suggestions(answer, tickers, with_positions)
    problems.extend(suggestion_problems)
    if problems:
        return None, problems
    order = {code: i for i, code in enumerate(expected)}
    parsed = [
        ParsedAspect(a.code, to_half_points(a.score), a.reasoning.strip())
        for a in sorted(answer.aspects, key=lambda a: order[a.code])
    ]
    return (
        ParsedReview(
            parsed,
            answer.verdict,
            answer.verdict_reason.strip(),
            answer.sources,
            suggestions,
        ),
        [],
    )


def parse_answer(
    text: str, prompt_id: str, with_positions: bool, tickers: Collection[str] | None = None
) -> ParsedReview:
    """The answer of an AI reviewer; an invalid one fails the review (REV-08)."""
    parsed, problems = check_answer(text, prompt_id, with_positions, tickers)
    if parsed is None:
        raise LlmError(problems[0])
    return parsed


# --- Prompt ID -------------------------------------------------------------------------

_ISSUED = "%Y%m%dT%H%M%SZ"
_PROMPT_ID = re.compile(r"^R(\d+)-(\d{8}T\d{6}Z)-(\d+)(-[0-9a-f]{16})?-([0-9a-f]{6})$")


@dataclass(frozen=True)
class PromptRef:
    """What a prompt ID stands for (REV-19): the reviewed version, when the prompt was
    made from it (a later change of the draft makes the review outdated, REV-09) and the
    news period (REV-04)."""

    version_id: int
    issued_at: datetime
    news_days: int
    fingerprint: str = ""  # of the content the prompt was made from (REV-09)

    @property
    def prompt_id(self) -> str:
        body = (
            f"R{self.version_id}-{self.issued_at.astimezone(UTC).strftime(_ISSUED)}"
            f"-{self.news_days}" + (f"-{self.fingerprint}" if self.fingerprint else "")
        )
        return f"{body}-{_checksum(body)}"

    @property
    def news_from(self) -> date:
        return (self.issued_at - timedelta(days=self.news_days)).date()

    @property
    def news_to(self) -> date:
        return self.issued_at.date()


def _checksum(body: str) -> str:
    """Catches IDs that were mistyped or changed by the AI; not a secret."""
    return hashlib.sha256(body.encode()).hexdigest()[:6]


def parse_prompt_id(prompt_id: str) -> PromptRef | None:
    """The reference of a prompt ID, or None if it is not one. IDs of prompts from before
    scoring version 3 (thesis or policy reviews) are not accepted any more."""
    match = _PROMPT_ID.match(prompt_id.strip())
    if not match:
        return None
    version_id, issued, news_days, fingerprint, check = match.groups()
    body = f"R{version_id}-{issued}-{news_days}{fingerprint or ''}"
    if _checksum(body) != check:
        return None
    return PromptRef(
        version_id=int(version_id),
        issued_at=datetime.strptime(issued, _ISSUED).replace(tzinfo=UTC),
        news_days=int(news_days),
        fingerprint=(fingerprint or "").lstrip("-"),
    )


# --- Prompt ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewPrompt:
    """The complete review prompt (REV-19), the same for AI reviewers and manual reviews."""

    prompt_id: str
    instructions: str
    content: str  # what is reviewed: title, thesis and target structure (REV-05)
    json_schema: dict[str, Any]
    with_positions: bool  # P1-P6 are scored (REV-02)
    tickers: tuple[str, ...] = ()  # the reviewed positions, which suggestions refer to

    def llm_request(self) -> LlmRequest:
        return LlmRequest(
            system=self.instructions,
            prompt=self.content,
            json_schema=self.json_schema,
            web_search=True,  # T6 and the verdict use news (REV-04)
        )

    def text(self) -> str:
        """One text to paste into an AI outside the app (REV-18): instructions, the answer
        format and the content."""
        return f"""{self.instructions}

---

{self.content}

---

The answer format as JSON Schema:

```json
{json.dumps(self.json_schema, indent=2)}
```"""


def _answer_format(prompt_id: str) -> str:
    return f"""Answer with one JSON object in the given answer format and nothing else.
Repeat this prompt ID exactly in the field prompt_id: {prompt_id}"""


# --- Request --------------------------------------------------------------------------


def _aspect_list(items: tuple[Aspect, ...]) -> str:
    return "\n".join(f"- {a.code} {a.name}: {a.guide}" for a in items)


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


def _content(version: PolicyVersion) -> str:
    """REV-05, REV-19: the title, the thesis and the target structure; nothing else."""
    structure = _structure(version) if version.positions else "(no positions yet)"
    return (
        f"Title: {version.thesis_title}\n\n<thesis>\n{version.thesis_md}\n</thesis>\n\n"
        f"<target_structure>\n{structure}\n</target_structure>"
    )


def _structure_part(with_positions: bool) -> str:
    if not with_positions:
        return """The policy has no positions yet, so its target structure is not scored: score
only T1 to T6."""
    return f"""Aspects P1 to P6 judge whether the target structure matches the thesis: 0 means
it does not match the thesis at all, 10 a perfect match. They judge only the thesis and
the target structure given here, not the news.

Thresholds are relative to the target: absolute threshold = target x (1 + threshold/100).
Example: target 40 %, sell threshold +25 % -> sell above 50 %. Positions with exit = yes
are sold completely in the next rebalancing. Sell proceeds are always reinvested. A
position of type cash_buffer holds cash for buying dips.

Target-structure aspects:
{_aspect_list(POLICY_ASPECTS)}"""


def _proposal_part(with_positions: bool) -> str:
    if with_positions:
        return "Leave proposals empty."
    return f"""As the policy has no positions yet, propose 1 to {MAX_PROPOSALS} target structures
that follow from the thesis, each with a short name, a description of how it differs from
the others and its positions. The targets of a proposal sum to 100 and it has at most one
position of type cash_buffer. Use real, liquid tickers. Only the assets the thesis argues
for belong in a proposal."""


def review_prompt(version: PolicyVersion, ref: PromptRef) -> ReviewPrompt:
    """REV-02 to REV-05, REV-19: one review of the whole policy: aspects T1-T6 and the
    verdict with current news, and P1-P6 if it has positions."""
    news_from, news_to = ref.news_from, ref.news_to
    with_positions = bool(version.positions)
    instructions = f"""You review an investment policy written by a private investor: its
investment thesis and the target structure that follows from it. Today is
{news_to.isoformat()}.

The thesis follows a template with eight sections: 1 Belief, 2 Investor Fit,
3 Implementation, 4 Opportunity, 5 Downside, 6 Invalidation, 7 Early Warnings,
8 Monitoring. Aspects T1 to T5 judge the text itself, section by section; if the thesis
does not use the template, judge the same content wherever it is.

Aspect T6 and the verdict judge the thesis against current news: search the web for news
from {news_from.isoformat()} to {news_to.isoformat()} on the assets the thesis is about
(take them from the thesis text), in particular on its value drivers, risks, break
conditions and warning signals. If you cannot search the web, say so in the reasoning of
T6 and in the verdict reason, judge T6 and the verdict only on what you know, and leave
the sources empty. Only T6 and the verdict use news.

Thesis aspects:
{_aspect_list(THESIS_ASPECTS)}

{_structure_part(with_positions)}

{SCORING_RULES}

Verdict on the thesis, independent of the scores, with a short reason:
- broken: the news shows that a break condition of the thesis is met.
- warning: warning signals are observed, or parts of the thesis are outdated.
- good: neither of the above.

List every news article you rely on under sources (title, publication date, link).
Every statement based on news refers to its source as [n], the position in that list
starting at 1. Do not invent sources.

Suggestions are optional, each one concrete change the investor can take over with one
click. Make none if nothing needs to change. Each suggestion has a kind and a reason; set
only the fields of its kind and leave the others null:
- thesis_section: replace the text of one section of the thesis template (section 1 to
  {SECTION_COUNT}); text is the whole new text of the section in markdown, without its
  heading.
- position_change: ticker of an existing position and exactly one new value of
  target_pct, buy_threshold_pct, sell_threshold_pct, exit or rationale.
- position_add: a new position with ticker, name, type, target_pct, buy_threshold_pct,
  sell_threshold_pct, exit and rationale.
- position_remove: ticker of the position to remove.
{_proposal_part(with_positions)}

{_answer_format(ref.prompt_id)}"""
    return ReviewPrompt(
        prompt_id=ref.prompt_id,
        instructions=instructions,
        content=_content(version),
        json_schema=_schema(with_positions, ref.prompt_id),
        with_positions=with_positions,
        tickers=tuple(p.asset.ticker for p in version.positions),
    )
