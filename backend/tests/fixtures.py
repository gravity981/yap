"""Database, clock and factory fixtures (test strategy §8)."""

import json
import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from yap.db.engine import make_engine, make_session_factory
from yap.db.migrate import upgrade
from yap.db.models import (
    AiReviewer,
    Investor,
    Policy,
    PolicyVersion,
    Portfolio,
    Review,
    ReviewAspect,
)
from yap.domain.reviews import SCORING_VERSION
from yap.llm import LlmConfig, LlmError
from yap.llm.base import LlmRequest
from yap.messages import msg
from yap.services import policies, portfolios
from yap.services.policies import PositionSpec
from yap.services.secrets import KeyBox

START = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


@dataclass
class FakeClock:
    current: datetime = START

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> datetime:
        self.current += timedelta(**kwargs)
        return self.current


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("db") / "template.db"
    upgrade(f"sqlite:///{path}")
    return path


@pytest.fixture
def db_url(migrated_template: Path, tmp_path: Path) -> str:
    path = tmp_path / "test.db"
    shutil.copy(migrated_template, path)
    return f"sqlite:///{path}"


@pytest.fixture
def session(db_url: str) -> Iterator[Session]:
    engine = make_engine(db_url)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@dataclass
class Factory:
    session: Session
    clock: FakeClock
    _counter: int = field(default=0)

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def investor(
        self, name: str | None = None, *, admin: bool = False, investor: bool = True
    ) -> Investor:
        account = Investor(
            username=name or f"investor{self._next()}",
            password_hash="x",
            is_admin=admin,
            is_investor=investor,
            base_currency="CHF" if investor else None,
            active=True,
            created_at=self.clock.now(),
        )
        self.session.add(account)
        self.session.flush()
        return account

    def admin(self) -> Investor:
        return self.investor(f"admin{self._next()}", admin=True, investor=False)

    def policy_draft(
        self,
        owner: Investor,
        *,
        name: str | None = None,
        thesis_title: str = "Core thesis",
        thesis_md: str = "# Thesis",
        positions: list[PositionSpec] | None = None,
    ) -> Policy:
        """A policy with only its draft v1: the thesis and, if given, positions (POL-01)."""
        policy = policies.create_policy(
            self.session,
            owner,
            self.clock,
            name=name or f"policy{self._next()}",
            thesis_title=thesis_title,
            thesis_md=thesis_md,
        )
        if positions is not None:
            policies.update_draft(self.session, owner, self.clock, policy.id, positions=positions)
        return policy

    def ai_reviewer(
        self,
        name: str = "Standard",
        *,
        provider: str = "openai",
        model: str = "gpt-x",
        limit: int = 10,
        enabled: bool = True,
        api_key: str = "sk-test",
    ) -> AiReviewer:
        """An AI reviewer with a key encrypted with TEST_SECRET (REV-13, REV-15)."""
        reviewer = AiReviewer(
            name=name,
            provider=provider,
            model=model,
            api_key_encrypted=KeyBox(TEST_SECRET).encrypt(api_key),
            api_key_last4=api_key[-4:],
            monthly_review_limit=limit,
            enabled=enabled,
            created_at=self.clock.now(),
            updated_at=self.clock.now(),
        )
        self.session.add(reviewer)
        self.session.flush()
        return reviewer

    def review(
        self,
        owner: Investor,
        draft: PolicyVersion,
        *,
        kind: str = "full",
        half_points: tuple[int, ...] = (14, 12, 16, 10, 14, 13),
        verdict: str | None = "good",
        scoring_version: str = SCORING_VERSION,
    ) -> Review:
        """A finished review of a version, stored directly (no provider): of the whole
        policy (T1-T6, and P1-P6 if `half_points` has twelve scores), or one from before
        stage 2 of kind `thesis` or `policy`."""
        if kind == "policy":
            codes = [f"P{i}" for i in range(1, 7)]
        else:
            codes = [f"T{i}" for i in range(1, 7)] + [f"P{i}" for i in range(1, 7)]
            codes = codes[: len(half_points)]
        review = Review(
            kind=kind,
            policy_version_id=draft.id,
            started_by=owner.id,
            state="done",
            verdict=verdict if kind != "policy" else None,
            scoring_version=scoring_version,
            provider="anthropic",
            model="claude-x",
            started_at=self.clock.now(),
            completed_at=self.clock.now(),
            aspects=[
                ReviewAspect(aspect=code, half_points=half, reasoning_md=f"About {code}")
                for code, half in zip(codes, half_points, strict=True)
            ],
        )
        self.session.add(review)
        self.session.flush()
        return review

    def active_policy(
        self,
        owner: Investor,
        positions: list[PositionSpec] | None = None,
        *,
        name: str | None = None,
        thesis_title: str = "Core thesis",
        verdict: str | None = None,
    ) -> Policy:
        """A policy whose v1 is active, with the given (or the default) positions; with a
        verdict, v1 was activated with a review that gives it this semaphore (THS-04)."""
        policy = self.policy_draft(owner, name=name, thesis_title=thesis_title)
        policies.update_draft(
            self.session,
            owner,
            self.clock,
            policy.id,
            positions=positions if positions is not None else default_positions(),
            thesis=policies.ThesisSpec(thesis_title, "# Thesis"),
        )
        if verdict is not None:
            draft = policies.get_draft(policy)
            assert draft is not None
            self.review(owner, draft, verdict=verdict)
        policies.activate_draft(self.session, owner, self.clock, policy.id, None)
        self.session.refresh(policy)
        return policy

    def portfolio(
        self, owner: Investor, policy: Policy | None = None, **kwargs: object
    ) -> Portfolio:
        policy = policy or self.active_policy(owner)
        return portfolios.create_portfolio(
            self.session,
            owner,
            self.clock,
            name=str(kwargs.pop("name", f"portfolio{self._next()}")),
            policy_id=policy.id,
            **kwargs,  # type: ignore[arg-type]
        )


def spec(
    ticker: str,
    target: int | str,
    buy: int = -20,
    sell: int = 20,
    *,
    type: str = "ETF",
    exit: bool = False,
) -> PositionSpec:
    return PositionSpec(
        ticker=ticker,
        name=f"{ticker} name",
        type=type,
        target_pct=Decimal(target),
        buy_threshold_pct=Decimal(buy),
        sell_threshold_pct=Decimal(sell),
        exit=exit,
    )


def default_positions() -> list[PositionSpec]:
    return [spec("AAA", 60), spec("BBB", 40)]


@pytest.fixture
def factory(session: Session, clock: FakeClock) -> Factory:
    return Factory(session, clock)


# --- API ----------------------------------------------------------------------

PASSWORD = "correct horse battery"


@pytest.fixture
def app(db_url: str, clock: FakeClock, fake_llm: FakeLlm):  # type: ignore[no-untyped-def]
    from yap.api.app import create_app
    from yap.api.settings import Settings
    from yap.prices.fake import fake_adapter

    settings = Settings(database_url=db_url, migrate_on_startup=False, secret_key=TEST_SECRET)
    # No test calls a price provider either (test strategy §6)
    return create_app(settings, clock, adapters=fake_llm, price_adapters=fake_adapter)


TEST_SECRET = "test secret for API keys"


@dataclass
class FakeLlm:
    """Stands in for the provider adapters (test strategy §6): records the configs and
    requests it got, answers with `answers` (in turn) and fails with `error` if set, or
    raises `crash` like an error no adapter expected."""

    configs: list[LlmConfig] = field(default_factory=list)
    requests: list[LlmRequest] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    error: str | None = None
    crash: Exception | None = None

    def __call__(self, config: LlmConfig) -> FakeLlm:
        self.configs.append(config)
        return self

    def _fail(self) -> None:
        if self.crash:
            raise self.crash
        if self.error:
            raise LlmError(msg("provider_error", detail=self.error))

    def check(self) -> None:
        self._fail()

    def generate(self, request: LlmRequest) -> str:
        self.requests.append(request)
        self._fail()
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return with_prompt_id(answer, request)


def with_prompt_id(answer: str, request: LlmRequest) -> str:
    """Like a real AI, the fake repeats the prompt ID of the request (REV-19), unless the
    answer gives one or is no JSON object."""
    try:
        data = json.loads(answer)
    except json.JSONDecodeError:
        return answer
    if not isinstance(data, dict) or "prompt_id" in data:
        return answer
    prompt_id = request.json_schema["properties"]["prompt_id"]["enum"][0]
    return json.dumps({"prompt_id": prompt_id, **data})


@pytest.fixture
def fake_llm() -> FakeLlm:
    return FakeLlm()


@pytest.fixture
def client(app):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    # https: the session cookie is Secure and is only sent over https
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@dataclass
class Accounts:
    """Creates accounts directly in the database and logs them in through the API."""

    session: Session
    clock: FakeClock
    app: object

    def create(
        self,
        username: str,
        *,
        admin: bool = False,
        investor: bool = True,
        password: str = PASSWORD,
        must_change_password: bool = False,
    ) -> Investor:
        from yap.services import accounts

        account = accounts.create_account(
            self.session,
            self.clock,
            username=username,
            password=password,
            admin=admin,
            investor=investor,
            base_currency="CHF" if investor else None,
            must_change_password=must_change_password,
        )
        self.session.commit()
        return account

    def client(self, username: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
        """A separate logged-in client, so several users can act in one test."""
        from fastapi.testclient import TestClient

        c = TestClient(self.app, base_url="https://testserver")  # type: ignore[arg-type]
        response = c.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return c


@pytest.fixture
def accounts_api(session: Session, clock: FakeClock, app) -> Accounts:  # type: ignore[no-untyped-def]
    return Accounts(session, clock, app)
