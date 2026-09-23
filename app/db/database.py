# app/db/database.py

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATA_DIR, DB_ROLE_ACCT, get_sqlalchemy_url
from app.db.models import Base
from app.db.ar_currency_upgrade import upgrade_ar_currencies
from app.db.ar_payment_date_upgrade import upgrade_ar_payment_date
from app.db.exchange_rate_upgrade import upgrade_exchange_rate_identity, rename_legacy_exchange_rate_table


# -----------------------------------------------------------------------------
# Database engine and session factory
# -----------------------------------------------------------------------------

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine: Engine = create_engine(
    get_sqlalchemy_url(DB_ROLE_ACCT),
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def enable_sqlite_foreign_keys(connection, connection_record) -> None:
    """SQLite requires FK enforcement to be enabled on every connection."""
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(engine, "connect", enable_sqlite_foreign_keys)


def init_db() -> None:
    """=== database function ====
    Create all configured SQLAlchemy tables if they do not already exist.
    === by Sziller & ChatGPT ==="""
    rename_legacy_exchange_rate_table(engine)
    Base.metadata.create_all(bind=engine)
    upgrade_exchange_rate_identity(engine)
    upgrade_ar_currencies(engine)
    upgrade_ar_payment_date(engine)


def get_db_session() -> Generator[Session, None, None]:
    """=== database function ====
    Provide a SQLAlchemy session for FastAPI dependencies and close it afterwards.
    === by Sziller & ChatGPT ==="""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def create_db_session() -> Session:
    """=== database function ====
    Create a standalone SQLAlchemy session for scripts, tests, and service code.
    === by Sziller & ChatGPT ==="""
    return SessionLocal()


def drop_db() -> None:
    """=== database function ====
    Drop all SQLAlchemy tables from the configured accounting database.
    === by Sziller & ChatGPT ==="""
    Base.metadata.drop_all(bind=engine)


def reset_db() -> None:
    """=== database function ====
    Drop and recreate all SQLAlchemy tables for local development resets.
    === by Sziller & ChatGPT ==="""
    drop_db()
    init_db()
