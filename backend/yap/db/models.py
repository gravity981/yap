"""ORM models for the data model in spec section 4.1."""

from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from yap.db.types import DecimalText, UTCDateTime


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        Decimal: DecimalText(),
        datetime: UTCDateTime(),
    }


class Investor(Base):
    """An account with the admin role, the investor role or both (USR-05, USR-09)."""

    __tablename__ = "investor"
    __table_args__ = (
        CheckConstraint("is_admin OR is_investor", name="ck_investor_has_role"),
        CheckConstraint(
            "NOT is_investor OR base_currency IS NOT NULL", name="ck_investor_base_currency"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_investor: Mapped[bool] = mapped_column(Boolean, default=False)
    base_currency: Mapped[str | None] = mapped_column(String(3))  # null without investor role
    # The investor's choice (USR-08); null until chosen and without the investor role
    ai_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("ai_reviewer.id"))
    # USR-08: the default review method is manual instead of an AI reviewer
    manual_review_default: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str | None] = mapped_column(String(5))  # en | de; null = browser's (USR-10)
    time_zone: Mapped[str | None] = mapped_column(String(64))  # IANA; null = browser's (USR-11)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]  # deleted = deactivated + anonymised (USR-02)


class AiReviewer(Base):
    """An LLM that runs reviews, with its API key and monthly limit per investor (REV-13
    to REV-15). Archived instead of deleted, so past reviews and runs keep it."""

    __tablename__ = "ai_reviewer"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))  # unique among the not archived ones
    description: Mapped[str | None] = mapped_column(Text)  # shown to investors
    provider: Mapped[str] = mapped_column(String(20))  # anthropic | openai | google
    model: Mapped[str] = mapped_column(String(100))
    api_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    api_key_last4: Mapped[str] = mapped_column(String(4))
    monthly_review_limit: Mapped[int] = mapped_column(Integer)  # per investor, 0 = none
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class PriceProvider(Base):
    """A price provider configured by the admin, or the built-in exchange rate source
    (PRC-01, PRC-11). Archived instead of deleted."""

    __tablename__ = "price_provider"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))  # unique among the not archived ones
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    daily_call_limit: Mapped[int | None] = mapped_column(Integer)  # None: no limit
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ProviderUsage(Base):
    """Calls to a provider per calendar day in UTC, lookups and updates together (PRC-08)."""

    __tablename__ = "provider_usage"

    provider_id: Mapped[int] = mapped_column(ForeignKey("price_provider.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD, UTC
    calls: Mapped[int] = mapped_column(Integer, default=0)
    quota_exhausted: Mapped[bool] = mapped_column(Boolean, default=False)


class Listing(Base):
    """One asset as one provider offers it; shared by the whole server, public data only.
    Keeps only the latest price (PRC-07)."""

    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("provider_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("price_provider.id"))
    symbol: Mapped[str] = mapped_column(String(64))
    exchange: Mapped[str] = mapped_column(String(100))
    quote_currency: Mapped[str] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(200))
    available: Mapped[bool] = mapped_column(Boolean, default=True)  # PRC-09
    not_found_count: Mapped[int] = mapped_column(Integer, default=0)  # consecutive updates
    price: Mapped[Decimal | None]  # quote currency; None until the first update
    price_date: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD, the provider's
    price_updated_at: Mapped[datetime | None]

    provider: Mapped[PriceProvider] = relationship()


class TickerLookup(Base):
    """The cached answer of one provider for one ticker, shared by all investors (PRC-03)."""

    __tablename__ = "ticker_lookup"
    __table_args__ = (UniqueConstraint("provider_id", "ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("price_provider.id"))
    ticker: Mapped[str] = mapped_column(String(32))  # uppercase
    result: Mapped[str] = mapped_column(String(10))  # found | not_found
    looked_up_at: Mapped[datetime]

    listings: Mapped[list[Listing]] = relationship(secondary="ticker_lookup_listing")


class TickerLookupListing(Base):
    __tablename__ = "ticker_lookup_listing"

    ticker_lookup_id: Mapped[int] = mapped_column(
        ForeignKey("ticker_lookup.id", ondelete="CASCADE"), primary_key=True
    )
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id"), primary_key=True)


class PriceSource(Base):
    """Where an investor's prices of an asset come from (PRC-05): a listing (auto),
    entered by hand (manual), or not resolved yet because the lookup failed (unresolved)."""

    __tablename__ = "price_source"

    investor_id: Mapped[int] = mapped_column(ForeignKey("investor.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # auto | manual | unresolved
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listing.id"))
    updated_at: Mapped[datetime]

    asset: Mapped[Asset] = relationship()
    listing: Mapped[Listing | None] = relationship()


class FxRate(Base):
    """The latest exchange rate of a currency pair from the built-in source (PRC-11)."""

    __tablename__ = "fx_rate"

    base: Mapped[str] = mapped_column(String(3), primary_key=True)
    quote: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[Decimal]  # 1 base = rate quote
    rate_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, the source's
    updated_at: Mapped[datetime]


class PriceUpdateSettings(Base):
    """When the price update runs (PRC-07): a single row. The time of day is local to the
    stored time zone, so it stays the same local time across daylight saving changes."""

    __tablename__ = "price_update_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    time_of_day: Mapped[str] = mapped_column(String(5))  # HH:MM
    time_zone: Mapped[str] = mapped_column(String(64))  # IANA
    interval_hours: Mapped[int] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None]


class PriceUpdateRun(Base):
    __tablename__ = "price_update_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(10))  # schedule | cli
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    # Per provider: updated, skipped (limit), failed, not_found (PRC-10)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class LoginFailure(Base):
    """Failed login attempts per username, for the rate limit (NFR-02)."""

    __tablename__ = "login_failure"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), index=True)
    failed_at: Mapped[datetime]


class UserSession(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investor_id: Mapped[int] = mapped_column(ForeignKey("investor.id", ondelete="CASCADE"))
    created_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    expires_at: Mapped[datetime]


class Asset(Base):
    __tablename__ = "asset"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))


class Policy(Base):
    __tablename__ = "policy"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("investor.id"))
    name: Mapped[str] = mapped_column(String(100))
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime]

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy", order_by="PolicyVersion.version_no"
    )


class PolicyVersion(Base):
    __tablename__ = "policy_version"
    __table_args__ = (UniqueConstraint("policy_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policy.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    # The thesis of the version (THS-01); its semaphore comes from its review (THS-04)
    thesis_title: Mapped[str] = mapped_column(String(200))
    thesis_md: Mapped[str] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    # REV-20: not_reviewed | review_did_not_match, set at activation; null otherwise
    mark: Mapped[str | None] = mapped_column(String(30))
    activated_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]  # last auto-save of a draft (POL-14)
    created_at: Mapped[datetime]

    policy: Mapped[Policy] = relationship(back_populates="versions")
    reviews: Mapped[list[Review]] = relationship(viewonly=True, order_by="Review.id")
    positions: Mapped[list[PolicyPosition]] = relationship(
        back_populates="policy_version",
        order_by="PolicyPosition.sort_order",
        cascade="all, delete-orphan",
    )

    @property
    def label(self) -> str:
        return f"{self.policy.name}-v{self.version_no}"


class PolicyPosition(Base):
    __tablename__ = "policy_position"
    __table_args__ = (UniqueConstraint("policy_version_id", "asset_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_version_id: Mapped[int] = mapped_column(
        ForeignKey("policy_version.id", ondelete="CASCADE")
    )
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"))
    target_pct: Mapped[Decimal]
    buy_threshold_pct: Mapped[Decimal]
    sell_threshold_pct: Mapped[Decimal]
    exit: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale_md: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer)

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="positions")
    asset: Mapped[Asset] = relationship()


class Portfolio(Base):
    __tablename__ = "portfolio"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("investor.id"))
    policy_id: Mapped[int] = mapped_column(ForeignKey("policy.id"))  # current policy, NOT NULL
    name: Mapped[str] = mapped_column(String(100))
    # All amounts of the portfolio; fixed once it has snapshots (PTF-03)
    currency: Mapped[str] = mapped_column(String(3))
    default_contribution: Mapped[Decimal]
    precise_amounts: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime]

    policy: Mapped[Policy] = relationship()
    assignments: Mapped[list[PortfolioAssignment]] = relationship(
        order_by="PortfolioAssignment.valid_from"
    )
    positions: Mapped[list[PortfolioPosition]] = relationship(cascade="all, delete-orphan")


class PortfolioAssignment(Base):
    __tablename__ = "portfolio_assignment"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio.id"))
    policy_id: Mapped[int] = mapped_column(ForeignKey("policy.id"))
    valid_from: Mapped[datetime]

    policy: Mapped[Policy] = relationship()


class PortfolioPosition(Base):
    """Settings of a portfolio per asset (PTF-03): broker and whether it is traded in whole
    units only; null means the default by asset type."""

    __tablename__ = "portfolio_position"

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), primary_key=True)
    broker: Mapped[str | None] = mapped_column(String(100))
    whole_units: Mapped[bool | None] = mapped_column(Boolean)

    asset: Mapped[Asset] = relationship()


class Snapshot(Base):
    __tablename__ = "snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio.id"))
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    taken_at: Mapped[datetime]
    source: Mapped[str] = mapped_column(String(10))  # manual | import | rebalance
    corrects_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id"))

    portfolio: Mapped[Portfolio] = relationship(viewonly=True)
    policy_version: Mapped[PolicyVersion] = relationship()
    values: Mapped[list[SnapshotValue]] = relationship()


class SnapshotValue(Base):
    __tablename__ = "snapshot_value"

    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), primary_key=True)
    # How the value came about (CMP-10); all null for rows from before price tracking
    units: Mapped[Decimal | None]
    price: Mapped[Decimal | None]  # portfolio currency
    value: Mapped[Decimal]  # portfolio currency
    price_kind: Mapped[str | None] = mapped_column(String(10))  # auto | manual
    # For auto prices (CMP-10): where the price came from, frozen with the snapshot
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listing.id"))
    listing_price: Mapped[Decimal | None]  # in the listing's currency
    listing_currency: Mapped[str | None] = mapped_column(String(3))
    price_date: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD
    fx_rate: Mapped[Decimal | None]  # 1 if the same currency

    listing: Mapped[Listing | None] = relationship()

    asset: Mapped[Asset] = relationship()


class Rebalance(Base):
    __tablename__ = "rebalance"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio.id"))
    input_snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshot.id"))
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    contribution: Mapped[Decimal]
    withdrawal: Mapped[Decimal]
    precise_amounts: Mapped[bool] = mapped_column(Boolean)
    result_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id"))
    confirmed_at: Mapped[datetime]


class RebalanceAction(Base):
    __tablename__ = "rebalance_action"

    id: Mapped[int] = mapped_column(primary_key=True)
    rebalance_id: Mapped[int] = mapped_column(ForeignKey("rebalance.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"))
    phase: Mapped[str] = mapped_column(String(2))  # 1A | 1B | 3
    action: Mapped[str] = mapped_column(String(30))
    broker: Mapped[str | None] = mapped_column(String(100))
    # Copied at confirmation, like the broker; null for positions without units (RB-24)
    whole_units: Mapped[bool | None] = mapped_column(Boolean)
    calculated_units: Mapped[Decimal | None]
    executed_units: Mapped[Decimal | None]
    calculated_amount: Mapped[Decimal]
    executed_amount: Mapped[Decimal]


class Review(Base):
    """A review of a version (REV-01 to REV-12): of the whole policy, or from before stage 2
    of its thesis or its target structure. It is confirmed, and immutable from then on,
    when its draft is activated (REV-11)."""

    __tablename__ = "review"
    __table_args__ = (UniqueConstraint("policy_version_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # full; thesis | policy before stage 2
    # The reviewed version; at most one review of each kind (REV-09)
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    started_by: Mapped[int] = mapped_column(ForeignKey("investor.id"))
    state: Mapped[str] = mapped_column(String(10))  # queued | running | done | failed
    news_from: Mapped[datetime | None]  # null for policy reviews before stage 2
    news_to: Mapped[datetime | None]
    # REV-03: good | warning | broken; before scoring version 3 intact | needs_adaptation |
    # broken (REV-06); null for policy reviews before stage 2
    verdict: Mapped[str | None] = mapped_column(String(20))
    verdict_reason: Mapped[str | None] = mapped_column(Text)  # since scoring version 3
    # REV-09: of the reviewed content; null for reviews from before fingerprints
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    # REV-11, REV-23: when confirmed by activation; null while the draft is open
    saved_at: Mapped[datetime | None]
    # Investor changes of reviews from before REV-10 was dropped, read-only (JSON: note,
    # verdict, scores per aspect); null for all newer reviews
    legacy_modification: Mapped[str | None] = mapped_column(Text)
    scoring_version: Mapped[str] = mapped_column(String(20))  # REV-06
    method: Mapped[str] = mapped_column(String(10), default="ai")  # ai | manual (REV-18)
    prompt_id: Mapped[str | None] = mapped_column(String(60))  # REV-19; null before it
    # REV-17: the AI reviewer it runs on, its name at the start, provider and model; a
    # manual review has the provider "manual" and no model (before stage 2: the model the
    # investor named)
    ai_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("ai_reviewer.id"))
    ai_reviewer_name: Mapped[str | None] = mapped_column(String(100))  # null before 0007
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]

    aspects: Mapped[list[ReviewAspect]] = relationship(
        order_by="ReviewAspect.aspect", cascade="all, delete-orphan"
    )
    sources: Mapped[list[ReviewSource]] = relationship(
        order_by="ReviewSource.id", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list[ReviewSuggestion]] = relationship(
        order_by="ReviewSuggestion.id", cascade="all, delete-orphan"
    )


class ReviewAspect(Base):
    """Score of one aspect, as half points (0 to 20) (REV-02)."""

    __tablename__ = "review_aspect"

    review_id: Mapped[int] = mapped_column(
        ForeignKey("review.id", ondelete="CASCADE"), primary_key=True
    )
    aspect: Mapped[str] = mapped_column(String(5), primary_key=True)  # T1-T6 | P1-P6
    half_points: Mapped[int] = mapped_column(Integer)
    reasoning_md: Mapped[str] = mapped_column(Text)


class ReviewSource(Base):
    __tablename__ = "review_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("review.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    published_on: Mapped[str | None] = mapped_column(String(10))  # ISO date as reported
    url: Mapped[str] = mapped_column(String(2000))


class ReviewSuggestion(Base):
    __tablename__ = "review_suggestion"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("review.id", ondelete="CASCADE"))
    """A suggestion or proposal of a review (REV-07, REV-22). Its state may change only
    while its review belongs to an open draft (REV-11)."""

    # thesis_section | position_change | position_add | position_remove | proposal;
    # before scoring version 3 also thesis_text, thesis_status, policy_position (no change)
    kind: Mapped[str] = mapped_column(String(20))
    content_md: Mapped[str] = mapped_column(Text)  # the reason, or a proposal's description
    # What Take over applies (domain/suggestions.py); null for older suggestions
    change: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # What Take over replaced, so it can be undone
    previous: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="open")  # | taken_over | dismissed


class ReviewRun(Base):
    """One row per started review run; counts towards the monthly limit (REV-16)."""

    __tablename__ = "review_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    investor_id: Mapped[int] = mapped_column(ForeignKey("investor.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    # The limit counts per AI reviewer (REV-16); null for runs of plans not migrated in 0007
    ai_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("ai_reviewer.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime]


class TimelineEvent(Base):
    __tablename__ = "timeline_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    investor_id: Mapped[int] = mapped_column(ForeignKey("investor.id"))
    occurred_at: Mapped[datetime]
    type: Mapped[str] = mapped_column(String(30))
    portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio.id"))
    policy_version_id: Mapped[int | None] = mapped_column(ForeignKey("policy_version.id"))
    rebalance_id: Mapped[int | None] = mapped_column(ForeignKey("rebalance.id"))
    review_id: Mapped[int | None] = mapped_column(ForeignKey("review.id"))
    summary: Mapped[str] = mapped_column(String(500))  # English, as stored at the time
    # The values of the summary, so the UI can write it in its language (TL-02, NFR-10);
    # null for events from before 0010
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
