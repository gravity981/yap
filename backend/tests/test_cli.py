"""Admin command line, backup and restore (NFR-08)."""

import io
import sqlite3
from pathlib import Path

import pytest

from tests.fixtures import PASSWORD
from yap import cli


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    return path


def usernames(path: Path) -> list[tuple[str, int, int, str | None, int]]:
    """username, is_admin, is_investor, base_currency, must_change_password"""
    with sqlite3.connect(path) as c:
        return c.execute(
            "SELECT username, is_admin, is_investor, base_currency, must_change_password"
            " FROM investor ORDER BY id"
        ).fetchall()


@pytest.mark.req("NFR-09")
def test_migrate(db: Path) -> None:
    assert cli.main(["migrate"]) == 0
    assert db.exists()


@pytest.mark.req("USR-02")
def test_create_admin_and_investor(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["create-admin", "root", "--password-stdin"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["create-investor", "alice", "--currency", "CHF", "--password-stdin"]) == 0
    assert usernames(db) == [("root", 1, 0, None, 0), ("alice", 0, 1, "CHF", 1)]


@pytest.mark.req("USR-09")
def test_create_admin_who_is_also_an_investor(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    args = ["create-admin", "root", "--investor", "--currency", "chf", "--password-stdin"]
    assert cli.main(args) == 0
    assert usernames(db) == [("root", 1, 1, "CHF", 0)]


@pytest.mark.req("USR-09")
def test_create_admin_checks_the_investor_options(
    db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="only used with --investor"):
        cli.main(["create-admin", "root", "--currency", "CHF", "--password-stdin"])
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["create-admin", "root", "--investor", "--password-stdin"]) == 1
    assert "base currency" in capsys.readouterr().err


@pytest.mark.req("USR-02")
def test_create_reports_errors(
    db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert cli.main(["create-admin", "root", "--password-stdin"]) == 1
    assert "at least 12 characters" in capsys.readouterr().err


@pytest.mark.req("USR-02")
def test_password_prompt(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([PASSWORD, "different password"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    with pytest.raises(SystemExit, match="do not match"):
        cli.main(["create-admin", "root"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: PASSWORD)
    assert cli.main(["create-admin", "root"]) == 0


@pytest.mark.req("NFR-08")
def test_backup_and_restore(db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    cli.main(["create-admin", "root", "--password-stdin"])
    backup = tmp_path / "backups" / "app-1.db"
    assert cli.main(["backup", str(backup)]) == 0
    with pytest.raises(SystemExit, match="exists"):
        cli.main(["backup", str(backup)])

    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    cli.main(["create-investor", "alice", "--currency", "CHF", "--password-stdin"])
    assert len(usernames(db)) == 2
    with pytest.raises(SystemExit, match="--force"):
        cli.main(["restore", str(backup)])
    assert cli.main(["restore", str(backup), "--force"]) == 0
    assert usernames(db) == [("root", 1, 0, None, 0)]
    with pytest.raises(SystemExit, match="not found"):
        cli.main(["restore", str(tmp_path / "missing.db"), "--force"])


def test_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        cli.main(["migrate"])
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    with pytest.raises(SystemExit, match="SQLite file"):
        cli.main(["backup", "x.db"])
