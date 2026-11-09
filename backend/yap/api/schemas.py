"""Request and response bodies of the API.

Decimal values are serialized as strings in plain notation (PlainDecimal), so no precision
is lost (NFR-04); inputs accept numbers or strings.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from yap.api.decimals import PlainDecimal
from yap.db.models import (
    Asset,
    PolicyPosition,
    PolicyVersion,
    Review,
    Snapshot,
    SnapshotValue,
    TimelineEvent,
)
from yap.domain.bands import Band
from yap.prices import Provider
from yap.prices.base import NAMES
from yap.services.price_update import AutoPrice
from yap.services.snapshots import Comparison

# --- Assets -------------------------------------------------------------------


class AssetOut(BaseModel):
    ticker: str
    name: str
    type: str

    @classmethod
    def of(cls, asset: Asset) -> AssetOut:
        return cls(ticker=asset.ticker, name=asset.name, type=asset.type)


# --- Reviews in short -------------------------------------------------------


class ReviewBrief(BaseModel):
    """A review of a version, in short (THS-08, REV-02, REV-11)."""

    id: int
    kind: str  # full; thesis | policy for reviews from before stage 2
    state: str
    total: float | None  # the review's score (REV-02)
    thesis_score: float | None
    structure_score: float | None  # null without positions
    semaphore: str | None  # good | warning | broken; old verdicts mapped (REV-03, REV-06)
    scoring_version: str  # REV-06: scores of different versions are not comparable
    method: str  # REV-17: ai | manual, with the model and the AI reviewer's name
    model: str | None  # null for a manual review
    ai_reviewer_name: str | None
    outdated: bool
    completed_at: datetime | None
    saved_at: datetime | None  # REV-21: the date of the latest review

    @classmethod
    def of(
        cls, version: PolicyVersion, review: Review, score_from: Review | None = None
    ) -> ReviewBrief:
        """The review in short. The scores are its own, or those of `score_from`: a quick
        review has none (REV-26), so the version keeps the scores of its latest full one."""
        from yap.services import reviews

        scores = reviews.scores(score_from or review)
        semaphore = reviews.review_semaphore(review)
        return cls(
            id=review.id,
            kind=review.kind,
            state=review.state,
            total=half(scores.total),
            thesis_score=half(scores.thesis),
            structure_score=half(scores.structure),
            semaphore=semaphore.value if semaphore else None,
            scoring_version=review.scoring_version,
            method=review.method,
            model=review.model,
            ai_reviewer_name=review.ai_reviewer_name,
            outdated=reviews.outdated(review, version),
            completed_at=review.completed_at,
            saved_at=review.saved_at,
        )

    @classmethod
    def current(cls, version: PolicyVersion) -> ReviewBrief | None:
        """The review that gives the version its score and semaphore (REV-21)."""
        from yap.services import reviews

        review = reviews.current_review(version)
        return cls.of(version, review, reviews.scored_review(version)) if review else None


def half(half_points: int | None) -> float | None:
    return half_points / 2 if half_points is not None else None


# --- Policies -----------------------------------------------------------------


class NewPolicy(BaseModel):
    """POL-01: draft v1 holds the thesis given here (the template, filled in by the UI)."""

    name: str
    thesis_title: str | None = None  # null: the name
    thesis_md: str = ""


class ThesisIn(BaseModel):
    title: str
    content_md: str


class PositionIn(BaseModel):
    ticker: str
    name: str | None = None
    type: str | None = None
    target_pct: PlainDecimal
    buy_threshold_pct: PlainDecimal
    sell_threshold_pct: PlainDecimal
    exit: bool = False
    rationale_md: str = ""


class DraftIn(BaseModel):
    positions: list[PositionIn]
    thesis: ThesisIn | None = None  # null: the thesis stays as it is


class Activation(BaseModel):
    change_note: str | None = None


class PositionOut(BaseModel):
    ticker: str
    name: str
    type: str
    target_pct: PlainDecimal
    buy_threshold_pct: PlainDecimal
    sell_threshold_pct: PlainDecimal
    buy_abs_pct: PlainDecimal
    sell_abs_pct: PlainDecimal
    midband_pct: PlainDecimal
    exit: bool
    rationale_md: str

    @classmethod
    def of(cls, p: PolicyPosition) -> PositionOut:
        band = Band(p.target_pct, p.buy_threshold_pct, p.sell_threshold_pct)
        return cls(
            ticker=p.asset.ticker,
            name=p.asset.name,
            type=p.asset.type,
            target_pct=p.target_pct,
            buy_threshold_pct=p.buy_threshold_pct,
            sell_threshold_pct=p.sell_threshold_pct,
            buy_abs_pct=band.buy_abs,
            sell_abs_pct=band.sell_abs,
            midband_pct=band.midband,
            exit=p.exit,
            rationale_md=p.rationale_md,
        )


class VersionSummary(BaseModel):
    id: int
    version_no: int
    label: str
    thesis_title: str
    change_note: str | None
    mark: str | None  # REV-20: not_reviewed | review_did_not_match
    active_from: datetime | None
    active_until: datetime | None
    is_draft: bool
    # The review that gives the version its score and semaphore (THS-04, REV-21)
    review: ReviewBrief | None
    # All reviews of the version; more than one only for versions from before stage 2
    reviews: list[ReviewBrief]


class VersionOut(VersionSummary):
    thesis_md: str
    positions: list[PositionOut]

    @classmethod
    def of(
        cls, version: PolicyVersion, active_from: datetime | None, active_until: datetime | None
    ) -> VersionOut:
        return cls(
            **version_summary(version, active_from, active_until).model_dump(),
            thesis_md=version.thesis_md,
            positions=[PositionOut.of(p) for p in version.positions],
        )


def version_summary(
    version: PolicyVersion, active_from: datetime | None, active_until: datetime | None
) -> VersionSummary:
    from yap.services import reviews

    return VersionSummary(
        id=version.id,
        version_no=version.version_no,
        label=version.label,
        thesis_title=version.thesis_title,
        change_note=version.change_note,
        mark=reviews.effective_mark(version),  # REV-20: cleared by a later review
        active_from=active_from,
        active_until=active_until,
        is_draft=version.activated_at is None,
        review=ReviewBrief.current(version),
        reviews=[ReviewBrief.of(version, r) for r in version.reviews],
    )


class VersionRef(VersionOut):
    """A version looked up by its ID (e.g. from a timeline event), with its policy."""

    policy_id: int
    policy_name: str


class PortfolioRef(BaseModel):
    id: int
    name: str


class PolicyOut(BaseModel):
    id: int
    name: str
    archived_at: datetime | None
    created_at: datetime
    versions: list[VersionSummary]
    portfolios: list[PortfolioRef]
    # POL-11, THS-04: the semaphore of the active version is warning or broken
    thesis_warning: bool
    semaphore: str | None  # of the active version; null: not reviewed
    semaphore_reason: str | None  # PTF-07: the reason of the latest review's verdict
    mark: str | None  # REV-20: of the active version, until a later review is saved
    sharing: str  # POL-18: private | text | all
    active_version_no: int | None
    active_from: datetime | None
    latest_review: ReviewBrief | None  # REV-21: of the active version
    pending_review: ReviewBrief | None  # POL-20: running or failed, not saved yet
    draft: DraftBrief | None  # POL-19


class DraftBrief(BaseModel):
    """POL-19: a policy's draft in short."""

    version_no: int
    label: str
    updated_at: datetime | None  # last saved (POL-14)
    positions: int
    # POL-22: the thesis or target structure differs from the active version; an unchanged
    # draft is still "the same version" and reviewing it is reviewing the active version
    changed: bool
    review: ReviewBrief | None  # matches, no longer matches, or none (REV-09)


class PolicySummary(BaseModel):
    """POL-19: a policy in the policies list."""

    id: int
    name: str
    archived_at: datetime | None
    active_version_label: str | None
    has_draft: bool
    thesis_warning: bool
    semaphore: str | None
    semaphore_reason: str | None
    mark: str | None
    sharing: str
    active_version_no: int | None
    active_from: datetime | None
    latest_review: ReviewBrief | None
    pending_review: ReviewBrief | None
    draft: DraftBrief | None
    portfolios: list[PortfolioRef]


class PositionChangeOut(BaseModel):
    ticker: str
    change: str
    fields: dict[str, tuple[str, str]]


class VersionDiffOut(BaseModel):
    positions: list[PositionChangeOut]
    thesis_changed: bool
    thesis_diff: str  # unified diff of thesis title and text (POL-09)


# --- Portfolios and snapshots -------------------------------------------------


class NewPortfolio(BaseModel):
    name: str
    policy_id: int
    currency: str | None = None  # null: the investor's base currency (PTF-03)
    default_contribution: PlainDecimal = Decimal(0)
    precise_amounts: bool = False


class PortfolioSettings(BaseModel):
    default_contribution: PlainDecimal
    precise_amounts: bool
    currency: str | None = None  # null: unchanged; fixed once snapshots exist (PTF-03)


class PositionSettingsIn(BaseModel):
    broker: str | None = None  # empty or null: no broker
    whole_units: bool | None = None  # null: the default by asset type (PTF-03)


class Reassignment(BaseModel):
    policy_id: int


class AssignmentOut(BaseModel):
    policy_id: int
    policy_name: str
    valid_from: datetime


class AutoPriceOut(BaseModel):
    """CMP-01, CMP-10: an auto price with the listing, its own price and currency, the
    exchange rate and the provider's date."""

    listing_id: int
    symbol: str
    exchange: str
    provider_name: str
    listing_price: PlainDecimal
    listing_currency: str
    fx_rate: PlainDecimal
    price_date: str

    @classmethod
    def of(cls, auto: AutoPrice) -> AutoPriceOut:
        listing = auto.listing
        return cls(
            listing_id=listing.id,
            symbol=listing.symbol,
            exchange=listing.exchange,
            provider_name=NAMES[Provider(listing.provider.provider)],
            listing_price=auto.listing_price,
            listing_currency=listing.quote_currency,
            fx_rate=auto.fx_rate,
            price_date=auto.price_date,
        )

    @classmethod
    def of_row(cls, row: SnapshotValue) -> AutoPriceOut | None:
        if row.price_kind != "auto" or row.listing is None:
            return None
        assert row.listing_price is not None and row.fx_rate is not None
        assert row.price is not None and row.price_date is not None
        return cls.of(
            AutoPrice(row.listing, row.listing_price, row.fx_rate, row.price, row.price_date)
        )


class ComparisonRowOut(BaseModel):
    ticker: str
    name: str
    type: str
    units: PlainDecimal | None  # null: unknown (CMP-10) or not held
    price: PlainDecimal | None  # portfolio currency
    price_kind: str | None  # auto | manual
    auto: AutoPriceOut | None  # CMP-10: where an auto price came from
    value: PlainDecimal
    allocation_pct: PlainDecimal
    target_pct: PlainDecimal | None
    buy_abs_pct: PlainDecimal | None
    sell_abs_pct: PlainDecimal | None
    deviation_pct: PlainDecimal | None
    exit: bool
    status: str


class SnapshotSummary(BaseModel):
    id: int
    taken_at: datetime
    source: str
    corrects_snapshot_id: int | None
    policy_version_id: int
    policy_version_label: str
    total_value: PlainDecimal


class AllocationShare(BaseModel):
    ticker: str
    allocation_pct: PlainDecimal


class SnapshotListItem(SnapshotSummary):
    """CMP-08: a past snapshot with the share of every position it held."""

    allocations: list[AllocationShare]


class SnapshotOut(SnapshotSummary):
    portfolio_id: int
    currency: str  # the portfolio's (PTF-03)
    rows: list[ComparisonRowOut]

    @classmethod
    def of(cls, comparison: Comparison) -> SnapshotOut:
        s = comparison.snapshot
        return cls(
            **snapshot_summary(comparison).model_dump(),
            portfolio_id=s.portfolio_id,
            currency=s.portfolio.currency,
            rows=[
                ComparisonRowOut(
                    ticker=r.ticker,
                    name=r.name,
                    type=r.type,
                    units=r.units,
                    price=r.price,
                    price_kind=r.price_kind,
                    auto=AutoPriceOut.of_row(r.held) if r.held else None,
                    value=r.value,
                    allocation_pct=r.allocation_pct,
                    target_pct=r.band.target_pct if r.band else None,
                    buy_abs_pct=r.band.buy_abs if r.band else None,
                    sell_abs_pct=r.band.sell_abs if r.band else None,
                    deviation_pct=r.deviation_pct,
                    exit=r.exit,
                    status=r.status.value,
                )
                for r in comparison.rows
            ],
        )


def snapshot_list_item(comparison: Comparison) -> SnapshotListItem:
    return SnapshotListItem(
        **snapshot_summary(comparison).model_dump(),
        allocations=[
            AllocationShare(ticker=r.ticker, allocation_pct=r.allocation_pct)
            for r in comparison.rows
            if r.value > 0
        ],
    )


def snapshot_summary(comparison: Comparison) -> SnapshotSummary:
    s: Snapshot = comparison.snapshot
    return SnapshotSummary(
        id=s.id,
        taken_at=s.taken_at,
        source=s.source,
        corrects_snapshot_id=s.corrects_snapshot_id,
        policy_version_id=s.policy_version_id,
        policy_version_label=s.policy_version.label,
        total_value=comparison.total_value,
    )


class PortfolioSummary(BaseModel):
    """CMP-09: portfolio with policy and band status of the latest snapshot."""

    id: int
    name: str
    currency: str
    policy_id: int
    policy_name: str
    # PTF-07: the semaphore of the active version of the policy and the verdict's reason
    policy_semaphore: str | None
    policy_semaphore_reason: str | None
    archived_at: datetime | None
    latest_snapshot: SnapshotOut | None


class PositionSettingsOut(BaseModel):
    """PTF-03: per position of the active version, the latest snapshot or with settings."""

    ticker: str
    name: str
    type: str
    broker: str | None
    whole_units: bool | None  # with the default applied; null for the cash buffer


class PortfolioOut(PortfolioSummary):
    """PTF-05."""

    default_contribution: PlainDecimal
    precise_amounts: bool
    currency_locked: bool  # the portfolio has snapshots (PTF-03)
    active_version_label: str | None
    brokers: dict[str, str]
    positions: list[PositionSettingsOut]
    assignments: list[AssignmentOut]


class ValueIn(BaseModel):
    """CMP-01: units and the price or the value; the cash buffer has only a value."""

    ticker: str
    units: PlainDecimal | None = None
    price: PlainDecimal | None = None
    value: PlainDecimal | None = None
    name: str | None = None
    type: str | None = None


class NewSnapshot(BaseModel):
    values: list[ValueIn]
    corrects_snapshot_id: int | None = None


class PrefillRowOut(BaseModel):
    ticker: str
    name: str
    type: str
    units: PlainDecimal | None  # null: unknown, to be entered
    price: PlainDecimal | None  # the auto price, or the price last entered; null: none yet
    value: PlainDecimal  # of the previous snapshot
    in_policy: bool
    price_kind: str | None  # the price source: auto | manual | unresolved; null: none yet
    auto: AutoPriceOut | None  # the current auto price (CMP-01)
    # Why an auto source has no price: no_price, no_rate; unavailable: listing retired
    notice: str | None
    listing_symbol: str | None  # the source's listing, also a retired one (PRC-09)


# --- Timeline -----------------------------------------------------------------


class EventOut(BaseModel):
    id: int
    occurred_at: datetime
    type: str
    summary: str  # English; the UI writes it from `params` in its language (NFR-10)
    params: dict[str, Any] | None  # null for events from before the params were stored
    portfolio_id: int | None
    policy_version_id: int | None
    rebalance_id: int | None
    review_id: int | None

    @classmethod
    def of(cls, e: TimelineEvent) -> EventOut:
        return cls(
            id=e.id,
            occurred_at=e.occurred_at,
            type=e.type,
            summary=e.summary,
            params=e.params,
            portfolio_id=e.portfolio_id,
            policy_version_id=e.policy_version_id,
            rebalance_id=e.rebalance_id,
            review_id=e.review_id,
        )


# --- Imports ------------------------------------------------------------------


class ThesisImportPreview(BaseModel):
    """IMP-01: a new policy, or the draft (version) of the selected one."""

    creates_new_policy: bool
    version_no: int
    title: str


class CurrentStructurePreviewOut(BaseModel):
    values: list[tuple[str, PlainDecimal | None]]  # value, if the file gives one
    new_tickers: list[str]
