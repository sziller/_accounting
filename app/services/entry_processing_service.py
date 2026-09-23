"""Explicit AP recalculation. Only DERIVED_FIELDS may be written by processing."""
from decimal import Decimal, InvalidOperation
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import AccountingEntryORM
from app.engine.accounting_entry_processor import AccountingEntryProcessor, CurrencyConversionResult
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema
from app.services.accounting_entry_service import AccountingEntryService, tags_from_db
from app.services.local_currency_conversion import LocalCurrencyConversion

logger = logging.getLogger(__name__)
SOURCE_FIELDS = (
    'entry_type', 'category_code', 'tax_scope', 'counterparty_name', 'payment_method',
    'payment_date', 'has_invoice', 'invoice_number', 'invoice_date', 'amount_original',
    'currency_original', 'remarks', 'source_filename',
)
DERIVED_FIELDS = (
    'booking_year', 'currency_common', 'amount_common', 'exchange_rate', 'exchange_rate_date',
    'vat_rate_percent', 'vat_amount', 'deductible_percent', 'deductible_amount',
    'deductible_vat_amount', 'writeoff_method', 'conversion_status', 'conversion_note',
)


class EntryProcessingService:
    def __init__(self, db):
        self.db = db
        self.processor = AccountingEntryProcessor()
        self.fx = LocalCurrencyConversion(db)

    def process_entry(self, entry_id):
        """Own one transaction, serialize against edits, calculate before assigning Y."""
        reference = None
        try:
            self.db.execute(text('BEGIN IMMEDIATE'))
            row = self.db.get(AccountingEntryORM, entry_id, populate_existing=True)
            if row is None:
                self.db.rollback()
                return dict(id=entry_id, invoice_number=None, status='failed', message='Entry not found.')
            reference = row.invoice_number
            payload = AccountingEntryCreateSchema.model_validate({
                **{name: getattr(row, name) for name in SOURCE_FIELDS},
                'tags': tags_from_db(row.tags_json),
            })
            conversion = None
            if payload.currency_original != self.processor.currency_common:
                original, common = payload.currency_original, self.processor.currency_common
                if not self.fx.supports(original, common):
                    raise ValueError(f'Unsupported conversion: {original} → {common}.')
                rate = self.fx.lookup(original, common, payload.payment_date)
                source = self.fx.sources[original]
                if rate is None:
                    raise ValueError(f'No {source} EUR/{original} rate on or before {payload.payment_date}.')
                value = Decimal(rate.rate)
                if not value.is_finite() or value <= 0 or Decimal(rate.unit) != 1:
                    raise ValueError('Invalid stored exchange rate.')
                conversion = CurrencyConversionResult(
                    self.fx.calculate(payload.amount_original, value), value, rate.rate_date,
                    'resolved', f'Resolved using {source} EUR/{original} rate from {rate.rate_date}.')
            result = self.processor.process(payload, conversion=conversion)
            for name in DERIVED_FIELDS:
                value = getattr(result, name)
                setattr(row, name, str(value) if isinstance(value, Decimal) else value)
            self.db.flush()
            entry = AccountingEntryService._to_read_schema(row)
            self.db.commit()
            return dict(id=entry_id, invoice_number=reference, status='processed',
                        message='Derived accounting fields recalculated.', entry=entry)
        except (ValueError, InvalidOperation) as exc:
            self.db.rollback()
            return dict(id=entry_id, invoice_number=reference, status='failed', message=str(exc))
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception('AP processing database failure for %s', entry_id)
            return dict(id=entry_id, invoice_number=reference, status='failed', message='Database operation failed.')
        except Exception:
            self.db.rollback()
            logger.exception('AP processing failed for %s', entry_id)
            return dict(id=entry_id, invoice_number=reference, status='failed', message='Entry calculation failed.')

    def process_entries(self):
        ids = list(self.db.scalars(select(AccountingEntryORM.id).order_by(
            AccountingEntryORM.payment_date, AccountingEntryORM.id)))
        self.db.commit()  # End the listing transaction before per-entry transactions.
        results = [self.process_entry(entry_id) for entry_id in ids]
        # Bulk reports need no duplicate full record payloads.
        for result in results:
            result.pop('entry', None)
        return dict(processed=sum(r['status'] == 'processed' for r in results),
                    failed=sum(r['status'] == 'failed' for r in results), entries=results)
