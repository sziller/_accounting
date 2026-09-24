# app/core/config.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import os


HOST = os.getenv("ACCOUNTING_HOST", "127.0.0.1")
PORT = int(os.getenv("ACCOUNTING_PORT", "8000"))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# Set this to the directory containing the original JPEG source documents.
AP_SOURCE_IMAGE_DIRECTORY = DATA_DIR / "AP_source_images"
AR_INVOICE_PDF_DIRECTORY = DATA_DIR / "AR_invoice_pdf"
AR_COMMON_CURRENCY = "EUR"

# Inclusive start of MNB EUR/HUF history, through today.
MNB_EXCHANGE_RATE_START_DATE = date(2021, 1, 1)
# Explicit independent EUR/USD history baseline; editable without changing MNB.
ECB_EXCHANGE_RATE_START_DATE = date(2022, 10, 1)
# Synchronization lower-bound tolerance only, never interpolation/filling.
ECB_EXCHANGE_RATE_LOWER_BOUNDARY_TOLERANCE_DAYS = 7


# -----------------------------------------------------------------------------
# Database role names
# -----------------------------------------------------------------------------

DB_ROLE_ACCT = "ACCT"
DB_ROLE_REFR = "REFR"


# -----------------------------------------------------------------------------
# Database filenames and styles
# -----------------------------------------------------------------------------

# Accounting / bookkeeping runtime DB
DB_FULLNAME_ACCT = ".Accounting.db"
DB_STYLE_ACCT = "sqlite"

# Reference DB, optional later:
# categories, VAT rules, exchange rates, static lookup tables
DB_FULLNAME_REFR = ".Reference.db"
DB_STYLE_REFR = "sqlite"


@dataclass(frozen=True)
class DatabaseSpec:
    """=== config class ====
    Immutable database configuration object for one logical DB role.
    === by Sziller & ChatGPT ==="""

    role: str
    fullname: str
    style: str

    @property
    def path(self) -> Path:
        """=== config function ====
        Return the local filesystem path for this database.
        === by Sziller & ChatGPT ==="""
        if self.style != "sqlite":
            raise ValueError(f"Unsupported DB style for local app: {self.style}")

        return DATA_DIR / self.fullname

    @property
    def sqlalchemy_url(self) -> str:
        """=== config function ====
        Return the SQLAlchemy connection URL for this database.
        === by Sziller & ChatGPT ==="""
        if self.style == "sqlite":
            return f"sqlite:///{self.path}"

        raise ValueError(f"Unsupported DB style: {self.style}")


DB_SPECS: dict[str, DatabaseSpec] = {
    DB_ROLE_ACCT: DatabaseSpec(
        role=DB_ROLE_ACCT,
        fullname=DB_FULLNAME_ACCT,
        style=DB_STYLE_ACCT,
    ),
    DB_ROLE_REFR: DatabaseSpec(
        role=DB_ROLE_REFR,
        fullname=DB_FULLNAME_REFR,
        style=DB_STYLE_REFR,
    ),
}


def get_db_spec(role: str) -> DatabaseSpec:
    """=== config function ====
    Return the full database specification for a configured DB role.
    === by Sziller & ChatGPT ==="""
    try:
        return DB_SPECS[role]
    except KeyError as exc:
        raise KeyError(f"Unknown DB role: {role}") from exc


def get_db_fullname(role: str) -> str:
    """=== config function ====
    Return the configured database filename for a DB role.
    === by Sziller & ChatGPT ==="""
    return get_db_spec(role).fullname


def get_db_style(role: str) -> str:
    """=== config function ====
    Return the configured database backend style for a DB role.
    === by Sziller & ChatGPT ==="""
    return get_db_spec(role).style


def get_db_path(role: str) -> Path:
    """=== config function ====
    Return the resolved filesystem path for a DB role.
    === by Sziller & ChatGPT ==="""
    return get_db_spec(role).path


def get_sqlalchemy_url(role: str) -> str:
    """=== config function ====
    Return the SQLAlchemy connection URL for a DB role.
    === by Sziller & ChatGPT ==="""
    return get_db_spec(role).sqlalchemy_url


APP_ROUTER_INFO = {
    "accounting_entries": {
        "use": True,
        "prefix": "/acct",
        "env_ns": DB_ROLE_ACCT,
        "module": "app.routers.router_accounting_entries",
        "class_name": "AccountingEntriesRouter",
        "db_roles": [DB_ROLE_ACCT],

        "init": {
            "prefix": "/acct",
            "env_ns": DB_ROLE_ACCT,
            "db_roles": [DB_ROLE_ACCT],
            "tags": ["accounting_entries"],
        },

        "args": {
            "db_default_table_classname": "app.db.models.AccountingEntryORM",
        },

        "description": "Endpoints for local bookkeeping and accounting entries.",
        "externalDocs": {
            "description": "Local bookkeeping application documentation.",
            "url": "http://localhost:8000/docs",
        },
    },
}
