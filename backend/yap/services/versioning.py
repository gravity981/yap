"""Which policy version applies at a point in time (POL-07, POL-12, PTF-04, CMP-03).

Kept separate because consistent history depends on it; it is fully covered by
tests (NFR-12).
"""

from dataclasses import dataclass
from datetime import datetime

from yap.db.models import Policy, PolicyVersion, Portfolio


def active_version(policy: Policy, at: datetime) -> PolicyVersion | None:
    """Version with the latest activation at or before `at` (section 4.1).

    Activations at the same instant are ordered by version number.
    """
    best: PolicyVersion | None = None
    for version in policy.versions:
        activated = version.activated_at
        if activated is None or activated > at:
            continue
        if best is None or (activated, version.version_no) > (
            best.activated_at,
            best.version_no,
        ):
            best = version
    return best


@dataclass(frozen=True)
class VersionPeriod:
    version: PolicyVersion
    active_from: datetime | None  # None: draft
    active_until: datetime | None  # None: still active, or draft


def version_periods(policy: Policy) -> list[VersionPeriod]:
    """All versions with their activation periods, oldest first, draft last (POL-12)."""
    activated = sorted(
        (v for v in policy.versions if v.activated_at is not None),
        key=lambda v: (v.activated_at, v.version_no),
    )
    periods = [
        VersionPeriod(
            v,
            v.activated_at,
            activated[i + 1].activated_at if i + 1 < len(activated) else None,
        )
        for i, v in enumerate(activated)
    ]
    periods.extend(VersionPeriod(v, None, None) for v in policy.versions if v.activated_at is None)
    return periods


def policy_at(portfolio: Portfolio, at: datetime) -> int | None:
    """ID of the policy the portfolio was assigned to at `at` (PTF-04)."""
    policy_id: int | None = None
    for assignment in portfolio.assignments:
        if assignment.valid_from <= at:
            policy_id = assignment.policy_id
    return policy_id
