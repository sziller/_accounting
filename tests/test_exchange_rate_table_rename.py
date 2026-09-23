"""Legacy FX table rename preserves rows and is safe to repeat."""
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, inspect
from app.db.models import Base
from app.db.exchange_rate_upgrade import rename_legacy_exchange_rate_table
from app.db import database


class ExchangeRateTableRenameTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)

    def test_init_renames_legacy_table_without_changing_rows_or_indexes(self):
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as db:
            db.exec_driver_sql('ALTER TABLE eur_huf_exchange_rates RENAME TO exchange_rates')
            db.exec_driver_sql("""INSERT INTO exchange_rates
                (id,rate_date,base_currency,quote_currency,rate,unit,source,created_at,updated_at)
                VALUES ('original','2021-01-04','EUR','HUF','360.123400','1','MNB',
                        '2021-01-05 00:00:00','2021-01-06 00:00:00')""")
            before = db.exec_driver_sql('SELECT * FROM exchange_rates').all()
            indexes = db.exec_driver_sql('PRAGMA index_list(exchange_rates)').all()
        with patch.object(database, 'engine', self.engine):
            database.init_db()
            database.init_db()
        with self.engine.connect() as db:
            self.assertEqual(before, db.exec_driver_sql('SELECT * FROM eur_huf_exchange_rates').all())
            # SQLite may rename automatic constraint indexes; explicit indexes survive.
            after = db.exec_driver_sql('PRAGMA index_list(eur_huf_exchange_rates)').all()
            self.assertEqual({r[1] for r in indexes if not r[1].startswith('sqlite_autoindex')},
                             {r[1] for r in after if not r[1].startswith('sqlite_autoindex')})
        self.assertNotIn('exchange_rates', inspect(self.engine).get_table_names())
        self.assertIn('eur_usd_exchange_rates', inspect(self.engine).get_table_names())

    def test_fresh_database_initializes_normally(self):
        with patch.object(database, 'engine', self.engine):
            database.init_db()
        self.assertIn('eur_huf_exchange_rates', inspect(self.engine).get_table_names())
        self.assertNotIn('exchange_rates', inspect(self.engine).get_table_names())

    def test_conflicting_tables_fail_without_dropping_either(self):
        with self.engine.begin() as db:
            db.exec_driver_sql('CREATE TABLE exchange_rates (value TEXT)')
            db.exec_driver_sql('CREATE TABLE eur_huf_exchange_rates (value TEXT)')
            db.exec_driver_sql("INSERT INTO exchange_rates VALUES ('legacy')")
        with self.assertRaisesRegex(RuntimeError, 'Both'):
            rename_legacy_exchange_rate_table(self.engine)
        with self.engine.connect() as db:
            self.assertEqual(db.exec_driver_sql('SELECT value FROM exchange_rates').scalar(), 'legacy')
        self.assertIn('eur_huf_exchange_rates', inspect(self.engine).get_table_names())
