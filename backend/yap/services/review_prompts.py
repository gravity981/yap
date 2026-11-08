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
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from yap.db.models import PolicyVersion
from yap.domain.reviews import ASPECTS, ReviewKind, Verdict, to_half_points
from yap.llm import LlmError
from yap.llm.base import LlmRequest
from yap.messages import Message, msg

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
    prompt_id: str
    aspects: list[AspectAnswer]
    verdict: Verdict
    sources: list[SourceAnswer]
    suggestions: list[SuggestionAnswer]


class PolicyAnswer(_Model):
    prompt_id: str
    aspects: list[AspectAnswer]
    suggestions: list[SuggestionAnswer]


def _schema(kind: ReviewKind, prompt_id: str) -> dict[str, Any]:
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
    properties: dict[str, Any] = {
        "prompt_id": {"type": "string", "enum": [prompt_id]},
        "aspects": {"type": "array", "items": aspect},
    }
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
    kind: ReviewKind, text: str, prompt_id: str
) -> tuple[ParsedReview | None, list[Message]]:
    """The parsed answer, or every problem found in it, each saying where it is (REV-18).
    The answer must repeat the ID of its prompt (REV-19)."""
    data, problem = _json_object(text)
    if problem:
        return None, [problem]
    try:
        answer: ThesisAnswer | PolicyAnswer = (
            ThesisAnswer.model_validate(data)
            if kind == ReviewKind.THESIS
            else PolicyAnswer.model_validate(data)
        )
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
    expected = [a.code for a in ASPECTS[kind]]
    if sorted(a.code for a in answer.aspects) != expected:
        problems.append(msg("answer_aspects_wrong", aspects=", ".join(expected)))
    problems.extend(
        msg("score_invalid", score=a.score) for a in answer.aspects if not _valid_score(a.score)
    )
    if problems:
        return None, problems
    aspects = [
        ParsedAspect(a.code, to_half_points(a.score), a.reasoning.strip())
        for a in sorted(answer.aspects, key=lambda a: a.code)
    ]
    if isinstance(answer, ThesisAnswer):
        return ParsedReview(aspects, answer.verdict, answer.sources, answer.suggestions), []
    return ParsedReview(aspects, None, [], answer.suggestions), []


def parse_answer(kind: ReviewKind, text: str, prompt_id: str) -> ParsedReview:
    """The answer of an AI reviewer; an invalid one fails the review (REV-08)."""
    parsed, problems = check_answer(kind, text, prompt_id)
    if parsed is None:
        raise LlmError(problems[0])
    return parsed


# --- Prompt ID -------------------------------------------------------------------------

_ISSUED = "%Y%m%dT%H%M%SZ"
_PROMPT_ID = re.compile(r"^([TP])(\d+)-(\d{8}T\d{6}Z)-(\d+)-([0-9a-f]{6})$")


@dataclass(frozen=True)
class PromptRef:
    """What a prompt ID stands for (REV-19): the reviewed draft, when the prompt was made
    from it (a later change of the draft makes the review outdated, REV-09) and the news
    period of a thesis review."""

    kind: ReviewKind
    draft_id: int
    issued_at: datetime
    news_days: int  # 0 for policy reviews

    @property
    def prompt_id(self) -> str:
        body = (
            f"{'T' if self.kind == ReviewKind.THESIS else 'P'}{self.draft_id}"
            f"-{self.issued_at.astimezone(UTC).strftime(_ISSUED)}-{self.news_days}"
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
    """The reference of a prompt ID, or None if it is not one."""
    match = _PROMPT_ID.match(prompt_id.strip())
    if not match:
        return None
    letter, draft_id, issued, news_days, check = match.groups()
    body = f"{letter}{draft_id}-{issued}-{news_days}"
    if _checksum(body) != check:
        return None
    return PromptRef(
        kind=ReviewKind.THESIS if letter == "T" else ReviewKind.POLICY,
        draft_id=int(draft_id),
        issued_at=datetime.strptime(issued, _ISSUED).replace(tzinfo=UTC),
        news_days=int(news_days),
    )


# --- Prompt ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewPrompt:
    """The complete review prompt (REV-19), the same for AI reviewers and manual reviews."""

    prompt_id: str
    instructions: str
    content: str  # what is reviewed: thesis, and for a policy review its target structure
    json_schema: dict[str, Any]
    web_search: bool

    def llm_request(self) -> LlmRequest:
        return LlmRequest(
            system=self.instructions,
            prompt=self.content,
            json_schema=self.json_schema,
            web_search=self.web_search,
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


# --- Requests --------------------------------------------------------------------------


def _aspect_list(kind: ReviewKind) -> str:
    return "\n".join(f"- {a.code} {a.name}: {a.guide}" for a in ASPECTS[kind])


def _thesis_text(version: PolicyVersion) -> str:
    return (
        f"Title: {version.thesis_title}\nStatus set by the investor: {version.thesis_status}\n\n"
        f"<thesis>\n{version.thesis_md}\n</thesis>"
    )


def thesis_prompt(version: PolicyVersion, ref: PromptRef) -> ReviewPrompt:
    """REV-02 to REV-04: aspects T1-T6 and a verdict, with current news."""
    news_from, news_to = ref.news_from, ref.news_to
    instructions = f"""You review an investment thesis written by a private investor.
Today is {news_to.isoformat()}.

The thesis follows a template with eight sections: 1 Belief, 2 Investor Fit,
3 Implementation, 4 Opportunity, 5 Downside, 6 Invalidation, 7 Early Warnings,
8 Monitoring. Aspects T1 to T5 judge the text itself, section by section; if the thesis
does not use the template, judge the same content wherever it is.

Aspect T6 and the verdict judge the thesis against current news: search the web for news
from {news_from.isoformat()} to {news_to.isoformat()} on the assets the thesis is about
(take them from the thesis text), in particular on its value drivers, risks, break
conditions and warning signals. If you cannot search the web, say so in the reasoning of
T6, score T6 only on what you know, and leave the sources empty.

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
status (thesis_status). Make none if nothing needs to change.

{_answer_format(ref.prompt_id)}"""
    return ReviewPrompt(
        prompt_id=ref.prompt_id,
        instructions=instructions,
        content=_thesis_text(version),
        json_schema=_schema(ReviewKind.THESIS, ref.prompt_id),
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


def policy_prompt(version: PolicyVersion, ref: PromptRef) -> ReviewPrompt:
    """REV-02, REV-05: aspects P1-P6 from thesis and target structure; no web search."""
    instructions = f"""You review the target structure of an investment policy written by a
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
flags of positions (policy_position). Make none if nothing needs to change.

{_answer_format(ref.prompt_id)}"""
    content = (
        f"{_thesis_text(version)}\n\n<target_structure>\n{_structure(version)}\n</target_structure>"
    )
    return ReviewPrompt(
        prompt_id=ref.prompt_id,
        instructions=instructions,
        content=content,
        json_schema=_schema(ReviewKind.POLICY, ref.prompt_id),
        web_search=False,
    )
