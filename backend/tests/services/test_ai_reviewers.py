"""AI reviewers: configuration by the admin, choice by the investor (REV-13 to REV-15,
USR-08)."""

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory, FakeLlm
from yap.services import ai_reviewers
from yap.services.ai_reviewers import ReviewerSpec
from yap.services.common import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from yap.services.secrets import KeyBox

KEYS = KeyBox(TEST_SECRET)
SPEC = ReviewerSpec(
    name="Deep",
    provider="anthropic",
    model="claude-x",
    monthly_review_limit=5,
    description="Thorough, slower",
    api_key="sk-ant-secret-1234",
)


@pytest.mark.req("REV-13", "REV-15")
def test_admin_creates_any_number_of_reviewers_with_encrypted_keys(
    session: Session, factory: Factory
) -> None:
    admin = factory.admin()
    deep = ai_reviewers.create_reviewer(session, admin, factory.clock, KEYS, SPEC)
    quick = ai_reviewers.create_reviewer(
        session, admin, factory.clock, KEYS, ReviewerSpec("Quick", "openai", "gpt-x", 20, None, "k")
    )
    assert [r.name for r in ai_reviewers.list_reviewers(session, admin)] == ["Deep", "Quick"]
    assert (deep.description, deep.api_key_last4, quick.description) == (
        "Thorough, slower",
        "1234",
        None,
    )
    assert b"sk-ant-secret" not in deep.api_key_encrypted
    assert ai_reviewers.llm_config(deep, KEYS).api_key == "sk-ant-secret-1234"


@pytest.mark.req("REV-13", "REV-14")
@pytest.mark.parametrize(
    ("change", "path"),
    [
        ({"name": " "}, "name"),
        ({"name": "Deep"}, "name"),  # taken
        ({"provider": "mistral"}, "provider"),
        ({"model": ""}, "model"),
        ({"monthly_review_limit": -1}, "monthly_review_limit"),
        ({"api_key": None}, "api_key"),  # a new reviewer needs a key
    ],
)
def test_invalid_reviewers_are_refused(
    session: Session, factory: Factory, change: dict[str, object], path: str
) -> None:
    admin = factory.admin()
    ai_reviewers.create_reviewer(session, admin, factory.clock, KEYS, SPEC)
    spec = ReviewerSpec(**{**SPEC.__dict__, "name": "Other", **change})  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as error:
        ai_reviewers.create_reviewer(session, admin, factory.clock, KEYS, spec)
    assert error.value.problems[0][0] == path


@pytest.mark.req("REV-15")
def test_keys_need_the_server_secret(session: Session, factory: Factory) -> None:
    with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
        ai_reviewers.create_reviewer(session, factory.admin(), factory.clock, KeyBox(None), SPEC)


@pytest.mark.req("REV-14", "REV-15")
def test_updates_keep_the_key_unless_a_new_one_is_given(session: Session, factory: Factory) -> None:
    admin = factory.admin()
    reviewer = ai_reviewers.create_reviewer(session, admin, factory.clock, KEYS, SPEC)
    factory.clock.advance(days=1)
    changed = ReviewerSpec(**{**SPEC.__dict__, "model": "claude-y", "api_key": None})
    ai_reviewers.update_reviewer(session, admin, factory.clock, KEYS, reviewer.id, changed)
    assert (reviewer.model, reviewer.api_key_last4) == ("claude-y", "1234")
    assert reviewer.updated_at > reviewer.created_at
    renewed = ReviewerSpec(**{**SPEC.__dict__, "api_key": "sk-new-9999"})
    ai_reviewers.update_reviewer(session, admin, factory.clock, KEYS, reviewer.id, renewed)
    assert ai_reviewers.llm_config(reviewer, KEYS).api_key == "sk-new-9999"


@pytest.mark.req("REV-13", "USR-08")
def test_archived_reviewers_disappear_and_free_their_name(
    session: Session, factory: Factory
) -> None:
    admin, investor = factory.admin(), factory.investor()
    reviewer = ai_reviewers.create_reviewer(session, admin, factory.clock, KEYS, SPEC)
    ai_reviewers.choose_reviewer(session, investor, reviewer.id)
    ai_reviewers.archive_reviewer(session, admin, factory.clock, reviewer.id)
    assert ai_reviewers.list_reviewers(session, admin) == []
    assert ai_reviewers.available_reviewers(session, investor) == []
    with pytest.raises(NotFoundError):
        ai_reviewers.update_reviewer(session, admin, factory.clock, KEYS, reviewer.id, SPEC)
    with pytest.raises(NotFoundError):
        ai_reviewers.choose_reviewer(session, investor, reviewer.id)
    # The row stays for past reviews and runs; the name can be used again
    assert reviewer.archived_at is not None
    ai_reviewers.create_reviewer(session, admin, factory.clock, KEYS, SPEC)


@pytest.mark.req("USR-08", "REV-13")
def test_investors_choose_among_the_enabled_reviewers(session: Session, factory: Factory) -> None:
    investor = factory.investor()
    deep = factory.ai_reviewer("Deep")
    off = factory.ai_reviewer("Off", enabled=False)
    assert [r.name for r in ai_reviewers.available_reviewers(session, investor)] == ["Deep"]
    ai_reviewers.choose_reviewer(session, investor, deep.id)
    assert investor.ai_reviewer_id == deep.id
    with pytest.raises(ConflictError, match="disabled"):
        ai_reviewers.choose_reviewer(session, investor, off.id)
    ai_reviewers.choose_reviewer(session, investor, None)
    assert investor.ai_reviewer_id is None


@pytest.mark.req("USR-05", "USR-08")
def test_only_admins_configure_and_only_investors_choose(
    session: Session, factory: Factory
) -> None:
    admin, investor = factory.admin(), factory.investor()
    reviewer = factory.ai_reviewer()
    with pytest.raises(ForbiddenError):
        ai_reviewers.list_reviewers(session, investor)
    with pytest.raises(ForbiddenError):
        ai_reviewers.create_reviewer(session, investor, factory.clock, KEYS, SPEC)
    with pytest.raises(ForbiddenError):
        ai_reviewers.choose_reviewer(session, admin, reviewer.id)


@pytest.mark.req("REV-14")
def test_connection_test_reports_the_providers_answer(session: Session, factory: Factory) -> None:
    admin = factory.admin()
    reviewer = factory.ai_reviewer(provider="google", model="gemini-x")
    fake = FakeLlm()
    result = ai_reviewers.test_connection(session, admin, KEYS, fake, reviewer.id)
    assert (result.ok, str(result.message)) == (True, "Connected to google, model gemini-x")
    assert fake.configs[-1].api_key == "sk-test"
    fake.error = "Google rejected the API key"
    result = ai_reviewers.test_connection(session, admin, KEYS, fake, reviewer.id)
    assert (result.ok, str(result.message)) == (False, "Google rejected the API key")
    other_secret = KeyBox("another secret")
    result = ai_reviewers.test_connection(session, admin, other_secret, fake, reviewer.id)
    assert not result.ok and "cannot be decrypted" in str(result.message)
    fake.error = None
    fake.crash = RuntimeError("unexpected answer")
    result = ai_reviewers.test_connection(session, admin, KEYS, fake, reviewer.id)
    assert (result.ok, str(result.message)) == (
        False,
        "The test failed unexpectedly (RuntimeError: unexpected answer)",
    )
