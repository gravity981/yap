"""Alembic environment. The database URL comes from the Alembic config or DATABASE_URL."""

import os

from alembic import context

from yap.db.engine import make_engine
from yap.db.models import Base

config = context.config
url = config.get_main_option("sqlalchemy.url") or os.environ["DATABASE_URL"]

engine = make_engine(url)
with engine.connect() as connection:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Table rebuilds (batch mode) drop and recreate a table, which foreign key checks
        # refuse while other rows reference it. The pragma only works outside a transaction;
        # the references are checked after the migrations instead.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        # The driver does not start a transaction for DDL by itself; without this an
        # interrupted migration (e.g. a dev server restarted by its reloader) would stay
        # half applied. Alembic runs inside this transaction and leaves the commit to us.
        connection.exec_driver_sql("BEGIN")
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite needs table rebuilds for most ALTERs
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    if sqlite:
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if broken:
            connection.rollback()
            raise RuntimeError(f"Migration left broken foreign keys, rolled back: {broken[:5]}")
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
engine.dispose()
