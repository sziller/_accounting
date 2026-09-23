# Outgoing invoice authority contract

AP remains unchanged: authoritative `AccountingEntryORM.payment_date` selects
`resolve_tax_year(entry) → payment_date.year`.

OutgoingInvoice previously had no receipt date. Its invoice_date is issue date;
due_date is a deadline, not receipt evidence. IncomingPayment.payment_date is a
required date on a separate payment record. Allocations expose those dates but
many payments may settle one invoice; none is automatically promoted to the
invoice's date. A single invoice-level manual date cannot describe installment
cash flows. Future reconciliation/reporting must decide that policy explicitly.

`outgoing_invoices.payment_date` is now nullable SQL Date / Python date and an
optional create/read/PATCH field. It records actual receipt as a manual X fact.
Omission on PATCH preserves it; explicit null clears it. No automatic date,
parser inference, allocation synchronization, or paid-status calculation uses it.
PDF imports leave it null. It does not assert allocation-based full settlement.

## Complete outgoing-invoice field authority

| Field(s) | Authority | Source / producer |
|---|---|---|
| invoice_number | X | Printed invoice, parser or manual editor |
| invoice_date | X | Printed issue date, parser or manual editor |
| due_date | X, nullable | Explicit deadline/manual input; current parser leaves null |
| payment_date | X, nullable | Manually entered receipt fact; never inferred |
| customer_name, customer_reference | X | Customer identity/reference, parser where supported or manual input |
| net_amount, vat_amount | X, nullable | Printed totals/manual input; no AP VAT reconstruction |
| gross_amount, amount_original | X aliases | Printed gross; schemas enforce equality |
| currency, currency_original | X aliases | Printed original currency; schemas enforce equality |
| currency_common | X configuration/input | Config default AR_COMMON_CURRENCY, editable target currency; not processor-owned today |
| remarks | X | Invoice notes/payment terms where parser supplies them, or manual input |
| pdf_filename, pdf_sha256 | X documentary metadata | Exact basename and original-byte hash from importer; currently editable |
| amount_common | Y, nullable, persisted | Explicit normalize_pending_invoices action from original amount and local FX |
| paid_amount | Y, response-only | Decimal sum of allocations |
| outstanding_amount | Y, response-only | gross_amount minus allocation sum |
| payment_status | Y, response-only | Balance and due date/current date, not manual payment_date |
| allocations | Related facts, response projection | Junction records/payment dates; changed through allocation API, not invoice editor |
| id | System | Generated identity |
| created_at, updated_at | System | Existing UTC timestamp mechanism |

Allocation amounts and incoming payment facts are authoritative inputs in separate
tables, not outgoing-invoice calculated columns. No service_date, booking_year,
exchange_rate, exchange_rate_date, stored conversion_status or conversion_note
exists on outgoing_invoices. Conversion reports contain transient status/message;
these are not new persisted fields. No fields were invented for those concepts.

## Future date-policy boundary

For the intended IST workflow, a future centralized `resolve_ar_tax_year` should
resolve payment_date.year when present; absent date means unresolved (unknown or
not yet received), with no invoice-date fallback. No AR tax-year resolver or tax
processing is introduced now. A future invoice-date/SOLL policy belongs at that
single boundary, not scattered through calculations.

Existing AR FX normalization continues to use invoice_date and changes only
amount_common. Changing payment_date neither clears nor recalculates amount_common.
This is existing FX behavior, not an implemented AR tax-year policy.

## Upgrade and editor

Base.metadata.create_all handles new databases. `upgrade_ar_payment_date` runs
at init_db after existing upgrades; BEGIN IMMEDIATE serializes inspection and
ALTER TABLE ADD COLUMN payment_date DATE. It is idempotent, performs no backfill,
and preserves all existing rows with null receipt dates.

The locked AR editor exposes Payment Received Date through the existing
unlock/save/cancel flow. Date input is optional and blank saves as null.
No AP code, printed monetary values, VAT rules, allocations or matching changed.

## Explicit AR processing (Atomic AR Task 2)

This section supersedes the earlier statement that no AR resolver/processor exists.
`app.domain.ar_tax_year.resolve_ar_tax_year(invoice) -> int | None` centralizes
IST policy: payment_date.year if known, otherwise None. Invoice date is never a
tax-year fallback. A future SOLL policy belongs at this boundary. Unresolved tax
year does not block normalization or imply an allocation-derived unpaid status.

The X/Y classification above is unchanged. The only persisted accounting Y written
by processing is amount_common. System updated_at follows the existing ORM
mechanism; printed totals, currencies (including target currency_common), dates,
source references, allocations and incoming payments are never assigned.

Call chain:
- POST /acct/v0/outgoing-invoices/{id}/process
- ReceivablesRouter.process_entry → ReceivablesService.process_ar_entry
- _write (BEGIN IMMEDIATE) → load invoice → _calculate_common_amount
- Same currency: exact Decimal original amount, preserving existing precision.
- HUF/USD → LocalCurrencyConversion.lookup at invoice_date (latest on/before,
  explicit MNB/ECB) → divide original by stored EUR/quote rate, precision 64,
  cent ROUND_HALF_UP; existing validity/range guards remain unchanged.
- Assign amount_common, flush, refresh, build normal invoice response and trace,
  commit. Errors roll back before returning failed. Missing FX keeps old Y intact.

The existing normalize-pending endpoint remains compatible and shares the same
_calculate_common_amount helper, so there is no second conversion algorithm.
Explicit processing deliberately ignores whether Y was already populated.

POST /acct/v0/outgoing-invoices/process-entries enumerates all invoice IDs in
invoice_date/id order, ends that read transaction, then calls process_ar_entry
for each. Per-invoice commits/rollbacks isolate failures. Results contain
processed/failed counts and per-invoice status/message. A failed item never stops
valid subsequent items. The operation is not one all-or-nothing batch transaction.

Responses optionally include a non-persisted trace: tax_year (null if unresolved),
fx_date_policy='invoice_date', fx_lookup_date, fx_source, amount_common. This is
current processing context, not stored provenance. Actual observation dates are
reported in the existing FX message; no new rate/date DB columns were introduced.
Decimal response schemas preserve amounts as JSON strings.

The AR editor's top Process Entry button operates only on selection and refreshes
that same invoice on success. Bottom Process Entries operates on the full AR
population and refreshes the table/editor. Both are disabled during editing/busy
states, preserving unsaved drafts. No automatic processing runs during save/import.
No AR VAT/jurisdiction rules, AP modifications, schema changes, annual reporting,
or taxation-mode switch are introduced.

## Recognition events (Atomic AR Task 4)

Three separate concepts now apply:
- Invoice facts describe what was invoiced.
- Payment/allocation facts describe allocated receipt amounts and their dates.
- Recognition events are deterministic, non-persisted interpretations of those
  facts for future reporting; no report or annual aggregation is implemented.

`resolve_ar_recognition_events(invoice_facts, allocation_facts)` in
`app/domain/ar_recognition.py` returns a tuple of frozen `ArRecognitionEvent`
objects. Each contains invoice_id, recognition_date, tax_year, exact Decimal
amount_original, currency_original, source, optional payment_id/allocation_id.
Inputs are immutable fact objects, not ORM objects. No database work occurs in
the domain resolver. There are no recognized-common/net/VAT fields.

Precedence is exclusive:
1. Any allocations: one event per allocation, using its amount and the CURRENT
   parent IncomingPayment.payment_date. Tax year is that date's year. Source is
   `allocation`. Manual invoice payment_date is ignored, not cleared or synced.
2. No allocations plus manual invoice payment_date: one event for full printed
   gross in original currency. Source is `manual_invoice_payment`; payment and
   allocation IDs are None. Setting this manual date explicitly asserts full
   receipt without detailed records for recognition purposes.
3. Neither: empty tuple; no zero event or invoice-date fallback.

Partial allocations suppress the entire manual fallback, including any imagined
remaining receipt. Deleting the last allocation can therefore reactivate an
existing manual fallback; the field is deliberately not synchronized. Changing a
parent payment date changes future event resolution, not a persisted event history.
Unallocated payments do not generate invoice events. Recognition does not change
allocation-based paid_amount/payment_status: manual fallback is a separate contract.

Events sort by recognition_date, payment_id, allocation_id. Input/SQL order is
irrelevant; distinct allocations remain distinct even for the same payment.
The read-only `ArRecognitionService.resolve_invoice_events(invoice_id)` loads
all relevant scalar facts in one outer-joined query, disables autoflush, then
calls the pure resolver. It neither commits nor writes, uses no cached ORM field
values and rejects missing invoices or invalid parent-payment links explicitly.
No HTTP endpoint or frontend behavior is added.

`resolve_ar_tax_year` remains an invoice-level manual-context resolver, used only
for the manual fallback here; the existing processing trace is not a general
recognition-year statement. Detailed receipt years come from each payment date.
This is the current IST-oriented application contract, NOT verified historical
legislation. No VAT/net split, cent allocation, residual policy, or new FX valuation
is implied. Existing invoice_date-based normalization remains unchanged.

## Proportional recognition amounts (Atomic AR Task 5)

Events now also carry nullable net_amount_original, vat_amount_original and
amount_common. This supersedes the earlier monetary-scope restriction. No new
persisted values or recognition UI are introduced.

Timing still comes from parent payment_date; original gross is the exact allocated
amount. Net/VAT are shares of printed invoice totals, never rate-derived.
Common amount is a share of the EXISTING processed invoice amount_common. Missing
components remain None independently, including missing normalization. No FX
lookup, invoice processing, or inference of absent printed totals occurs.

`allocate_invoice_amounts(gross_total=..., net_total=..., vat_total=...,
common_total=..., recognized_gross_amounts=...)` returns immutable per-event shares.
The resolver sorts first by receipt date/payment ID/allocation ID, then calls this
pure helper. Completion uses the exact Decimal sum of allocated gross, not status,
manual date or paid_amount. Overallocated input is rejected rather than projected.

Precision: existing source schemas permit six decimal places and preserve textual
Decimal values. AR FX uses precision 64, cents and ROUND_HALF_UP; same-currency
normalization preserves original precision. Ordinary proportional component shares
use precision 64 and quantize to Decimal('0.01') with ROUND_HALF_UP, computing
component_total * allocated_gross / invoice_gross without float or rounded ratios.
Gross is never quantized. Manual full receipts and a single full allocation copy
invoice components exactly, including sub-cent precision.

For complete settlement, all but the final sorted event use ordinary rounding.
The final event receives each existing component total minus previous shares,
without another quantization. Thus sums reproduce stored totals exactly; for a
sub-cent stored total the final residual can retain sub-cent precision. None stays
None. For incomplete settlement every event is independently proportional/rounded;
no residual is forced and no unpaid event is fabricated.

Adding a later-ordered completing payment leaves earlier shares unchanged. A
backdated payment or date/ID ordering change can change which event is final and
therefore which absorbs the residual. Deletion also recomputes from current facts;
deleting the last allocation reactivates exact manual full values if its date
exists. These are projections, not frozen recognition history.

Independent rounding may make an individual event's net+VAT differ from its gross
by a cent. Tiny final receipts/many rounded shares can also yield a negative final
component residual. This is a consequence of the specified final-event rule;
no clamping, redistribution or extra component-balancing policy is introduced.

Example: printed gross/net/VAT/common 1190/1000/190/1190, with receipts 595 in
2026 and 595 in 2027, yields separate events each with gross/net/VAT/common
595/500/95/595. This is application accounting behavior, not newly researched or
historically verified tax legislation. Invoice/payment/allocation persistence,
allocation-based balance/status, AP, and invoice-date FX behavior remain unchanged.

## Cumulative precision-aware allocation (Atomic AR Task 5b)

This replaces Task 5's independent rounding/final residual algorithm and its
negative-final-component limitation. The event model and persistence are unchanged.

For each non-null component T (net, VAT, common), choose a fixed quantum q:
cent-exact values use 0.01; otherwise strip irrelevant trailing coefficient zeros
and use the smallest fractional scale that represents T exactly. Thus 19.000 →
0.01, 0.006 → 0.001, 1.234500 → 0.0001. Zero uses cents. Quantum selection does
not normalize under the active Decimal context and does not round the source.

For cumulative ordered gross C_i and invoice gross G:
- target_0 = 0
- target_i = quantize(T * C_i / G, q, ROUND_HALF_UP)
- when C_i == G, target_i is exactly stored T instead
- event component_i = target_i - target_(i-1)

Arithmetic retains AR precision 64. Gross amounts are untouched. Since T is on
its component's rounding grid, non-negative increasing entitlements have
non-decreasing targets no greater than T. Increments are non-negative without
clipping. Prefix sums telescope to their cumulative targets; full settlement sums
exactly to T. Partial settlement is not forced to T (rounding may reach T early).
For T=0.006 and receipts 99.99 + 0.01 of G=100, targets are 0.006 and 0.006,
so components are 0.006 and 0.000, not a negative final value.

Manual full payment and single full allocation still copy exact stored values.
Null components remain null. Foreign common values still come only from the
invoice's existing normalization, now apportioned at their appropriate precision.
No FX lookup or new valuation occurs.

Appending a later-ordered payment preserves every prior prefix target/share.
Backdated insertion or editing can legitimately change subsequent shares. Individual
net+VAT need not equal event gross: for G=0.02, net=VAT=0.01, and two gross receipts
of 0.01, the first net and VAT are each 0.01 and the second each zero. Aggregate
net/VAT totals reconcile; no per-event balancing correction is imposed. Ordinary
1190/1000/190 with two 595 receipts still gives 595/500/95 per event.

This is application allocation behavior, not researched historical legislation.

## Recognition read API and selected-invoice display

GET /acct/v0/outgoing-invoices/{id}/recognition-events returns a bare ordered
array from ArRecognitionService.resolve_invoice_events. Its response schema
serializes Decimal amounts as strings and preserves null components. It adds no
fields, writes, valuation, or recognition policy. Missing invoice returns 404.

The selected invoice's Recognition section follows Payments / Allocations and
renders one row per backend event, without sorting or aggregation. Original
components show event.currency_original; common values show the selected invoice's
currency_common. Decimal strings are displayed verbatim (no float conversion or
cent truncation). Manual fallback is labelled Manual full-payment date with an
explanation; allocations are labelled Payment allocation with IDs in a tooltip.
Only a successful empty array displays No receipt recognized yet. Loading/errors
are local to recognition; stale requests cannot replace the current selection.
Invoice/payment saves, allocation changes, processing and invoice refresh reload
recognition via the existing selection/read-only refresh paths. Invoice drafts
are preserved. This UI does not edit events or infer dates/amounts.
