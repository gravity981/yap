"""Engine and session setup for SQLite (section 2.4)."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str, *, writer_transactions: bool = True) -> Engine:
    """`writer_transactions`: see `_begin`; the migrations manage their transactions themselves."""
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        if writer_transactions:
            # pysqlite starts no transaction by itself (see `_begin`)
            dbapi_connection.isolation_level = None

    if writer_transactions:

        @event.listens_for(engine, "begin")
        def _begin(connection: Any) -> None:
            # Every request writes (it renews its session), so a transaction that started as
            # a reader would fail at once with "database is locked" when another one
            # committed in the meantime, whatever the busy timeout. Starting as the writer
            # makes it wait its turn instead.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
