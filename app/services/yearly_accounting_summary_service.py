"""Read-only yearly aggregation. Accounting engines are upstream authorities."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
import re

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import AccountingEntryORM, OutgoingInvoiceORM
from app.domain.yearly_accounting_summary import (
    YearlyAccountingSummary, SummaryWarning, ApSummaryGroup, ArCurrencyComponents,
)
from app.services.ar_recognition_service import ArRecognitionService


def _money(value):
    if value is None:
        return None
    try:
        value = Decimal(value)
        return value if value.is_finite() and value >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _currency(value):
    return isinstance(value, str) and re.fullmatch('[A-Z]{3}', value) is not None


def _known_sum(values):
    known = [value for value in values if value is not None]
    return sum(known, Decimal('0')) if known else None


class YearlyAccountingSummaryService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, tax_year: int) -> YearlyAccountingSummary:
        if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 1 <= tax_year <= 9999:
            raise ValueError('tax_year must be an integer between 1 and 9999')
        with self.db.no_autoflush, localcontext() as context:
            context.prec = 64
            return self._build(tax_year)

    def _build(self, tax_year):
        warnings = [SummaryWarning('processing_freshness_unverified', 0,
            'Processed field presence is checked; rule-processing freshness cannot currently be proven.')]
        incomplete = False
        currencies = set()
        groups = defaultdict(list)
        included = excluded = non_expense = unassigned = multi_year = 0
        expense = vat = Decimal('0')
        columns = ('entry_type','category_code','tax_scope','booking_year','currency_common',
                   'amount_common','vat_amount','deductible_amount','deductible_vat_amount',
                   'conversion_status','writeoff_method')
        rows = self.db.execute(select(*(getattr(AccountingEntryORM, key) for key in columns))).mappings()
        for row in rows:
            if row['booking_year'] is None or not 1 <= row['booking_year'] <= 9999:
                unassigned += 1
                continue
            if row['booking_year'] != tax_year:
                continue
            amounts = tuple(_money(row[key]) for key in ('amount_common','vat_amount','deductible_amount','deductible_vat_amount'))
            valid = (all(value is not None for value in amounts) and _currency(row['currency_common'])
                     and row['conversion_status'] in ('resolved','not_required'))
            groups[(row['entry_type'],row['category_code'],row['tax_scope'],row['currency_common'])].append((amounts,valid))
            if _currency(row['currency_common']):
                currencies.add(row['currency_common'])
            if not valid:
                incomplete = True
            multi_year += row['writeoff_method'] == 'multi_year'
            if row['entry_type'] != 'expense':
                non_expense += 1
                continue
            if not valid:
                excluded += 1
            else:
                included += 1
                expense += amounts[2]
                vat += amounts[3]
        breakdown = tuple(ApSummaryGroup(*key, len(items), sum(not valid for _,valid in items),
            *(_known_sum([amounts[i] for amounts,_ in items]) for i in range(4)))
            for key,items in sorted(groups.items(), key=lambda pair: tuple(str(v) for v in pair[0])))
        invalid_ap = sum(group.incomplete_count for group in breakdown)
        for code,count,message in (
            ('ap_incomplete',invalid_ap,'Selected-year AP records have missing/unusable processed values or incomplete conversion. Expense records are excluded from headlines; detail sums contain known values only.'),
            ('ap_year_unassigned',unassigned,'AP records have no usable booking year; they cannot be assigned to any year and are not silently dated from payment_date.'),
            ('ap_non_expense',non_expense,'Non-expense AP records appear in detail only, not headline expense/VAT subtotals.'),
            ('multi_year_limitation',multi_year,'Only the persisted booking-year deduction is shown; no depreciation continuation exists.'),
        ):
            if count: warnings.append(SummaryWarning(code,count,message))
        incomplete |= bool(unassigned)
        ar_groups = defaultdict(list)
        events_count = ar_excluded = no_events = resolution_failures = 0
        revenue = Decimal('0')
        recognition = ArRecognitionService(self.db)
        # Never prefilter invoices: cross-year events and cumulative prefixes matter.
        invoices = self.db.execute(select(OutgoingInvoiceORM.id,OutgoingInvoiceORM.currency_common).order_by(OutgoingInvoiceORM.id)).all()
        for identity, common_currency in invoices:
            try:
                events = recognition.resolve_invoice_events(identity)
            except (ValueError, InvalidOperation):
                resolution_failures += 1
                incomplete = True
                continue
            if not events:
                no_events += 1
            for event in events:
                if event.tax_year != tax_year:
                    continue
                events_count += 1
                ar_groups[event.currency_original].append(event)
                if _currency(common_currency):
                    currencies.add(common_currency)
                common = _money(event.amount_common)
                if common is None or not _currency(common_currency):
                    ar_excluded += 1
                    incomplete = True
                else:
                    revenue += common
        components = tuple(ArCurrencyComponents(currency,len(events),
            sum((e.amount_original for e in events),Decimal('0')),
            _known_sum([e.net_amount_original for e in events]),
            _known_sum([e.vat_amount_original for e in events]),
            sum(e.net_amount_original is None for e in events),
            sum(e.vat_amount_original is None for e in events))
            for currency,events in sorted(ar_groups.items()))
        missing_net = sum(group.missing_net_count for group in components)
        missing_vat = sum(group.missing_vat_count for group in components)
        for code,count,message in (
            ('ar_common_incomplete',ar_excluded,'Recognized events lack a usable common amount/currency and are excluded from the common headline.'),
            ('ar_net_missing',missing_net,'Recognized net is unknown for these events; known subtotals are partial.'),
            ('ar_vat_missing',missing_vat,'Recognized VAT is unknown for these events; known subtotals are partial.'),
            ('ar_recognition_failed',resolution_failures,'Invoice recognition could not be resolved; affected years cannot be established.'),
        ):
            if count: warnings.append(SummaryWarning(code,count,message))
        incomplete |= bool(missing_net or missing_vat)
        mismatch = len(currencies) > 1
        if mismatch:
            incomplete = True
            warnings.append(SummaryWarning('currency_mismatch',len(currencies),
                'Common currencies disagree: '+', '.join(sorted(currencies))+'. Common headlines are unavailable; no mixed-currency total is returned.'))
        return YearlyAccountingSummary(
            tax_year, next(iter(currencies)) if len(currencies)==1 else None, tuple(sorted(currencies)),
            included,excluded,non_expense,unassigned,events_count,ar_excluded,no_events,
            None if mismatch else revenue, None if mismatch else expense,
            None if mismatch else revenue-expense, None if mismatch else vat,
            components,breakdown,'incomplete' if incomplete else 'complete',tuple(warnings))
