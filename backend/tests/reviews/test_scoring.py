import pytest

from yap.domain.reviews import (
    POLICY_ASPECTS,
    SCORING_VERSION,
    THESIS_ASPECTS,
    ReviewKind,
    Scores,
    Verdict,
    aspects_of,
    score,
    scores_of,
    semaphore,
    to_half_points,
    total_half_points,
)


@pytest.mark.req("REV-02")
@pytest.mark.parametrize(("value", "half"), [(0, 0), (0.5, 1), (6.5, 13), (10, 20)])
def test_scores_are_0_to_10_in_half_steps(value: float, half: int) -> None:
    assert to_half_points(value) == half
    assert score(half) == value


@pytest.mark.req("REV-02")
@pytest.mark.parametrize("value", [-0.5, 10.5, 6.3, 7.25])
def test_other_scores_are_rejected(value: float) -> None:
    with pytest.raises(ValueError, match=r"steps of 0\.5"):
        to_half_points(value)


@pytest.mark.req("REV-02")
@pytest.mark.parametrize(
    ("scores", "total"),
    [
        ((7, 7, 7, 7, 7, 7), 7),
        ((6, 6.5), 6.5),  # 6.25 -> halves round up
        ((7, 6, 8, 5, 7, 6.5), 6.5),  # 6.58
        ((10, 0, 0), 3.5),  # 3.33
        ((5, 5.5, 5.5), 5.5),  # 5.33 -> 5.5
        ((5, 5, 5.5), 5),  # 5.17 -> 5
    ],
)
def test_total_is_the_rounded_average_of_equally_weighted_aspects(
    scores: tuple[float, ...], total: float
) -> None:
    assert score(total_half_points([to_half_points(s) for s in scores])) == total


@pytest.mark.req("REV-02", "REV-03", "REV-05")
def test_six_aspects_per_review_kind() -> None:
    assert [a.code for a in THESIS_ASPECTS] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert [a.code for a in POLICY_ASPECTS] == ["P1", "P2", "P3", "P4", "P5", "P6"]


@pytest.mark.req("REV-06", "THS-07")
def test_thesis_aspects_follow_the_template_and_old_versions_keep_their_names() -> None:
    assert SCORING_VERSION == "3"
    assert [a.name for a in THESIS_ASPECTS] == [
        "Belief",
        "Fit and implementation",
        "Opportunity",
        "Downside",
        "Invalidation, warnings and monitoring",
        "Current evidence",
    ]
    # Version 3 reviews thesis and target structure together
    assert aspects_of(ReviewKind.FULL, SCORING_VERSION) == THESIS_ASPECTS + POLICY_ASPECTS
    assert aspects_of(ReviewKind.THESIS, "2") == THESIS_ASPECTS
    old = aspects_of(ReviewKind.THESIS, "1")
    assert [a.name for a in old][:2] == ["Core claim", "Value drivers"]
    # The policy aspects did not change
    assert aspects_of(ReviewKind.POLICY, "1") == POLICY_ASPECTS
    assert aspects_of(ReviewKind.THESIS, "unknown") == THESIS_ASPECTS


@pytest.mark.req("REV-02")
@pytest.mark.parametrize(
    ("thesis", "structure", "expected"),
    [
        ((7, 6, 8, 5, 7, 6.5), (8, 7, 6, 9, 7.5, 8), (6.5, 7.5, 7)),
        ((8, 8, 7, 7.5, 6, 8), (8, 7.5, 6, 7, 7, 6.5), (7.5, 7, 7.5)),  # 7.25 -> 7.5
        ((6, 6, 6, 6, 6, 6), (), (6, None, 6)),  # without positions: the thesis score
        ((), (8, 7, 6, 9, 7.5, 8), (None, 7.5, 7.5)),  # a policy review before stage 2
        ((), (), (None, None, None)),
    ],
)
def test_thesis_target_structure_and_review_scores(
    thesis: tuple[float, ...],
    structure: tuple[float, ...],
    expected: tuple[float | None, float | None, float | None],
) -> None:
    half = {f"T{i}": to_half_points(s) for i, s in enumerate(thesis, 1)}
    half |= {f"P{i}": to_half_points(s) for i, s in enumerate(structure, 1)}
    result = scores_of(half)
    assert isinstance(result, Scores)
    assert tuple(None if v is None else score(v) for v in vars(result).values()) == expected


@pytest.mark.req("REV-03", "REV-06", "THS-04")
@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("good", Verdict.GOOD),
        ("warning", Verdict.WARNING),
        ("broken", Verdict.BROKEN),
        ("intact", Verdict.GOOD),
        ("needs_adaptation", Verdict.WARNING),
        (None, None),
    ],
)
def test_old_verdicts_are_shown_as_semaphores(verdict: str | None, expected: object) -> None:
    assert semaphore(verdict) == expected
