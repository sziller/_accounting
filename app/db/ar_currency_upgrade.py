"""Additive, idempotent SQLite upgrade for existing outgoing-invoice archives."""
import re

from sqlalchemy import text

from app.core import config
from app.db.models import _money_check


def upgrade_ar_currencies(engine):
    common = config.AR_COMMON_CURRENCY
    if not re.fullmatch(r"[A-Z]{3}", common):
        raise ValueError("AR_COMMON_CURRENCY must be a three-letter uppercase code")
    # Serialize schema checks with ALTER/backfill, including concurrent startup.
    with engine.connect() as connection:
        connection.execute(text("BEGIN IMMEDIATE"))
        try:
            columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(outgoing_invoices)")}
            definitions = {
                "amount_original": "VARCHAR(64) NOT NULL DEFAULT '1' CHECK (" + _money_check("amount_original") + ")",
                "amount_common": "VARCHAR(64) CHECK (" + _money_check("amount_common", positive=False) + ")",
                "currency_original": "VARCHAR(3) NOT NULL DEFAULT 'EUR' CHECK (length(currency_original) = 3 AND currency_original NOT GLOB '*[^A-Z]*')",
                "currency_common": f"VARCHAR(3) NOT NULL DEFAULT '{common}' CHECK (length(currency_common) = 3 AND currency_common NOT GLOB '*[^A-Z]*')",
            }
            for column, definition in definitions.items():
                if column in columns:
                    continue
                connection.exec_driver_sql(f"ALTER TABLE outgoing_invoices ADD COLUMN {column} {definition}")
                # SQLite needs a non-null constant default for ADD COLUMN. Replace
                # it with the exact stored source value within this transaction.
                if column == "amount_original":
                    connection.exec_driver_sql("UPDATE outgoing_invoices SET amount_original = gross_amount")
                elif column == "currency_original":
                    connection.exec_driver_sql("UPDATE outgoing_invoices SET currency_original = currency")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
