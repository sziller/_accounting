"""Atomic full AP recalculation through the public API."""
from datetime import date
from decimal import Decimal
import unittest
from fastapi import FastAPI
from types import SimpleNamespace
import test_receivables as fixtures
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from unittest.mock import patch
from app.db.database import get_db_session
from app.db.models import Base, AccountingEntryORM
from app.routers.router_accounting_entries import AccountingEntriesRouter
from app.services.entry_processing_service import SOURCE_FIELDS, DERIVED_FIELDS
from app.services.exchange_rate_service import ExchangeRateService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService
from test_invoice_number_policy import raw_row


class EntryProcessingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        app = FastAPI()
        router = AccountingEntriesRouter()
        router.reinit()
        app.include_router(router)
        def session():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db_session] = session
        self.app = app
        def post(path):
            status, body = fixtures.ReceivablesTests.request(self, 'POST', path.removeprefix('/acct/v0/'), {})
            return SimpleNamespace(status_code=status, text=str(body), json=lambda: body)
        self.client = SimpleNamespace(post=post)

    def seed(self, number, currency='EUR'):
        row = raw_row(number)
        row.currency_original = currency
        row.amount_original = '119.00'
        row.payment_date = date(2026, 2, 10)
        row.category_code = 'bewirtung'
        row.amount_common = '999.00'
        row.vat_amount = '999.00'
        row.deductible_amount = '999.00'
        row.booking_year = 1900
        row.writeoff_method = 'none'
        row.exchange_rate = '999'
        row.exchange_rate_date = date(1900, 1, 1)
        row.conversion_status = 'resolved'
        with Session(self.engine) as db:
            db.add(row)
            db.commit()
            return row.id

    def snapshot(self, id):
        with Session(self.engine) as db:
            row = db.get(AccountingEntryORM, id)
            return {c.name: getattr(row, c.name) for c in row.__table__.columns}

    def process(self, id):
        response = self.client.post(f'/acct/v0/entries/{id}/process')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_stale_values_replaced_all_sources_preserved_and_idempotent(self):
        id = self.seed('ONE')
        other = self.seed('TWO')
        before, untouched = self.snapshot(id), self.snapshot(other)
        result = self.process(id)
        self.assertEqual(result['status'], 'processed')
        after = self.snapshot(id)
        protected = set(before) - set(DERIVED_FIELDS) - {'updated_at'}
        self.assertEqual({k: before[k] for k in protected}, {k: after[k] for k in protected})
        self.assertEqual((after['amount_common'], after['vat_amount'], after['deductible_amount'],
                          after['deductible_vat_amount']), ('119.00', '19.00', '83.30', '13.30'))
        self.assertEqual((after['booking_year'], after['writeoff_method']), (2026, 'partial'))
        self.assertIsNone(after['exchange_rate'])
        self.assertIsNone(after['exchange_rate_date'])
        self.assertEqual(self.snapshot(other), untouched)
        self.process(id)
        again = self.snapshot(id)
        self.assertEqual({k: after[k] for k in DERIVED_FIELDS}, {k: again[k] for k in DERIVED_FIELDS})
        self.assertEqual(result['entry']['vat_amount'], '19.00')

    def test_both_historical_sources_and_division(self):
        for currency, service, source, amount, rate in [
            ('HUF', ExchangeRateService, 'MNB', '40000', '400'),
            ('USD', EurUsdExchangeRateService, 'ECB', '110', '1.1000')]:
            with self.subTest(currency=currency):
                id = self.seed(currency, currency)
                with Session(self.engine) as db:
                    row = db.get(AccountingEntryORM, id)
                    row.amount_original = amount
                    db.commit()
                    service(db).upsert_rate(rate_date=date(2026, 2, 6), base_currency='EUR',
                        quote_currency=currency, source=source, rate=Decimal(rate))
                self.assertEqual(self.process(id)['status'], 'processed')
                row = self.snapshot(id)
                self.assertEqual(row['amount_common'], '100.00')
                self.assertEqual(row['exchange_rate_date'], date(2026, 2, 6))
                self.assertIn(source, row['conversion_note'])

    def test_bulk_all_statuses_and_failure_keeps_entire_row(self):
        good = self.seed('GOOD')
        missing = self.seed('MISSING', 'USD')
        bad = self.seed('INVALID')
        with Session(self.engine) as db:
            db.get(AccountingEntryORM, bad).category_code = 'unknown'
            db.commit()
        before_missing, before_bad = self.snapshot(missing), self.snapshot(bad)
        report = self.client.post('/acct/v0/entries/process').json()
        self.assertEqual((report['processed'], report['failed']), (1, 2))
        self.assertEqual(len(report['entries']), 3)
        self.assertEqual(self.snapshot(missing), before_missing)
        self.assertEqual(self.snapshot(bad), before_bad)
        self.assertEqual(self.snapshot(good)['amount_common'], '119.00')
        self.assertIn('No ECB', next(r['message'] for r in report['entries'] if r['id'] == missing))

    def test_failure_after_assignments_rolls_back(self):
        id = self.seed('ROLLBACK')
        before = self.snapshot(id)
        with patch('app.services.entry_processing_service.AccountingEntryService._to_read_schema', side_effect=ValueError('test failure')):
            self.assertEqual(self.process(id)['status'], 'failed')
        self.assertEqual(before, self.snapshot(id))

    def test_unknown_id_returns_explicit_failure(self):
        self.assertEqual(self.process('missing')['status'], 'failed')
