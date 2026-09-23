# Pending currency conversions

Both AP and AR buttons read `Process pending currency conversions`.
AP: `accounting_entries.js:reprocessPendingConversions()` posts to
`/acct/v0/conversions/reprocess-pending`; the router calls
`ConversionService.reprocess_pending()` / `_try_resolve_entry()` and commits
accounting entries, recalculating their existing derived tax fields.
AR: the `ar_invoice_import.js` normalization handler posts to
`/acct/v0/outgoing-invoices/normalize-pending`; the receivables router calls
`ReceivablesService.normalize_pending_invoices()` and updates `amount_common`
inside its existing transaction. Counts and per-invoice messages are unchanged.

`LocalCurrencyConversion` shares pair dispatch, local lookup and division:
- HUF/EUR: `ExchangeRateService`, source MNB, base EUR, quote HUF.
- USD/EUR: `EurUsdExchangeRateService`, source ECB, base EUR, quote USD.

Both choose the latest observation on or before the conversion date: AP uses
payment_date, AR uses invoice_date. No network calls, alternate source, future
rate or manufactured observation is used. EUR = original amount / stored rate;
Decimal values are rounded to cents using ROUND_HALF_UP. Existing context policy
is retained (AP ambient Decimal context; AR precision 64).

Identical currencies retain the original exact amount without a rate query.
AP keeps its existing statuses: not_required for identical currencies, resolved
for successful FX, pending for absent history, failed for unsupported pairs.
AR reports converted/pending; its null amount_common selects pending records.
Already converted records are not reprocessed. AP stores the rate and actual
observation date; AR includes the source rate/date in the processing message.
