"""Policies and their versions (POL-01 to POL-13); a version holds its thesis (THS-01)."""

import difflib
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import (
    Investor,
    Policy,
    PolicyPosition,
    PolicyVersion,
    Portfolio,
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
    thesis_title: str | None = None,
    thesis_md: str = "",
) -> Policy:
    """Creates a policy whose draft v1 holds the given thesis and no positions (POL-01).
    The thesis title defaults to the policy name."""
    require_investor(actor)
    name = require_text(name, "name", msg("name_required"))
    if session.scalar(select(Policy).where(Policy.owner_id == actor.id, Policy.name == name)):
        raise ConflictError(msg("policy_name_taken", name=name))
    title = (thesis_title or "").strip() or name
    now = clock.now()
    policy = Policy(owner_id=actor.id, name=name, created_at=now)
    session.add(policy)
    session.flush()
    session.add(
        PolicyVersion(
            policy_id=policy.id,
            version_no=1,
            thesis_title=title,
            thesis_md=thesis_md,
            updated_at=now,
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
        thesis_title=latest.thesis_title,
        thesis_md=latest.thesis_md,
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


@dataclass(frozen=True)
class ThesisSpec:
    """The thesis of a draft as entered or imported (THS-01); it has no status (THS-04)."""

    title: str
    content_md: str


def update_thesis(
    session: Session, actor: Investor, clock: Clock, policy_id: int, thesis: ThesisSpec
) -> PolicyVersion:
    """Replaces the thesis of the draft."""
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    _set_thesis(draft, thesis)
    draft.updated_at = clock.now()  # an earlier review is now outdated (REV-09)
    session.flush()
    return draft


def _set_thesis(draft: PolicyVersion, thesis: ThesisSpec) -> None:
    draft.thesis_title = require_text(thesis.title, "thesis_title", msg("title_required"))
    draft.thesis_md = thesis.content_md


def update_draft(
    session: Session,
    actor: Investor,
    clock: Clock,
    policy_id: int,
    *,
    positions: list[PositionSpec],
    thesis: ThesisSpec | None = None,
) -> PolicyVersion:
    """Replaces the target structure of the draft, and its thesis if given."""
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    validate_position_specs(positions)
    if thesis is not None:
        _set_thesis(draft, thesis)
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


def delete_draft(session: Session, actor: Investor, policy_id: int) -> bool:
    """POL-16: discards the draft with its reviews; the policy is back to its active
    version. A policy that was never activated is deleted with its draft. Returns whether
    the policy was deleted."""
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    reviews.delete_with_draft(session, draft)
    never_activated = all(v.activated_at is None for v in policy.versions)
    session.delete(draft)
    session.flush()
    if never_activated:  # no portfolio can follow it (PTF-02), nothing refers to it
        session.delete(policy)
        session.flush()
        return True
    session.refresh(policy)
    return False


def update_change_note(
    session: Session, actor: Investor, clock: Clock, policy_id: int, note: str | None
) -> PolicyVersion:
    """POL-14, POL-17: the change note of the draft, saved like every other change."""
    policy = get_policy(session, actor, policy_id)
    draft = _require_draft(policy)
    draft.change_note = note.strip() if note and note.strip() else None
    session.flush()
    return draft


SHARING_LEVELS = ("private", "text", "all")


def rename_policy(session: Session, actor: Investor, policy_id: int, name: str) -> Policy:
    """POL-21: the name of a policy and with it the labels of its versions (`<name>-v1`);
    timeline entries keep the name they were written with."""
    policy = get_policy(session, actor, policy_id)
    name = require_text(name, "name", msg("name_required"))
    taken = session.scalar(
        select(Policy).where(
            Policy.owner_id == actor.id, Policy.name == name, Policy.id != policy.id
        )
    )
    if taken is not None:
        raise ConflictError(msg("policy_name_taken", name=name))
    policy.name = name
    session.flush()
    return policy


def set_sharing(
    session: Session, actor: Investor, clock: Clock, policy_id: int, level: str
) -> Policy:
    """POL-18: private, text (the thesis of the active version) or all (thesis and target
    structure). Only a policy whose active version has a review can be shared (REV-20)."""
    policy = get_policy(session, actor, policy_id)
    if level not in SHARING_LEVELS:
        raise ValidationError.single(msg("sharing_level_unknown", level=level), "sharing")
    if level != "private":
        active = active_version(policy, clock.now())
        # A quick review has no score; sharing needs a reviewed version (REV-20, REV-26)
        review = reviews.scored_review(active) if active is not None else None
        if review is None:
            raise ConflictError(msg("sharing_needs_review", name=policy.name))
    policy.sharing = level
    session.flush()
    return policy


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
    # POL-17: the note given with the activation, or the one saved with the draft
    given = change_note if change_note is not None else draft.change_note
    note = given.strip() if given and given.strip() else None
    if draft.version_no > 1 and not note:
        raise ValidationError.single(msg("change_note_required_v2"), "change_note")
    now = clock.now()
    draft.mark = reviews.prepare_activation(session, draft, now)  # REV-11, REV-20
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
    thesis_changed: bool  # title or text
    thesis_diff: str  # unified diff of title and text, empty if they are the same


_COMPARED_FIELDS = ("target_pct", "buy_threshold_pct", "sell_threshold_pct", "exit", "rationale_md")


def compare_versions(old: PolicyVersion, new: PolicyVersion) -> VersionDiff:
    """POL-09: changed positions, targets, thresholds, exit flags, and whether the thesis
    changed."""
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

    def text(v: PolicyVersion) -> list[str]:
        return f"# {v.thesis_title}\n{v.thesis_md.rstrip()}\n".splitlines(keepends=True)

    lines = difflib.unified_diff(
        text(old),
        text(new),
        fromfile=f"v{old.version_no}",
        tofile=f"v{new.version_no}",
    )
    return VersionDiff(
        positions=changes,
        thesis_changed=(old.thesis_title, old.thesis_md) != (new.thesis_title, new.thesis_md),
        thesis_diff="".join(lines),
    )


def get_version(session: Session, actor: Investor, version_id: int) -> PolicyVersion:
    require_investor(actor)
    version = session.get(PolicyVersion, version_id)
    if version is None or version.policy.owner_id != actor.id:
        raise NotFoundError(msg("policy_version_not_found", id=version_id))
    return version
