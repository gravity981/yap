"""Settings from the environment (spec 2.6)."""

from pathlib import Path

import pytest

from yap.api.settings import Settings


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    for name in ("APP_SECRET_KEY", "APP_SECRET_KEY_FILE", "COOKIE_SECURE", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.req("REV-15", "NFR-09")
def test_secret_key_from_a_compose_secret_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "app_secret_key"
    secret.write_text("from the file\n")
    monkeypatch.setenv("APP_SECRET_KEY", "from the environment")
    assert Settings.from_env().secret_key == "from the environment"
    monkeypatch.setenv("APP_SECRET_KEY_FILE", str(secret))
    assert Settings.from_env().secret_key == "from the file"  # the file wins, trimmed


@pytest.mark.req("NFR-02")
def test_cookies_are_secure_unless_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings.from_env().cookie_secure is True
    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert Settings.from_env().cookie_secure is False
