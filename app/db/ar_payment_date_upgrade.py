"""Add the authoritative nullable receipt date without backfilling guessed facts."""
from sqlalchemy import text


def upgrade_ar_payment_date(engine):
    with engine.connect() as connection:
        connection.execute(text('BEGIN IMMEDIATE'))
        try:
            columns = {row[1] for row in connection.exec_driver_sql(
                'PRAGMA table_info(outgoing_invoices)')}
            if 'payment_date' not in columns:
                connection.exec_driver_sql(
                    'ALTER TABLE outgoing_invoices ADD COLUMN payment_date DATE')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
