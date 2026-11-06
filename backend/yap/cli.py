"""Admin command line (section 1.3).

    python -m yap.cli migrate
    python -m yap.cli create-admin USERNAME [--investor --currency CHF]
        [--password-stdin]
    python -m yap.cli create-investor USERNAME --currency CHF [--password-stdin]
    python -m yap.cli backup FILE
    python -m yap.cli restore FILE --force
    python -m yap.cli update-prices

The database comes from DATABASE_URL. Passwords are prompted for, or read from
stdin with --password-stdin (for scripts). Accounts created here other than the
first admin get a temporary password that must be changed at first login.
"""

import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from yap.db.engine import make_engine, make_session_factory
from yap.db.migrate import upgrade
from yap.services import accounts
from yap.services.common import ServiceError, SystemClock


def _database_path(url: str) -> Path:
    database = make_url(url).database
    if not database or database == ":memory:":
        raise SystemExit("DATABASE_URL must point to a SQLite file")
    return Path(database)


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise SystemExit("Passwords do not match")
    return password


def _create(
    url: str, username: str, password: str, *, admin: bool, investor: bool, currency: str | None
) -> None:
    upgrade(url)
    engine = make_engine(url)
    try:
        with make_session_factory(engine)() as session:
            accounts.create_account(
                session,
                SystemClock(),
                username=username,
                password=password,
                admin=admin,
                investor=investor,
                base_currency=currency,
                must_change_password=not admin,
            )
            session.commit()
    finally:
        engine.dispose()


def backup(url: str, target: Path) -> None:
    """Consistent copy while the app runs, via SQLite's online backup (NFR-08)."""
    if target.exists():
        raise SystemExit(f"{target} exists; choose a new file")
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(_database_path(url))
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def restore(url: str, source_file: Path) -> None:
    """Replaces the database with a backup (NFR-08). Stop the app first."""
    if not source_file.exists():
        raise SystemExit(f"{source_file} not found")
    source = sqlite3.connect(source_file)
    destination = sqlite3.connect(_database_path(url))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def update_prices(url: str) -> str:
    """PRC-07: one run of the price update by hand, like the scheduled one."""
    from yap.api.settings import _secret
    from yap.prices import AdapterFactory, adapter_for
    from yap.services import price_update
    from yap.services.secrets import KeyBox

    adapters: AdapterFactory = adapter_for
    if os.environ.get("PRICE_FAKE") == "1":
        if os.environ.get("APP_ENV") == "prod":
            raise SystemExit("PRICE_FAKE must not be set in production")
        from yap.prices.fake import fake_adapter

        adapters = fake_adapter
    engine = make_engine(url)
    try:
        with make_session_factory(engine)() as session:
            keys = KeyBox(_secret("APP_SECRET_KEY"))
            run = price_update.run_update(session, SystemClock(), keys, adapters, "cli")
            if run is None:
                raise SystemExit("A price update is running already")
            lines = [
                f"{provider}: " + ", ".join(f"{k} {v}" for k, v in counts.items())
                for provider, counts in (run.result or {}).items()
            ]
            return "\n".join(lines) or "Nothing to update"
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yap.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply all database migrations")
    for name in ("create-admin", "create-investor"):
        sub = commands.add_parser(name)
        sub.add_argument("username")
        sub.add_argument("--password-stdin", action="store_true")
        if name == "create-investor":
            sub.add_argument("--currency", required=True, help="base currency, e.g. CHF")
        else:
            # USR-09: e.g. a single person who runs the app for themselves
            sub.add_argument("--investor", action="store_true", help="also an investor")
            sub.add_argument("--currency", help="base currency with --investor, e.g. CHF")
    commands.add_parser("backup").add_argument("file", type=Path)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("file", type=Path)
    restore_parser.add_argument(
        "--force", action="store_true", help="confirm that the app is stopped"
    )
    commands.add_parser("update-prices", help="update the prices of all listings in use now")
    args = parser.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")

    try:
        if args.command == "migrate":
            upgrade(url)
        elif args.command in ("create-admin", "create-investor"):
            admin = args.command == "create-admin"
            if admin and args.currency and not args.investor:
                raise SystemExit("--currency is only used with --investor")
            password = _read_password(args.password_stdin)
            _create(
                url,
                args.username,
                password,
                admin=admin,
                investor=not admin or args.investor,
                currency=args.currency,
            )
        elif args.command == "backup":
            backup(url, args.file)
        elif args.command == "restore":
            if not args.force:
                raise SystemExit("Stop the app, then confirm with --force")
            restore(url, args.file)
        elif args.command == "update-prices":
            print(update_prices(url))
    except ServiceError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
