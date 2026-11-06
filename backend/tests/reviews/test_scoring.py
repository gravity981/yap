import pytest

from yap.domain.reviews import (
    POLICY_ASPECTS,
    THESIS_ASPECTS,
    score,
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
