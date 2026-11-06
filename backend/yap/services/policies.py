"""Policies and their versions (POL-01 to POL-13)."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import (
    Investor,
    Policy,
    PolicyPosition,
    PolicyVersion,
    Portfolio,
    ThesisRevision,
)
from yap.domain.rebalancing import MultipleCashBuffersError, TargetSumError
from yap.domain.types import (
    BUY_THRESHOLD_MAX,
    BUY_THRESHOLD_MIN,
    HUNDRED,
    SELL_THRESHOLD_MIN,
    TARGET_SUM_TOLERANCE,
    AssetType,
)
from yap.messages import Message, msg
from yap.services import reviews
from yap.services.assets import get_or_create_asset, normalize_ticker
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
    get_owned,
    require_investor,
    require_text,
)
from yap.services.theses import (
    activated_revisions,
    can_read_revision,
    get_readable_thesis,
    readable_revisions,
)
from yap.services.timeline import EventType, add_event
from yap.services.versioning import active_version


@dataclass(frozen=True)
class PositionSpec:
    """A target-structure row as entered or imported (POL-02)."""

    ticker: str
    target_pct: Decimal
    buy_threshold_pct: Decimal
    sell_threshold_pct: Decimal
    name: str | None = None
    type: AssetType | str | None = None
    exit: bool = False
    rationale_md: str = ""


def create_policy(
    session: Session,
    actor: Investor,
    clock: Clock,
    *,
    name: str,
    thesis_id: int,
) -> Policy:
    """Creates a policy with an empty draft v1 pinning the thesis' latest readable,
    activated revision (POL-01)."""
    require_investor(actor)
    name = require_text(name, "name", msg("name_required"))
    if session.scalar(select(Policy).where(Policy.owner_id == actor.id, Policy.name == name)):
        raise ConflictError(msg("policy_name_taken", name=name))
    thesis = get_readable_thesis(session, actor, thesis_id)
    revisions = activated_revisions(readable_revisions(session, actor, thesis))
    if not revisions:
        raise ValidationError.single(msg("thesis_not_activated"), "thesis_id")
    now = clock.now()
    policy = Policy(owner_id=actor.id, name=name, created_at=now)
    session.add(policy)
    session.flush()
    session.add(
        PolicyVersion(
            policy_id=policy.id,
            version_no=1,
            thesis_revision_id=revisions[-1].id,
            created_at=now,
        )
    )
    session.flush()
    session.refresh(policy)
    return policy


def list_policies(session: Session, actor: Investor) -> list[Policy]:
    require_investor(actor)
    return list(
        session.scalars(select(Policy).where(Policy.owner_id == actor.id).order_by(Policy.name))
    )


def get_policy(session: Session, actor: Investor, policy_id: int) -> Policy:
    return get_owned(session, Policy, policy_id, actor)


def get_draft(policy: Policy) -> PolicyVersion | None:
    return next((v for v in policy.versions if v.activated_at is None), None)


def _require_draft(policy: Policy) -> PolicyVersion:
    draft = get_draft(policy)
    if draft is None:
        raise NotFoundError(msg("policy_has_no_draft", name=policy.name))
    return draft


def create_draft(session: Session, actor: Investor, clock: Clock, policy_id: int) -> PolicyVersion:
    """A new draft is a copy of the latest version; at most one draft (POL-06)."""
    policy = get_policy(session, actor, policy_id)
    _require_not_archived(policy)
    if get_draft(policy) is not None:
        raise ConflictError(msg("policy_has_draft", name=policy.name))
    latest = policy.versions[-1]
    draft = PolicyVersion(
        policy_id=policy.id,
        version_no=latest.version_no + 1,
        thesis_revision_id=latest.thesis_revision_id,
        updated_at=clock.now(),
        created_at=clock.now(),
        positions=[
            PolicyPosition(
                asset_id=p.asset_id,
                target_pct=p.target_pct,
                buy_threshold_pct=p.buy_threshold_pct,
                sell_threshold_pct=p.sell_threshold_pct,
                exit=p.exit,
                rationale_md=p.rationale_md,
                sort_order=p.sort_order,
            )
            for p in latest.positions
        ],
    )
    session.add(draft)
    session.flush()
    session.refresh(policy)
    return draft


def validate_position_specs(positions: list[PositionSpec], path: str = "positions") -> None:
    """Row-level rules (POL-04, IMP-05); the sum rule is checked at activation."""
    problems: list[tuple[str, Message]] = []
    seen: set[str] = set()
    cash_buffers = 0
    for i, p in enumerate(positions):
        row = f"{path}[{i}]"
        ticker = normalize_ticker(p.ticker)
        if ticker in seen:
            problems.append((f"{row}.ticker", msg("ticker_duplicate", ticker=ticker)))
        seen.add(ticker)
        if p.target_pct < 0 or p.target_pct > HUNDRED:
            problems.append((f"{row}.target_pct", msg("target_range")))
        if not BUY_THRESHOLD_MIN <= p.buy_threshold_pct <= BUY_THRESHOLD_MAX:
            problems.append((f"{row}.buy_threshold_pct", msg("buy_threshold_range")))
        if p.sell_threshold_pct < SELL_THRESHOLD_MIN:
            problems.append((f"{row}.sell_threshold_pct", msg("sell_threshold_min")))
        if p.type is not None and str(p.type) == AssetType.CASH_BUFFER.value:
            cash_buffers += 1
    if cash_buffers > 1:
        problems.append((path, msg("one_cash_buffer")))
    if problems:
        raise ValidationError(problems)


def update_draft(
    session: Session,
    actor: Investor,
    clock: Clock,
    policy_id: int,
    *,
    positions: list[PositionSpec],
) -> PolicyVersion:
    """Replaces the target structure of the draft."""
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    validate_position_specs(positions)
    assets = [
        get_or_create_asset(session, p.ticker, p.name, p.type, f"positions[{i}]")
        for i, p in enumerate(positions)
    ]
    cash = [a for a in assets if a.type == AssetType.CASH_BUFFER.value]
    if len(cash) > 1:
        raise ValidationError.single(msg("one_cash_buffer"), "positions")
    draft.positions.clear()
    session.flush()
    draft.positions.extend(
        PolicyPosition(
            asset_id=asset.id,
            target_pct=p.target_pct,
            buy_threshold_pct=p.buy_threshold_pct,
            sell_threshold_pct=p.sell_threshold_pct,
            exit=p.exit,
            rationale_md=p.rationale_md,
            sort_order=i,
        )
        for i, (p, asset) in enumerate(zip(positions, assets, strict=True))
    )
    draft.updated_at = clock.now()  # an earlier review is now outdated (REV-09)
    session.flush()
    session.refresh(draft)
    return draft


def delete_draft(session: Session, actor: Investor, policy_id: int) -> None:
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    if draft.version_no == 1:
        raise ConflictError(msg("policy_first_version_kept"))
    reviews.delete_with_draft(session, draft)
    session.delete(draft)
    session.flush()
    session.refresh(policy)


def portfolios_using(session: Session, policy: Policy) -> list[Portfolio]:
    """Portfolios currently assigned to the policy (POL-08, POL-12)."""
    return list(
        session.scalars(
            select(Portfolio).where(Portfolio.policy_id == policy.id).order_by(Portfolio.name)
        )
    )


def activate_draft(
    session: Session, actor: Investor, clock: Clock, policy_id: int, change_note: str | None
) -> PolicyVersion:
    """Activates the draft now (POL-05 to POL-08). Activation time is never set by the caller."""
    policy = get_policy(session, actor, policy_id)
    _require_not_archived(policy)
    draft = _require_draft(policy)
    target_sum = sum((p.target_pct for p in draft.positions), Decimal(0))
    if abs(target_sum - HUNDRED) > TARGET_SUM_TOLERANCE:
        raise ValidationError.single(TargetSumError(target_sum).message, "positions")
    if sum(1 for p in draft.positions if p.asset.type == AssetType.CASH_BUFFER.value) > 1:
        raise ValidationError.single(MultipleCashBuffersError().message, "positions")
    note = change_note.strip() if change_note else None
    if draft.version_no > 1 and not note:
        raise ValidationError.single(msg("change_note_required_v2"), "change_note")
    now = clock.now()
    reviews.prepare_activation(session, draft)
    draft.change_note = note
    draft.activated_at = now
    session.flush()
    portfolios = portfolios_using(session, policy)
    affected = ", ".join(p.name for p in portfolios) or "no portfolios"
    add_event(
        session,
        policy.owner_id,
        now,
        EventType.POLICY_ACTIVATED,
        f"{draft.label} activated ({affected})" + (f": {note}" if note else ""),
        {"version": draft.label, "portfolios": [p.name for p in portfolios], "note": note},
        policy_version_id=draft.id,
    )
    reviews.confirm_with_draft(session, draft, policy.owner_id, now)  # REV-11
    return draft


def newer_thesis_revision(
    session: Session, actor: Investor, policy: Policy, at: datetime
) -> ThesisRevision | None:
    """POL-10: newest readable revision of the thesis, if newer than the active version's."""
    version = active_version(policy, at)
    if version is None:
        return None
    pinned = version.thesis_revision
    candidates = activated_revisions(readable_revisions(session, actor, pinned.thesis))
    newest = candidates[-1] if candidates else pinned
    return newest if newest.revision_no > pinned.revision_no else None


def adopt_newer_thesis_revision(
    session: Session, actor: Investor, clock: Clock, policy_id: int
) -> PolicyVersion:
    """POL-10: one action creates (or updates) the draft to pin the newest revision."""
    policy = get_policy(session, actor, policy_id)
    newest = newer_thesis_revision(session, actor, policy, clock.now())
    if newest is None:
        raise ConflictError(msg("policy_thesis_current"))
    draft = get_draft(policy) or create_draft(session, actor, clock, policy_id)
    draft.thesis_revision_id = newest.id
    draft.updated_at = clock.now()
    session.flush()
    session.refresh(draft)
    return draft


def set_draft_thesis_revision(
    session: Session, actor: Investor, clock: Clock, policy_id: int, revision_id: int
) -> PolicyVersion:
    """The draft may pin another revision of the policy's thesis (the thesis stays the same)."""
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    revision = session.get(ThesisRevision, revision_id)
    if (
        revision is None
        or revision.thesis_id != draft.thesis_revision.thesis_id
        or revision.is_draft
        or not can_read_revision(session, actor, revision)
    ):
        raise NotFoundError(msg("policy_thesis_revision_not_found", id=revision_id))
    draft.thesis_revision_id = revision.id
    draft.updated_at = clock.now()
    session.flush()
    session.refresh(draft)
    return draft


def archive_policy(session: Session, actor: Investor, clock: Clock, policy_id: int) -> Policy:
    """POL-13: only without assigned portfolios."""
    policy = get_policy(session, actor, policy_id)
    if portfolios_using(session, policy):
        raise ConflictError(msg("policy_has_portfolios"))
    policy.archived_at = clock.now()
    return policy


def _require_not_archived(policy: Policy) -> None:
    if policy.archived_at is not None:
        raise ConflictError(msg("policy_archived", name=policy.name))


@dataclass
class PositionChange:
    ticker: str
    change: str  # added | removed | changed
    fields: dict[str, tuple[object, object]] = field(default_factory=dict)


@dataclass
class VersionDiff:
    positions: list[PositionChange]
    thesis_revision: tuple[int, int] | None


_COMPARED_FIELDS = ("target_pct", "buy_threshold_pct", "sell_threshold_pct", "exit", "rationale_md")


def compare_versions(old: PolicyVersion, new: PolicyVersion) -> VersionDiff:
    """POL-09: changed positions, targets, thresholds, exit flags and thesis revision."""
    old_rows = {p.asset.ticker: p for p in old.positions}
    new_rows = {p.asset.ticker: p for p in new.positions}
    changes: list[PositionChange] = []
    for ticker, p in new_rows.items():
        if ticker not in old_rows:
            changes.append(PositionChange(ticker, "added"))
            continue
        before = old_rows[ticker]
        diff = {
            f: (getattr(before, f), getattr(p, f))
            for f in _COMPARED_FIELDS
            if getattr(before, f) != getattr(p, f)
        }
        if diff:
            changes.append(PositionChange(ticker, "changed", diff))
    changes.extend(PositionChange(t, "removed") for t in old_rows if t not in new_rows)
    return VersionDiff(
        positions=changes,
        thesis_revision=(old.thesis_revision.revision_no, new.thesis_revision.revision_no)
        if old.thesis_revision_id != new.thesis_revision_id
        else None,
    )


def get_version(session: Session, actor: Investor, version_id: int) -> PolicyVersion:
    require_investor(actor)
    version = session.get(PolicyVersion, version_id)
    if version is None or version.policy.owner_id != actor.id:
        raise NotFoundError(msg("policy_version_not_found", id=version_id))
    return version
