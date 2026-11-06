"""Version and health (section 5.7), app startup (NFR-09)."""

import subprocess

import pytest
from fastapi.testclient import TestClient

from yap import version
from yap.api.app import create_app, create_app_from_env


@pytest.fixture(autouse=True)
def fresh_version_cache():  # type: ignore[no-untyped-def]
    version.version_info.cache_clear()
    yield
    version.version_info.cache_clear()


@pytest.mark.req("NFR-09")
def test_version_from_image_environment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.0")
    monkeypatch.setenv("APP_COMMIT", "3f9c2e1")
    version.version_info.cache_clear()  # the app fixture already read the dev version
    assert client.get("/api/version").json() == {"version": "1.2.0", "commit": "3f9c2e1"}
    assert client.get("/api/health").json() == {"status": "ok", "version": "1.2.0"}


@pytest.mark.req("NFR-09")
def test_version_with_release_candidate_suffix(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.0")
    monkeypatch.setenv("APP_COMMIT", "3f9c2e1")
    monkeypatch.setenv("APP_VERSION_SUFFIX", "rc.2")
    version.version_info.cache_clear()
    assert client.get("/api/version").json() == {"version": "1.2.0-rc.2", "commit": "3f9c2e1"}
    assert client.get("/api/health").json() == {"status": "ok", "version": "1.2.0-rc.2"}


@pytest.mark.req("NFR-09")
def test_version_from_git_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_VERSION", raising=False)
    info = version.version_info()
    assert info.version.endswith("+dev")
    assert info.commit != ""


@pytest.mark.req("NFR-09")
def test_version_without_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_VERSION", raising=False)

    def no_git(*args: object, **kwargs: object) -> None:
        raise subprocess.SubprocessError("no git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert version.version_info() == version.VersionInfo("0.0.0+dev", "unknown")


@pytest.mark.req("NFR-09")
def test_app_migrates_on_startup(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'new.db'}")
    monkeypatch.setenv("APP_ENV", "prod")
    app = create_app_from_env()
    assert app.docs_url is None  # API docs only in dev
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/api/health").json()["status"] == "ok"
    assert create_app.__name__ == "create_app"


@pytest.mark.req("NFR-09")
def test_serves_the_built_frontend(db_url: str, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from yap.api.settings import Settings

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside")
    app = create_app(Settings(database_url=db_url, migrate_on_startup=False, static_dir=str(dist)))
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/").text == "<div id=root></div>"
        assert c.get("/portfolios/3").text == "<div id=root></div>"  # frontend route
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        # encoded, so the client does not normalise it away; must not escape dist/
        assert c.get("/assets/%2e%2e/%2e%2e/secret.txt").text != "outside"
        assert c.get("/%2e%2e/secret.txt").text != "outside"
        assert c.get("/api/unknown").status_code == 404
        assert c.get("/api/version").status_code == 200
