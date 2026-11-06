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
    Snapshot,
    SnapshotValue,
    ThesisRevision,
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


# --- Theses -------------------------------------------------------------------


class NewThesis(BaseModel):
    title: str
    content_md: str
    visibility: str = "private"
    status: str = "intact"


class ThesisDraftIn(BaseModel):
    title: str
    content_md: str
    status: str
    change_note: str | None = None  # may be given now or at activation (THS-03)


class VisibilityIn(BaseModel):
    visibility: str


class ReviewBrief(BaseModel):
    """The review of a revision or version, in short (THS-08, REV-11)."""

    id: int
    state: str
    total: float | None
    verdict: str | None
    modified: bool
    outdated: bool

    @classmethod
    def of(cls, draft: ThesisRevision | PolicyVersion) -> ReviewBrief | None:
        from yap.services import reviews

        review = draft.review
        if review is None:
            return None
        totals = reviews.totals(review)
        return cls(
            id=review.id,
            state=review.state,
            total=totals.effective / 2 if totals else None,
            verdict=reviews.effective_verdict(review),
            modified=review.modified,
            outdated=reviews.outdated(review, draft),
        )


class RevisionSummary(BaseModel):
    id: int
    revision_no: int
    title: str
    status: str
    change_note: str | None
    is_draft: bool
    activated_at: datetime | None
    created_at: datetime
    review: ReviewBrief | None


class RevisionOut(RevisionSummary):
    thesis_id: int
    content_md: str


class ThesisSummary(BaseModel):
    id: int
    is_own: bool
    visibility: str
    latest: RevisionSummary  # for the owner this can be the draft
    has_draft: bool
    active_revision_no: int | None  # latest activated revision; policies can only use these


class ThesisOut(BaseModel):
    """THS-08: revisions in chronological order (reviews follow with stage 4)."""

    id: int
    is_own: bool
    visibility: str
    created_at: datetime
    revisions: list[RevisionSummary]


class RevisionDiff(BaseModel):
    from_revision_no: int
    to_revision_no: int
    unified_diff: str


# --- Policies -----------------------------------------------------------------


class NewPolicy(BaseModel):
    name: str
    thesis_id: int


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


class DraftThesisRevision(BaseModel):
    thesis_revision_id: int


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
    thesis_revision_id: int
    thesis_revision_no: int
    thesis_status: str
    change_note: str | None
    active_from: datetime | None
    active_until: datetime | None
    is_draft: bool
    review: ReviewBrief | None


class VersionOut(VersionSummary):
    positions: list[PositionOut]

    @classmethod
    def of(
        cls, version: PolicyVersion, active_from: datetime | None, active_until: datetime | None
    ) -> VersionOut:
        return cls(
            **version_summary(version, active_from, active_until).model_dump(),
            positions=[PositionOut.of(p) for p in version.positions],
        )


def version_summary(
    version: PolicyVersion, active_from: datetime | None, active_until: datetime | None
) -> VersionSummary:
    return VersionSummary(
        id=version.id,
        version_no=version.version_no,
        label=version.label,
        thesis_revision_id=version.thesis_revision_id,
        thesis_revision_no=version.thesis_revision.revision_no,
        thesis_status=version.thesis_revision.status,
        change_note=version.change_note,
        active_from=active_from,
        active_until=active_until,
        is_draft=version.activated_at is None,
        review=ReviewBrief.of(version),
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
    thesis_id: int
    archived_at: datetime | None
    created_at: datetime
    versions: list[VersionSummary]
    portfolios: list[PortfolioRef]
    newer_thesis_revision_id: int | None
    # POL-11: the active version pins a thesis revision that needs adaptation or is broken
    thesis_warning: bool
    thesis_status: str | None  # status of the revision pinned by the active version


class PolicySummary(BaseModel):
    id: int
    name: str
    archived_at: datetime | None
    active_version_label: str | None
    has_draft: bool
    newer_thesis_revision_id: int | None
    thesis_warning: bool
    thesis_status: str | None


class PositionChangeOut(BaseModel):
    ticker: str
    change: str
    fields: dict[str, tuple[str, str]]


class VersionDiffOut(BaseModel):
    positions: list[PositionChangeOut]
    thesis_revision: tuple[int, int] | None


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
    thesis_revision_id: int | None

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
            thesis_revision_id=e.thesis_revision_id,
        )


# --- Imports ------------------------------------------------------------------


class ThesisImportPreview(BaseModel):
    creates_new_thesis: bool
    revision_no: int
    title: str
    status: str
    visibility: str | None


class CurrentStructurePreviewOut(BaseModel):
    values: list[tuple[str, PlainDecimal | None]]  # value, if the file gives one
    new_tickers: list[str]
