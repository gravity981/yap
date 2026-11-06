"""Aspects and scoring of thesis and policy reviews (spec section 3.9, REV-02, REV-06).

Scores are 0 to 10 in steps of 0.5 and are kept as half points (0 to 20), so they stay
exact integers. The total is the average of the aspect scores, all weighing the same,
rounded to the nearest half point (halves round up).
"""

from dataclasses import dataclass
from enum import StrEnum

# Version of the aspects, rules and LLM instructions; stored with every review (REV-06).
# Change it whenever any of them changes, so scores stay comparable.
SCORING_VERSION = "1"

MAX_HALF_POINTS = 20  # score 10


class ReviewKind(StrEnum):
    THESIS = "thesis"
    POLICY = "policy"


class Verdict(StrEnum):
    """REV-03; the same values as the thesis status (THS-04)."""

    INTACT = "intact"
    NEEDS_ADAPTATION = "needs_adaptation"
    BROKEN = "broken"


@dataclass(frozen=True)
class Aspect:
    code: str
    name: str
    guide: str  # what a high and a low score mean; given to the LLM


THESIS_ASPECTS = (
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
    Aspect("P4", "Exits", "Exit flags match the thesis status and its break conditions."),
    Aspect(
        "P5",
        "Concentration",
        "The diversification matches the risk profile the thesis describes.",
    ),
    Aspect("P6", "Rationales", "Each position's rationale agrees with the thesis."),
)

ASPECTS = {ReviewKind.THESIS: THESIS_ASPECTS, ReviewKind.POLICY: POLICY_ASPECTS}


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
