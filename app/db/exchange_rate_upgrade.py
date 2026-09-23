"""Add pair/date uniqueness without rebuilding or discarding historical rates."""
from sqlalchemy import text


def rename_legacy_exchange_rate_table(engine):
    """Rename in place before create_all; preserve all rows and indexes."""
    with engine.connect() as connection:
        connection.execute(text("BEGIN IMMEDIATE"))
        try:
            tables = set(connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).scalars())
            if "exchange_rates" in tables:
                if "eur_huf_exchange_rates" in tables:
                    raise RuntimeError(
                        "Both exchange_rates and eur_huf_exchange_rates exist; "
                        "resolve the table conflict before startup. No data was changed."
                    )
                connection.exec_driver_sql(
                    "ALTER TABLE exchange_rates RENAME TO eur_huf_exchange_rates"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def upgrade_exchange_rate_identity(engine):
    with engine.connect() as connection:
        connection.execute(text("BEGIN IMMEDIATE"))
        try:
            conflict = connection.exec_driver_sql("""SELECT rate_date, base_currency, quote_currency
                FROM eur_huf_exchange_rates GROUP BY rate_date, base_currency, quote_currency
                HAVING count(*) > 1 LIMIT 1""").first()
            if conflict:
                raise RuntimeError(
                    f"Conflicting exchange-rate providers for {conflict[0]} {conflict[1]}/{conflict[2]}; "
                    "resolve the authoritative observation before upgrading. No rates were discarded.")
            connection.exec_driver_sql("""CREATE UNIQUE INDEX IF NOT EXISTS uq_exchange_rate_date_pair
                ON eur_huf_exchange_rates (rate_date, base_currency, quote_currency)""")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
