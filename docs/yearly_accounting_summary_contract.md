# Yearly accounting preview contract

The summary consumes processed accounting facts. It does not reproduce the
accounting engine. No report model is persisted; no UI or endpoint is introduced.

`YearlyAccountingSummaryService(db).build(tax_year)` returns frozen domain
objects from `app/domain/yearly_accounting_summary.py`. It performs scalar reads
with autoflush disabled, does not commit or write, and uses Decimal precision 64
without additional monetary rounding. Caller owns the session/read transaction.

## Populations and time

AP selection is strictly booking_year == selected year. Only entry_type='expense'
contributes to expense/input-VAT headlines. All selected-year AP types remain in
detail, grouped by entry_type/category_code/tax_scope/currency_common. Non-expense
counts/warnings explicitly disclose the headline exclusion. No category is legally
reclassified and no amount sign is inferred from entry_type.

AR loads every invoice and asks ArRecognitionService for its COMPLETE ordered
sequence before filtering event.tax_year. Invoice issue/manual receipt years never
prefilter the population. The report never calls allocation math directly. Parent
invoice currency_common supplies the missing currency context for event.amount_common.

## Monetary bases

Headlines use stored AP deductible_amount and deductible_vat_amount, not formulas
from gross/rates/percentages. AR headline uses event.amount_common. The result is:
recognized AR common gross minus processed AP expense deductible gross.
`gross_basis_result` is NOT taxable profit, net profit, or a VAT-adjusted result.

AR original gross, known net, and known VAT are grouped separately by original
currency. Unknown components are not fabricated: all-unknown known subtotal is
None; mixed known/unknown subtotal sums only known values and supplies missing
counts. Common net/VAT is not derived. AP detail sums usable populated fields even
on incomplete rows; incomplete_count warns that these are partial known subtotals.
An all-missing detail subtotal is None, not zero.

## Currency and preview completeness

Currencies are taken conservatively from all selected-year AP detail records and
selected AR events with valid common-currency context, including incomplete items.
With exactly one currency, report_currency identifies it. With none, it is None
(empty/zero preview does not imply EUR). With multiple, common headline amounts
and gross_basis_result are None, completeness is incomplete, and currency_mismatch
lists the currencies. Currency-specific detail remains available. No conversion
occurs and no mixed-currency total is returned.

AP completeness requires finite non-negative amount_common, vat_amount,
deductible_amount, deductible_vat_amount, a valid uppercase three-letter currency,
and conversion_status resolved/not_required. Incomplete expense rows are excluded
from headlines; ap_included_count/ap_excluded_count count expense rows only.
Incomplete non-expense rows also flag preview completeness through detail counts.
Missing/out-of-domain booking_year cannot be assigned from payment_date: these
are globally counted by ap_unassigned_year_count and warn in every year's preview.
The normal database schema forbids NULL booking_year, but loading remains defensive.

Missing AR common amount/currency excludes that event only from its common
headline, not original-currency components or ar_event_count. Missing net/VAT
marks the overall preview incomplete without withholding known common totals.
No events is not an error: ar_invoices_without_events counts such invoices across
all years. Recognition resolution failures are counted and mark all-year previews
incomplete because affected event years cannot be established. Infrastructure/DB
errors are not converted into a fabricated empty or complete report.

Warnings have stable code/count/message fields. Presence checks cannot prove
processing freshness: every summary explicitly says so. No Process Entry call,
VAT/deduction history lookup, FX operation or depreciation algorithm is permitted.
Multi-year rows contribute their persisted booking-year amount only and carry a
limitation warning; no later-year continuation is fabricated. Informational
non-expense/freshness/multi-year warnings do not by themselves mark monetary
presence incomplete. 'complete' therefore means this preview's data checks passed,
not legal finality or historically verified rules.

This preserves the legacy stored-facts-to-summary architecture:
PAYED_SUM_to_write_off → AP deductible_amount;
VAT_to_write_off → AP deductible_vat_amount.
It does not seek byte-identical reproduction of legacy float calculations.

## Read-only API

`GET /acct/v0/yearly-accounting-summary/{tax_year}` exposes the summary unchanged.
The year must be an integer from 1 through 9999; invalid path values return HTTP
422. A successful preview returns HTTP 200 even when `completeness` is
`incomplete`; callers must inspect completeness and structured warnings.

The response preserves every domain field name. Decimal monetary values are JSON
strings, including nested AP breakdown and AR original-currency groups. Nullable
values remain JSON `null`; tuples serialize as arrays. Warnings are objects with
`code`, `count`, and `message`. The OpenAPI response schema documents this contract.
The route only calls `YearlyAccountingSummaryService.build()` and serializes its
result. It does not process entries, commit data, or add accounting calculations.

## Gewinnermittlung view

The dedicated `#summary` view renders this pipeline:

processed AP + AR recognition → YearlyAccountingSummaryService
→ read-only yearly-summary API → Gewinnermittlung UI.

The UI renders the yearly summary. It does not calculate accounting results.
The selector initially uses the browser's current calendar year. Entering the view,
changing the year, or clicking Refresh Summary issues only a summary GET request.
The selected year survives navigation; AP/AR drafts are not touched.

Headlines retain backend names and common currency, with unavailable values shown
as `Unavailable`. Decimal strings are displayed verbatim, preserving sub-cent
precision. AP groups retain every supplied entry type; original-currency AR groups
stay separate with explicit missing-component counts. Completeness and structured
warning messages/counts are prominent. Empty successful responses display zeros
and empty-table messages; loading/error states hide previous results to avoid
presenting an old year as the requested report. Late responses cannot replace a
newer request's report. No processing action is triggered by this view.
