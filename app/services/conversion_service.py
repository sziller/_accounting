# app/services/conversion_service.py

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.exchange_rate_repository import decimal_from_db
from app.db.models import AccountingEntryORM
from app.domain.accounting_rules import (
    get_deductible_percent,
    get_vat_rate_percent,
)
from app.services.local_currency_conversion import LocalCurrencyConversion
from app.domain.tax_year import resolve_tax_year
from app.domain.deduction_calculation import calculate_deductions


CENT = Decimal("0.01")


class ConversionService:
    """
    === Class: ConversionService ===
    Resolve pending accounting-entry amounts into the application's common
    currency using exchange rates already stored in the local database.

    The current implemented external-currency conversion path is:

    `HUF -> EUR`

    using historical MNB EUR/HUF exchange-rate observations.

    === Responsibilities ===
    - locate accounting entries whose conversion status is `pending`;
    - retrieve suitable locally stored historical exchange rates;
    - convert supported original-currency amounts into EUR;
    - persist exchange-rate metadata used for the conversion;
    - update conversion status and explanatory notes;
    - recalculate VAT and deductible amounts after conversion;
    - mark unsupported currency paths as failed.

    === Non-Responsibilities ===
    This service does not:

    - contact MNB;
    - fetch exchange rates remotely;
    - import exchange-rate history;
    - determine whether the local rate database is current;
    - manipulate invoice source files.

    Remote rate acquisition belongs to
    `MnbExchangeRateImportService`.

    === Supported Conversion Behavior ===
    If original and common currencies are identical:

    - no exchange rate is required;
    - the original amount becomes the common-currency amount;
    - conversion status becomes `not_required`.

    Current foreign-currency support:

    `HUF -> EUR`

    using a stored MNB observation represented as:

    `1 EUR = <rate> HUF`

    Conversion is therefore:

    `EUR amount = HUF amount / EUR-HUF rate`

    Other currency paths are currently marked as `failed`.

    === Historical Rate Lookup ===
    HUF/EUR conversion requests the newest locally stored MNB EUR/HUF
    observation whose date is less than or equal to the accounting entry's
    `payment_date`.

    This supports weekends and holidays where MNB may publish no new rate on
    the exact accounting date.

    === Important Current Limitation ===
    No maximum age/freshness constraint is applied to historical fallback.

    Consequently, if the local exchange-rate table is incomplete, an
    arbitrarily old observation may currently be accepted as the newest rate
    available before the requested payment date.

    The local exchange-rate dataset should therefore be kept synchronized
    before pending entries are automatically resolved.

    === Unit Handling ===
    `ExchangeRateORM.unit` is not used by this service.

    This is compatible with the currently implemented EUR/HUF MNB path where
    EUR is quoted with unit `1`.

    Generic MNB currencies with provider units other than `1` must not be
    assumed to convert correctly without extending the conversion formula.

    === Transaction Behavior ===
    Batch reprocessing modifies eligible ORM rows in memory and commits once
    after processing the selected batch.

    Single-entry reprocessing commits after attempting that entry.

    === by Sziller & ChatGPT ===
    """

    def __init__(self, db: Session) -> None:
        """=== service function ====
        Store the active SQLAlchemy session and initialize exchange-rate access.
        === by Sziller & ChatGPT ==="""
        self.db = db
        self.currency_conversion = LocalCurrencyConversion(db)
        self.exchange_rate_service = self.currency_conversion.huf

    def reprocess_pending(self, *, limit: int = 100) -> int:
        """
        === Method name: reprocess_pending ===
        Attempt to resolve a bounded set of accounting entries currently marked
        with conversion status `pending`.

        === Parameters ===
        - `limit: int`
          Maximum number of pending entries considered.

          Default: `100`

        === Functionality ===
        1. Retrieve pending accounting entries through `_get_pending_entries()`.
        2. Process entries in ascending payment-date order.
        3. Attempt conversion of each entry through `_try_resolve_entry()`.
        4. Count entries successfully resolved or changed to `not_required`.
        5. Commit all resulting accounting-entry changes once.
        6. Return the resolved count.

        === Returns ===
        Integer number of entries for which `_try_resolve_entry()` returned
        `True`.

        === Important Semantics ===
        An entry that remains pending because no suitable local rate exists does
        not increase the count.

        An unsupported conversion path is marked `failed` but also does not
        increase the count.

        === Remote Behavior ===
        No remote provider is contacted.

        Only rates already stored locally are available to this method.

        === Transaction Behavior ===
        One database commit occurs after the selected batch has been processed.

        === by Sziller & ChatGPT ===
        """
        rows = self._get_pending_entries(limit=limit)
        resolved_count = 0

        for row in rows:
            resolved = self._try_resolve_entry(row)

            if resolved:
                resolved_count += 1

        self.db.commit()

        return resolved_count

    def _get_pending_entries(
            self,
            *,
            limit: int,
    ) -> list[AccountingEntryORM]:
        """
        === Method name: _get_pending_entries ===
        Retrieve accounting entries currently waiting for common-currency
        conversion.

        === Selection Criteria ===
        Rows must satisfy:

        `conversion_status == "pending"`

        === Ordering ===
        Entries are processed by:

        `payment_date ASC`

        oldest first.

        === Limit ===
        At most `limit` rows are returned.

        === Persistence Behavior ===
        Read-only.

        === by Sziller & ChatGPT ===
        """
        stmt = (
            select(AccountingEntryORM)
            .filter(AccountingEntryORM.conversion_status == "pending")
            .order_by(AccountingEntryORM.payment_date.asc())
            .limit(limit)
        )

        return list(self.db.execute(stmt).scalars().all())

    def _try_resolve_entry(self, row: AccountingEntryORM) -> bool:
        """
        === Method name: _try_resolve_entry ===
        Attempt to resolve the common-currency state of one accounting entry using
        locally stored exchange-rate information.

        === Parameters ===
        - `row: AccountingEntryORM`
          Persisted accounting entry to examine and potentially modify.

        === Case 1: Original Currency Equals Common Currency ===
        If:

        `currency_original == currency_common`

        then:

        - `amount_common = amount_original`;
        - no exchange rate/date is stored;
        - conversion status becomes `not_required`;
        - conversion note is cleared;
        - dependent VAT/deductibility values are recalculated.

        Returns `True`.

        === Case 2: HUF -> EUR ===
        Requests the latest local MNB rate satisfying:

        - base currency: EUR
        - quote currency: HUF
        - source: MNB
        - rate date <= payment date

        If no such row exists:

        - status remains `pending`;
        - an explanatory conversion note is stored;
        - returns `False`.

        If a rate exists:

        `amount_common = amount_original / exchange_rate`

        rounded to cents using `ROUND_HALF_UP`.

        The entry stores:

        - converted common-currency amount;
        - exchange rate;
        - actual rate date used;
        - status `resolved`;
        - explanatory conversion note.

        VAT and deductible amounts are then recalculated.

        Returns `True`.

        === Case 3: Unsupported Conversion ===
        Any other original/common-currency combination is marked:

        `conversion_status = "failed"`

        with an explanatory note.

        Returns `False`.

        === Important Limitations ===
        - Historical lookup has no maximum fallback age.
        - Exchange-rate `unit` is not incorporated into the conversion formula.
        - Therefore current foreign-currency behavior should be considered
          specifically implemented for MNB EUR/HUF rather than generic MNB
          currency conversion.

        === Transaction Behavior ===
        This method does not commit.

        The caller owns transaction completion.

        === by Sziller & ChatGPT ===
        """
        if row.currency_original == row.currency_common:
            row.amount_common = row.amount_original
            row.exchange_rate = None
            row.exchange_rate_date = None
            row.conversion_status = "not_required"
            row.conversion_note = None
            self._recalculate_derived_fields(row)
            return True

        if self.currency_conversion.supports(row.currency_original, row.currency_common):
            source = self.currency_conversion.sources[row.currency_original]
            rate_row = self.currency_conversion.lookup(
                row.currency_original, row.currency_common, row.payment_date)

            if rate_row is None:
                row.conversion_status = "pending"
                row.conversion_note = (
                    f"No {source} EUR/{row.currency_original} exchange rate available on or before "
                    f"{row.payment_date}."
                )
                return False

            original_amount = Decimal(row.amount_original)
            exchange_rate = decimal_from_db(rate_row.rate)

            row.amount_common = self._decimal_to_db(
                self.currency_conversion.calculate(original_amount, exchange_rate)
            )
            row.exchange_rate = self._decimal_to_db(exchange_rate)
            row.exchange_rate_date = rate_row.rate_date
            row.conversion_status = "resolved"
            row.conversion_note = (
                f"Resolved using {source} EUR/{row.currency_original} rate from {rate_row.rate_date}."
            )

            self._recalculate_derived_fields(row)

            return True

        row.conversion_status = "failed"
        row.conversion_note = (
            f"Unsupported conversion path: "
            f"{row.currency_original}->{row.currency_common}."
        )

        return False

    def _recalculate_derived_fields(self, row: AccountingEntryORM) -> None:
        """=== service function ====
        Recalculate VAT and deductible values after common-currency conversion.
        === by Sziller & ChatGPT ==="""
        if row.amount_common is None:
            row.vat_amount = None
            row.deductible_amount = None
            row.deductible_vat_amount = None
            return

        amount_common = Decimal(row.amount_common)

        vat_rate_percent = get_vat_rate_percent(
            category_code=row.category_code,
            tax_scope=row.tax_scope,
            tax_year=resolve_tax_year(row),
        )

        deductible_percent = get_deductible_percent(row.category_code, tax_year=resolve_tax_year(row))

        vat_amount = self._calculate_vat_from_gross(
            gross_amount=amount_common,
            vat_rate_percent=vat_rate_percent,
        )

        deductions = calculate_deductions(
            tax_year=resolve_tax_year(row), amount_common=amount_common,
            vat_amount=vat_amount, deductible_percent=deductible_percent,
        )
        deductible_amount = deductions.deductible_amount
        deductible_vat_amount = deductions.deductible_vat_amount

        row.vat_rate_percent = self._decimal_to_db(vat_rate_percent)
        row.deductible_percent = self._decimal_to_db(deductible_percent)
        row.vat_amount = self._decimal_to_db(vat_amount)
        row.deductible_amount = self._decimal_to_db(deductible_amount)
        row.deductible_vat_amount = self._decimal_to_db(deductible_vat_amount)

    @staticmethod
    def _calculate_vat_from_gross(
        *,
        gross_amount: Decimal,
        vat_rate_percent: Decimal,
    ) -> Decimal:
        """=== service function ====
        Calculate VAT amount from a gross amount and VAT percentage.
        === by Sziller & ChatGPT ==="""
        if vat_rate_percent == Decimal("0"):
            return Decimal("0.00")

        rate = vat_rate_percent / Decimal("100")
        vat = gross_amount * (Decimal("1") - (Decimal("1") / (Decimal("1") + rate)))

        return ConversionService._money(vat)

    def reprocess_entry(self, *, entry_id: str) -> bool:
        """=== service function ====
        Reprocess one accounting-entry currency conversion by id.
        === by Sziller & ChatGPT ==="""
        row = self.db.get(AccountingEntryORM, entry_id)

        if row is None:
            return False

        resolved = self._try_resolve_entry(row)

        self.db.commit()

        return resolved
    
    @staticmethod
    def _money(value: Decimal) -> Decimal:
        """=== service function ====
        Round a Decimal monetary value to cents.
        === by Sziller & ChatGPT ==="""
        return value.quantize(CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _decimal_to_db(value: Decimal | None) -> str | None:
        """=== service function ====
        Convert Decimal values into database-safe strings.
        === by Sziller & ChatGPT ==="""
        if value is None:
            return None

        return str(value)
