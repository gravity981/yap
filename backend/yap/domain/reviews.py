"""Aspects and scoring of reviews (spec section 3.9, REV-02, REV-03, REV-06).

A review judges a policy as a whole: its thesis (T1-T6, and the verdict) and, if it has
positions, its target structure (P1-P6). Scores are 0 to 10 in steps of 0.5 and are kept
as half points (0 to 20), so they stay exact integers. The thesis score is the average of
T1-T6, the target-structure score the average of P1-P6, and the review's score the
average of both; every average is rounded to the nearest half point (halves round up).
"""

from dataclasses import dataclass
from enum import StrEnum

# Version of the aspects, rules and LLM instructions; stored with every review (REV-06).
# Change it whenever any of them changes, so scores stay comparable, and keep the aspects
# of every earlier version in ASPECTS_BY_VERSION, so old reviews keep their names.
# Version 3: one review of thesis and target structure, semaphore verdicts (REV-03).
SCORING_VERSION = "3"

MAX_HALF_POINTS = 20  # score 10


class ReviewKind(StrEnum):
    FULL = "full"  # thesis and target structure, since scoring version 3
    # POL-20: the active version again; only the verdict and the news, no scores (REV-26)
    QUICK = "quick"
    # Reviews from before stage 2, kept in the history of their versions
    THESIS = "thesis"
    POLICY = "policy"


class Verdict(StrEnum):
    """REV-03: the verdict on the thesis, which is its semaphore (THS-04)."""

    GOOD = "good"
    WARNING = "warning"
    BROKEN = "broken"


# REV-06: the verdicts of reviews before scoring version 3
LEGACY_VERDICTS = {
    "intact": Verdict.GOOD,
    "needs_adaptation": Verdict.WARNING,
    "broken": Verdict.BROKEN,
}


def semaphore(verdict: str | None) -> Verdict | None:
    """The semaphore a stored verdict stands for, of any scoring version (REV-06)."""
    if verdict is None:
        return None
    if verdict in LEGACY_VERDICTS:
        return LEGACY_VERDICTS[verdict]
    return Verdict(verdict)


@dataclass(frozen=True)
class Aspect:
    code: str
    name: str
    guide: str  # what a high and a low score mean; given to the LLM


# Version 2: the aspects follow the sections of the thesis template (THS-07)
THESIS_ASPECTS = (
    Aspect(
        "T1",
        "Belief",
        "Section 1 of the template. 10: a clear claim that could be proven wrong, with a "
        "time horizon. 0: vague, cannot be checked.",
    ),
    Aspect(
        "T2",
        "Fit and implementation",
        "Sections 2 and 3. 10: the investor fit is stated and consistent with the assets; "
        "each asset has a role and a rationale, including why it rather than alternatives. "
        "0: missing or contradictory.",
    ),
    Aspect(
        "T3",
        "Opportunity",
        "Section 4. 10: concrete, measurable value drivers. 0: none, or only 'it will go up'.",
    ),
    Aspect(
        "T4",
        "Downside",
        "Section 5. 10: the main risks are named and realistic, including likelihood and "
        "impact. 0: no risks named.",
    ),
    Aspect(
        "T5",
        "Invalidation, warnings and monitoring",
        "Sections 6 to 8. 10: observable break conditions and warning signals with clear "
        "thresholds, and metrics to monitor. 0: none, or impossible to observe.",
    ),
    Aspect(
        "T6",
        "Current evidence",
        "10: recent news confirms the value drivers and no warning signals are observed. "
        "0: the news contradicts the value drivers.",
    ),
)

# Version 1, before the thesis template of THS-07; kept for the names of old reviews
THESIS_ASPECTS_V1 = (
    Aspect(
        "T1",
        "Core claim",
        "10: a clear claim that could be proven wrong, with a time horizon. "
        "0: vague, cannot be checked.",
    ),
    Aspect(
        "T2",
        "Value drivers",
        "10: concrete, measurable drivers. 0: none, or only 'it will go up'.",
    ),
    Aspect(
        "T3",
        "Risks",
        "10: the main risks are named and realistic, including likelihood and impact. "
        "0: no risks named.",
    ),
    Aspect(
        "T4",
        "Break conditions and warning signals",
        "10: observable triggers with clear thresholds. 0: none, or impossible to observe.",
    ),
    Aspect(
        "T5",
        "Fit and alternatives",
        "10: role in the portfolio, holding period and why this asset rather than "
        "alternatives are explained and consistent. 0: missing or contradictory.",
    ),
    Aspect(
        "T6",
        "Current evidence",
        "10: recent news confirms the value drivers and no warning signals are observed. "
        "0: the news contradicts the value drivers.",
    ),
)

POLICY_ASPECTS = (
    Aspect(
        "P1",
        "Coverage",
        "Every asset the thesis argues for has a position, and every position is backed "
        "by the thesis.",
    ),
    Aspect(
        "P2",
        "Weighting",
        "Target allocations reflect the conviction and role the thesis describes (core "
        "holding vs. smaller speculative position).",
    ),
    Aspect(
        "P3",
        "Bands",
        "Buy and sell thresholds suit the volatility and holding period the thesis describes.",
    ),
    Aspect(
        "P4",
        "Exits",
        "Exit flags match the break conditions and what the thesis says about leaving an asset.",
    ),
    Aspect(
        "P5",
        "Concentration",
        "The diversification matches the risk profile the thesis describes.",
    ),
    Aspect("P6", "Rationales", "Each position's rationale agrees with the thesis."),
)

# The aspects of every scoring version (REV-06). Version 3 reviews thesis and target
# structure together; the aspects of the earlier separate reviews did not change in it.
_BEFORE_3 = {"1": THESIS_ASPECTS_V1, "2": THESIS_ASPECTS}


def aspects_of(kind: ReviewKind | str, scoring_version: str) -> tuple[Aspect, ...]:
    """The aspects a review was scored with; unknown versions get the current ones."""
    if kind == ReviewKind.POLICY:
        return POLICY_ASPECTS
    if kind == ReviewKind.THESIS:
        return _BEFORE_3.get(scoring_version, THESIS_ASPECTS)
    return THESIS_ASPECTS + POLICY_ASPECTS


def to_half_points(score: float) -> int:
    """A score from 0 to 10 in steps of 0.5 as half points; anything else is rejected."""
    half = score * 2
    if half != int(half) or not 0 <= half <= MAX_HALF_POINTS:
        raise ValueError(f"Score {score} is not between 0 and 10 in steps of 0.5")
    return int(half)


def total_half_points(half_points: list[int]) -> int:
    """Average of the aspects, rounded to the nearest half point; halves round up."""
    if not half_points:
        raise ValueError("A review has at least one aspect")
    # Integer arithmetic: floor(sum / n + 1/2) without floating point
    n = len(half_points)
    return (2 * sum(half_points) + n) // (2 * n)


def score(half_points: int) -> float:
    return half_points / 2


@dataclass(frozen=True)
class Scores:
    """The scores of a review in half points (REV-02); None where nothing was scored."""

    thesis: int | None  # T1-T6
    structure: int | None  # P1-P6; none without positions
    total: int | None  # the review's score: both averaged, or the one there is


def scores_of(half_points: dict[str, int]) -> Scores:
    """The thesis, target-structure and review scores from the aspect scores by code."""
    thesis = [v for code, v in half_points.items() if code.startswith("T")]
    structure = [v for code, v in half_points.items() if code.startswith("P")]
    t = total_half_points(thesis) if thesis else None
    p = total_half_points(structure) if structure else None
    parts = [x for x in (t, p) if x is not None]
    return Scores(t, p, total_half_points(parts) if parts else None)
