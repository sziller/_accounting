# Accounting-rule contract and historical boundaries

Accounting Entry → authoritative X → resolve tax year → applicable accounting rules
→ ordered Y dependencies → persist Y on the same entry.

## Authority, not independent formulas

X/Y is an authority distinction, not a direct dependency distinction. X is supplied
by the user/source and processing must preserve it. Y belongs to the processing
engine and Process Entry may completely replace it, even when already populated.
Y may depend on earlier Y calculated in the same run; it must not consume stale Y.

X: entry_type, category_code, tax_scope, counterparty_name, payment_method,
payment_date, has_invoice, invoice_number, invoice_date, amount_original,
currency_original, remarks, tags_json (API: tags), source_filename.

Y: booking_year, currency_common, amount_common, exchange_rate, exchange_rate_date,
vat_rate_percent, vat_amount, deductible_percent, deductible_amount,
deductible_vat_amount, writeoff_method, conversion_status, conversion_note.

id, created_at and updated_at are system metadata outside X/Y. Processing preserves
id/created_at; updated_at follows the existing persistence mechanism. VAT class is
an intermediate domain lookup, not a persisted field or user override.

## Current dependencies and sequence

1. Validate X; resolve tax_year from payment_date through resolve_tax_year(entry).
2. Resolve currency/common amount and FX metadata using the existing currency stage.
   Explicit Process Entry performs local FX lookup before calling the processor;
   tax-year resolution is independent of that lookup. FX dates/policy are unchanged.
3. Resolve VAT rate from category_code and tax_scope; resolve deductible percentage
   and writeoff classification from category_code.
4. Calculate VAT from this run's amount_common and vat_rate_percent.
5. Calculate deductible_amount from amount_common and deductible_percent; calculate
   deductible_vat_amount from the newly calculated VAT and deductible_percent.
6. Assemble Y, including booking_year=tax_year, and persist through the existing
   DERIVED_FIELDS assignments and per-entry transaction.

VAT rate does not depend on amount_common; the VAT amount depends on both. Likewise
percentage classification is independent of VAT, but deductible VAT uses both.
The current missing-conversion and atomic failure policies remain unchanged.

## A. Tax year

app/domain/tax_year.py:resolve_tax_year is the single AP policy boundary.
Current IST/payment-date (cash-basis) behavior is payment_date.year. invoice_date
and stored booking_year do not select the year. tax_year is transient processing
context; booking_year remains its persisted Y representation. No tax_year column,
user field, taxation-mode selector, or new processing parameter is introduced.

A future invoice/accrual-date basis could change this boundary. It is intentionally
not implemented. Changing year policy does not implicitly change FX lookup dates.

## B. Historical static parameters

Numerical/classification parameters will live in source-controlled domain code,
using change-point histories: select the latest effective year <= tax_year. Store
only changes, never duplicate annual snapshots. The policy for requests before the
first defined year must be explicit when histories are introduced; no fallback is
implemented in this step.

Illustration only, not a statement of enacted rates and not executable policy:
`{2007: Decimal('19'), 2028: Decimal('20')}` would select 19 for 2027 and 20 for 2028.
Existing VAT/deduction constants remain unchanged and currently year-independent.
This step does not pass tax_year into those functions or convert their constants.

## C. Historical behavioral rules

When an algorithm changes materially, retain separate historical implementations
and use a narrow tax-year resolver to select one. Keep old implementations callable
for historical reproducibility. Do not replace them with a highly parameterized
universal function solely to avoid small amounts of duplication. No hypothetical
future algorithm or behavioral dispatcher is implemented in this step.

## Persistence boundary

Rule definitions and their histories belong in source control, never SQL tables.
The entry database continues storing calculated Y only. No rules database, rule
version/provenance columns, migrations, or schema changes are introduced. Historical
reproduction will require the applicable source definitions; this step makes no
claim that existing rows carry a processing-version snapshot.

The active processor is app/engine/accounting_entry_processor.py. The older duplicate
processor in app/engine/__init__.py now uses the same tax-year boundary; it was not
otherwise reorganized. Services copying processed.booking_year are persistence,
not additional tax-year policies.

## Implemented VAT change-point parameters (Atomic Task 2)

`resolve_historical_value(history, tax_year)` in `app/domain/historical_values.py`
returns the value at the greatest effective year <= tax_year, without modifying
or converting the value. Empty histories and years before the first change point
raise `HistoricalValueUnavailable`, a ValueError domain exception.

An entry at year N applies from tax year N until superseded by a later change
point. Gaps need no annual copies. Artificial future rates exist in tests only.

`accounting_rules.VAT_RATE_HISTORY` now contains one compatibility change point
at year 1 per class: standard=19, reduced=7, none=0, not_applicable=0, multi_year=19.
The AP input schema accepts the full Python date range without a minimum tax year.
Year 1 deliberately preserves the previously timeless application policy for all
those accepted years; it is NOT a reconstructed legislative effective date or a
claim that these percentages were legally correct in every historical period.
Choosing a narrower historical validity boundary would be a separate policy change.

The active processor resolves tax_year once and passes it explicitly to
get_vat_rate_percent. The older processor and pending-conversion recalculation
also use resolve_tax_year. Domestic category → unchanged VAT class → historical
rate. The non-domestic early return remains exactly Decimal('0') and bypasses
history lookup. VAT formulas, FX, booking year, deductible percentages and writeoff
rules are unchanged. Static VAT constants alone have migrated to histories;
the earlier description of timeless VAT constants is superseded by this section.
No database/schema or provenance changes accompany this source-controlled rule data.

## Provisional coverage versus verified history (Atomic Task 2.5)

The canonical production dataset is now explicitly named
`LEGACY_VAT_COMPATIBILITY_HISTORY`. `VAT_RATE_HISTORY` is an alias to that same
mapping for existing callers/tests, not a separate dataset or verified history.
Every class currently has provisional compatibility coverage beginning at year 1.
No entry in this dataset claims a verified legislative effective year. A successful
lookup means the old application policy can be reproduced, not that the policy
has been legally verified for the requested year.

Read-only local-data audit at this step: five AP entries, payment dates from
2024-01-12 through 2026-09-05; two records in 2024 and three in 2026. These counts
are an audit snapshot, not configured limits. No AP minimum accounting year is
configured. MNB history starts 2021-01-01; ECB history starts 2024-01-01. Those are
independent FX collection limits and do not establish VAT historical coverage.
Tests using years 1 and 9999 exercise accepted-date compatibility only, while
artificial multi-change-point histories test generic resolution semantics.

Migration strategy, for a later explicitly authorized rules task:
1. Establish reviewed effective years and values per VAT class; do not infer them
   from this compatibility mapping or from the FX collection configuration.
2. Introduce clearly distinguished verified histories and tests for their declared
   periods. Do not silently append verified points to a mapping still labeled
   entirely provisional. Keep any retained legacy coverage explicitly named.
3. Switch the VAT-specific boundary to the verified histories over their declared
   coverage, and explicitly decide whether to retire or narrow earlier compatibility
   support. Before-first-year requests must fail unless a separately visible
   compatibility policy has deliberately been retained outside the generic resolver.
4. Review affected entry years/results before any bulk recalculation. Only the
   reviewed coverage may be described as verified; source control retains old rules.

This task introduces no verified tax-history data, fallback, rule database, provenance
framework, or recalculation. The generic resolver is unchanged: greatest effective
year <= tax_year, with explicit failure before the first point or for an empty map.

## Category deduction parameters (Atomic Task 3)

`LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY` explicitly preserves the
old category percentages from compatibility year 1: n/a=100, multi-year equipment
33.333, auto=0, raum=100, bewirtung=70, hausratversicherung=50,
haftpflichtversicherung=50, festnetz=50. These are not verified legislative dates.

`get_deductible_percent(category_code, *, tax_year)` owns the existing category
fallback: absent category → Decimal('100'); present category → generic change-point
resolution. An empty explicit history or an uncovered year fails; it does not use
that fallback. The generic historical resolver is unchanged.

Both processor definitions pass their resolved tax_year. Pending-conversion
recalculation passes resolve_tax_year(row). Deductible gross still uses this run's
common amount × percentage, deductible VAT uses this run's VAT × percentage, with
the existing cent rounding. Neither reads stored stale Y. The writeoff helper
accepts tax_year solely to forward it to its existing percentage lookup: multi_year
special case, zero → none, non-100 → partial, otherwise immediate. Its algorithm
and multi-year behavior have not been versioned or changed.

Reviewed effective dates can later replace/narrow this compatibility coverage via
the same explicit review-and-migration strategy documented for VAT above. Retained
legacy coverage must stay visibly distinguished from verified history; no silent
fallback is added. No VAT, FX, tax-year policy, formulas, schema or persisted
provenance changed in this step. This section supersedes the earlier statement
that deduction constants have not yet migrated to histories.

## Independent category VAT classification history (Atomic Task 5)

Three separate static parameter histories now exist:
- `LEGACY_CATEGORY_VAT_CLASS_COMPATIBILITY_HISTORY`: category → VAT class.
- `LEGACY_VAT_COMPATIBILITY_HISTORY` / alias `VAT_RATE_HISTORY`: VAT class → rate.
- `LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY`: category → deduction %.

All current year-1 points are legacy compatibility baselines, not verified
legislative effective dates. No future production points were invented.

`get_vat_class(category_code, *, tax_year)` uses the existing generic resolver.
The domestic path in `get_vat_rate_percent` first resolves the category's class,
then independently resolves that class's percentage using the same tax_year.
The processor already supplies resolve_tax_year(payload), based on payment date;
invoice date is not used. Class changes and rate changes need not coincide.

A missing category still raises exactly `ValueError("Unknown category code: ...")`.
There is no default class. Present histories with no applicable point use the
existing HistoricalValueUnavailable failure. The non-domestic early return remains
Decimal('0') and bypasses both histories, including the unknown-category check.
No deduction/writeoff behavior, VAT formulas, percentages, FX or schema changed.

## Retained VAT-treatment behavior (Atomic Task 6)

`resolve_vat_treatment_legacy(*, category_code, tax_scope, tax_year)` retains the
current procedure unchanged: non-domestic → Decimal('0'); domestic → historical
category VAT class → historical rate for that class. It produces a percentage,
not a monetary VAT amount. Gross-to-VAT arithmetic remains outside this boundary.

`LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY = {1: resolve_vat_treatment_legacy}`
is the only production behavioral registration. Year 1 is compatibility coverage,
not verified German legislative history. `get_vat_rate_percent` selects the callable
with the existing generic `resolve_historical_value`, then invokes it with the three
explicit arguments. There is no second generic resolver, historical flag set, or
hypothetical production implementation.

Behavior history chooses WHAT PROCEDURE runs. Separate static histories supply
category→class, class→percentage and category→deductible-percentage data. The
non-domestic procedure bypasses both domestic static histories; it still goes
through behavioral selection first. All accepted payment years (1–9999) retain
identical outcomes. An out-of-domain year before behavioral coverage fails through
the generic resolver; there is no hidden compatibility fallback.

When a reviewed behavior changes, add a separately named implementation and a new
change point. Keep the old implementation in source and callable for its earlier
period; do not delete it because the later function is active. Distinguish verified
change dates from retained compatibility coverage explicitly. No changes to other
behavioral rules, parameter histories, formulas, FX or schema accompany this step.

## Retained deduction calculation (Atomic Task 8)

Static history resolves `category + tax_year → deductible_percent`. Separately,
`app.domain.deduction_calculation.calculate_deductions` selects the behavioral
callable using `resolve_historical_value` and the already-resolved tax year.
`LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY` registers only
`{1: calculate_deductions_legacy}`. Year 1 means legacy compatibility coverage,
not verified legislative history. Future reviewed implementations must retain
this function and explicitly add their effective change point.

The retained function accepts only `amount_common`, already-rounded `vat_amount`,
and `deductible_percent` (Decimals). It returns an immutable `DeductionResult`
with `deductible_amount` and `deductible_vat_amount`. Each is its monetary base
multiplied by the shared percentage, divided by 100, then quantized to 0.01 with
ROUND_HALF_UP. VAT is rounded upstream before this second rounding boundary.
`deductible_percent` still means the shared legacy expense AND VAT percentage.
No independent VAT-deduction percentage is introduced.

Both AccountingEntryProcessor implementations and pending-conversion
`ConversionService._recalculate_derived_fields` use this same dispatch and fresh
intermediate values. FX, tax-year derivation, percentage histories, VAT treatment,
invoice validation and write-off classification remain outside the function.
Non-domestic VAT remains zero; gross deduction still uses the category percentage.
Invoice existence adds no monetary deduction condition. Persistence and schema
remain unchanged.

## Canonical AP audit map (Atomic Task 9)

The active implementation is `app/engine/accounting_entry_processor.py`, not the
older class exported by `app.engine`. This section describes the current code order.

`EntryProcessingService.process_entry` loads X into AccountingEntryCreateSchema
(validation), prepares non-EUR conversion using LocalCurrencyConversion, then
calls the active processor. Inside `process` the sequence is:

1. `_validate_invoice_rules(payload)`.
2. `resolve_tax_year(payload)`.
3. Accept supplied conversion, otherwise `_convert_to_common_currency(payload)`.
4. `get_vat_rate_percent(category_code, tax_scope, tax_year=...)`.
5. `get_deductible_percent(category_code, tax_year=...)`.
6. `get_writeoff_method(category_code, tax_year=...)` (re-resolves percentage).
7. If common amount is absent, all three monetary VAT/deduction values are None.
   Otherwise `_calculate_vat_from_gross`, then `calculate_deductions`.
8. Assemble immutable ProcessedAccountingEntry, projecting tax_year to booking_year.
9. Service assigns only DERIVED_FIELDS to ORM, serializes Decimals as strings,
   flushes, builds read schema, commits. Failure rolls back per entry.

No calculation was reordered for this documentation. X/Y denotes authority;
Y can depend on freshly computed Y. Explicit Process Entry fails before processor
invocation when required FX is unavailable; ordinary processor calls can return
pending/null monetary results.

| Y field | X / intermediate dependencies | Producer | Historical boundary |
|---|---|---|---|
| booking_year | payment_date → tax_year | resolve_tax_year → process assembly | None: payment-date policy |
| currency_common | processor EUR constant | process assembly | None |
| amount_common | original amount/currency, payment_date, selected FX | _convert_to_common_currency or LocalCurrencyConversion.calculate supplied by EntryProcessingService | External historical rates, not rule histories |
| exchange_rate | currency pair, payment_date | LocalCurrencyConversion.lookup → service conversion result | latest-on-or-before; MNB HUF / ECB USD |
| exchange_rate_date | actual selected observation date | same conversion result | Same lookup; pending processor placeholder is payment_date, not an observation |
| vat_rate_percent | category_code, tax_scope, tax_year | get_vat_rate_percent | VAT behavior → category class → class rate histories |
| vat_amount | fresh amount_common, vat_rate_percent | _calculate_vat_from_gross | None; zero shortcut or gross × (1 − 1/(1 + rate/100)), then cents |
| deductible_percent | category_code, tax_year | get_deductible_percent | Category percentage history; absent category → 100 |
| deductible_amount | fresh common gross, deductible_percent | calculate_deductions → calculate_deductions_legacy | Deduction behavior history |
| deductible_vat_amount | freshly rounded VAT, deductible_percent | same deduction function | Same history, same shared percentage |
| writeoff_method | category_code, re-resolved deductible percentage | get_writeoff_method | Label algorithm unversioned; underlying percentage historical |
| conversion_status | same currency / supplied FX / unresolved FX | _convert_to_common_currency or service conversion result | None |
| conversion_note | currency pair, date, resolution/failure | same conversion result | None |

All histories use `resolve_historical_value` (latest effective year <= tax_year):

| Mechanism | History constant | Entry point | 2024/2026 domestic bewirtung |
|---|---|---|---|
| Category → VAT class | LEGACY_CATEGORY_VAT_CLASS_COMPATIBILITY_HISTORY | get_vat_class | standard |
| Class → VAT rate | LEGACY_VAT_COMPATIBILITY_HISTORY (VAT_RATE_HISTORY alias) | resolve_vat_treatment_legacy | Decimal('19') |
| Category → percentage | LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY | get_deductible_percent | Decimal('70') |
| VAT treatment | LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY | get_vat_rate_percent | resolve_vat_treatment_legacy |
| Deductions | LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY | calculate_deductions | calculate_deductions_legacy |

All registrations are year-1 compatibility, not verified legal effective dates.
Non-domestic legacy treatment bypasses class/rate histories and yields zero.
Other categories retain their own classifications/percentages.

Intentionally unversioned: payment-date tax-year policy; EUR common currency;
MNB/ECB source selection and latest-on-or-before payment-date lookup; division by
stored EUR/quote rate; missing-rate handling; gross-to-VAT arithmetic; Decimal
context and cent ROUND_HALF_UP rounding; write-off label branch order (multi-year,
zero, partial, immediate); invoice metadata validation. `has_invoice` does not
change monetary formulas. No depreciation schedule is implemented by the label.

Remaining duplication (left untouched): all three processing paths retain the
same VAT formula/zero shortcut and cent helper; active/older processors duplicate
invoice validation and assembly. The old processor rejects foreign currencies;
the active processor accepts supplied conversions or returns pending; conversion
maintenance resolves stored FX and only recalculates a subset of Y (not booking
 year/writeoff). Same-currency conversion maintenance copies the original amount,
whereas the processors round to cents. These existing differences are not a new
historical rule. All three share VAT treatment, percentage and deduction behavior
boundaries; no remaining inline deduction formula contradicts those boundaries.

### Optional developer diagnostic

`app.engine.processing_audit.process_with_trace(payload, conversion=...)` returns
`(ProcessedAccountingEntry, ProcessingTrace)` without database or API changes.
It runs the normal processor once, then resolves current rule names for inspection.
It is NOT persisted execution provenance and cannot explain which earlier rules
produced an old stored row. Use a stable rule configuration during the call.

The trace includes tax_year, treatment function name, legacy domestic VAT class,
VAT rate, percentage, executed deduction function name (None if skipped), and
conversion_path. An unknown future treatment's internal class lookup is not
inferred. Supplied FX is labelled `supplied_conversion`, not guessed to be ECB/MNB:
CurrencyConversionResult carries no source field. Actual source/date details remain
in the conversion note/date; the service's authoritative source selection is
LocalCurrencyConversion.sources. No callable objects are exposed. Tests exercise
current results, skipped branches, artificial year dispatch and fresh dependencies.
