"""Startup lifecycle tests with real ECB parsing and isolated SQLite storage."""
import ast
from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.core import config
from app.db.models import Base, ExchangeRateORM, EurUsdExchangeRateORM
from app.services.exchange_rate_service import ExchangeRateService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService
from app.services.ecb_exchange_rate_sync_service import EcbExchangeRateSyncService
from app.services.historical_exchange_rate_service import ExchangeRateProviderError, ExchangeRateSchemaError

HEADER = 'FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n'


class EcbSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        setting = patch.object(config, 'ECB_EXCHANGE_RATE_START_DATE', date(2026, 9, 5))
        setting.start()
        self.addCleanup(setting.stop)
        self.usd = EurUsdExchangeRateService(self.db)

    def sync(self, body, end=date(2026, 9, 7)):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = body.encode()
        with patch('app.services.ecb_exchange_rate_provider.urlopen', return_value=response):
            return EcbExchangeRateSyncService(self.db).synchronize(today=end)

    def test_initial_restart_lookup_precision_and_huf_isolation(self):
        huf = ExchangeRateService(self.db).upsert_rate(rate_date=date(2026, 9, 7),
            base_currency='EUR', quote_currency='HUF', source='MNB', rate=Decimal('390.2500'))
        snapshot = (huf.id, huf.rate, huf.updated_at)
        body = HEADER + 'D,USD,EUR,SP00,A,2026-09-07,1.14900000000000000001\n'
        first = self.sync(body)
        self.assertEqual(first.requested_ranges, ((date(2026, 9, 5), date(2026, 9, 7)),))
        row = self.db.scalar(select(EurUsdExchangeRateORM))
        identity = (row.id, row.created_at, row.updated_at)
        second = self.sync(body)
        self.assertEqual(second.requested_ranges, ((date(2026, 9, 7), date(2026, 9, 7)),))
        self.assertEqual(len(self.db.scalars(select(EurUsdExchangeRateORM)).all()), 1)
        self.assertEqual(identity, (row.id, row.created_at, row.updated_at))
        self.assertEqual(snapshot, (huf.id, huf.rate, huf.updated_at))
        args = dict(base_currency='EUR', quote_currency='USD', source='ECB')
        self.assertEqual(self.usd.get_exact_rate(rate_date=date(2026, 9, 7), **args), Decimal('1.14900000000000000001'))
        self.assertIsNone(self.usd.get_exact_rate(rate_date=date(2026, 9, 6), **args))
        self.assertEqual(self.usd.get_latest_rate_on_or_before(rate_date=date(2026, 9, 13), **args).id, row.id)
        self.sync(body.replace('1.14900000000000000001', '1.1500'))
        self.assertEqual(row.rate, '1.1500')
        self.assertEqual(row.id, identity[0])
        self.assertEqual(len(self.db.scalars(select(ExchangeRateORM)).all()), 1)

    def test_tolerance_config_backfill_and_inclusive_refresh(self):
        self.sync(HEADER + 'D,USD,EUR,SP00,A,2026-09-07,1.1490\n')
        with patch.object(config, 'ECB_EXCHANGE_RATE_LOWER_BOUNDARY_TOLERANCE_DAYS', 0):
            result = self.sync(HEADER, end=date(2026, 9, 13))
        self.assertEqual(result.requested_ranges, ((date(2026, 9, 5), date(2026, 9, 13)),))
        result = self.sync(HEADER, end=date(2026, 9, 13))
        self.assertEqual(result.requested_ranges, ((date(2026, 9, 7), date(2026, 9, 13)),))
        self.assertEqual(result.processed_count, 0)

    def test_failures_and_missing_table(self):
        with self.assertRaises(ExchangeRateProviderError):
            self.sync('broken')
        self.assertEqual(self.db.scalars(select(EurUsdExchangeRateORM)).all(), [])
        EurUsdExchangeRateORM.__table__.drop(self.engine)
        with self.assertRaises(ExchangeRateSchemaError):
            self.sync(HEADER)

    def test_wrong_pair_and_future_start_rejected(self):
        with self.assertRaises(ValueError):
            self.usd.upsert_rate(rate_date=date(2026, 9, 7), base_currency='EUR',
                quote_currency='HUF', source='MNB', rate=Decimal('390'))
        with self.assertRaises(ValueError):
            self.sync(HEADER, end=date(2020, 1, 1))

    def test_existing_database_additive_upgrade_preserves_huf(self):
        EurUsdExchangeRateORM.__table__.drop(self.engine)
        ExchangeRateService(self.db).upsert_rate(rate_date=date(2021, 1, 4),
            base_currency='EUR', quote_currency='HUF', source='MNB', rate=Decimal('360.000'))
        before = self.db.execute(text('SELECT * FROM eur_huf_exchange_rates')).all()
        self.db.commit()
        from app.db import database
        with patch.object(database, 'engine', self.engine):
            database.init_db()
            database.init_db()
        self.assertEqual(before, self.db.execute(text('SELECT * FROM eur_huf_exchange_rates')).all())
        self.assertEqual(self.db.scalars(select(EurUsdExchangeRateORM)).all(), [])

    def test_startup_order_session_cleanup_and_error_policy(self):
        # Execute the actual startup functions without importing main's global app.
        tree = ast.parse(Path('main.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        env = {name: MagicMock() for name in ('create_db_session', 'logger', 'MnbExchangeRateSyncService',
               'EcbExchangeRateSyncService', 'FastAPI', 'init_db', 'StaticFiles', 'FrontendRouter',
               'AccountingEntriesRouter', 'ReceivablesRouter', 'YearlyAccountingSummaryRouter')}
        env.update(ExchangeRateProviderError=ExchangeRateProviderError, MnbExchangeRateProviderError=ExchangeRateProviderError)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'main.py', 'exec'), env)
        order = []
        env['init_db'].side_effect = lambda: order.append('init')
        env['MnbExchangeRateSyncService'].return_value.synchronize.side_effect = lambda: order.append('MNB')
        env['EcbExchangeRateSyncService'].return_value.synchronize.side_effect = ExchangeRateProviderError('offline')
        env['create_app']()
        self.assertEqual(order, ['init', 'MNB'])
        env['EcbExchangeRateSyncService'].return_value.synchronize.assert_called_once()
        self.assertEqual(env['create_db_session'].return_value.close.call_count, 2)
        env['logger'].exception.assert_called_once()
        env['EcbExchangeRateSyncService'].return_value.synchronize.side_effect = OperationalError('x', {}, Exception())
        with self.assertRaises(OperationalError):
            env['synchronize_ecb_rates_on_startup']()
        self.assertEqual(env['create_db_session'].return_value.close.call_count, 3)
