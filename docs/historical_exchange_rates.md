# EUR-based historical exchange rates

All observations use **1 EUR = X quote-currency units**. Rates enter the application
as `Decimal` and remain exact strings in SQLite. Float rates, nonpositive/nonfinite
rates, reversed pairs, EUR/EUR, and units other than one are rejected.

## Original EUR/HUF path

The manual entry point was and remains
`MnbExchangeRateImportService.import_eur_huf_rates(start_date=..., end_date=...)`.
It originally combined `_request_exchange_rates()`, `_parse_exchange_rates()`, and
per-observation persistence. The network operation is Zeep
`client.service.GetExchangeRates(startDate=..., endDate=..., currencyNames="EUR")`
using the existing MNB WSDL `http://www.mnb.hu/arfolyamok.asmx?WSDL`.

MNB's response quotes the requested base currency in HUF. Its `curr="USD"` is
therefore USD/HUF, **not EUR/USD**. This adapter only requests/parses EUR/HUF.
It handles raw/escaped XML and `GetExchangeRatesResult` wrappers, converts comma
decimal separators using Decimal, and retains actual published observation dates.
No missing weekend/holiday/day rows are generated.

`MnbExchangeRateSyncService.synchronize()` remains the startup entry point called
by `main.synchronize_mnb_rates_on_startup()` after `init_db()`. Its interval starts
at `config.MNB_EXCHANGE_RATE_START_DATE` and ends today. There is no newly added
scheduler. `scripts/import_mnb_rates.py` retains its manual CLI and yearly chunks.

## Current architecture

```text
MnbExchangeRateSyncService (HUF, configured window)
    → HistoricalExchangeRateService (history planning and import)
        → MnbHistoricalRateProvider (SOAP and MNB XML; no database)
        → validated HistoricalRateObservation objects
        → ExchangeRateService → ExchangeRateRepository → eur_huf_exchange_rates
```

The generic service's public entry points are:

```python
history = HistoricalExchangeRateService(db)
history.synchronize(
    quote_currency="HUF", provider=MnbHistoricalRateProvider(),
    start_date=config.MNB_EXCHANGE_RATE_START_DATE, end_date=today,
)
history.import_rates(
    quote_currency=quote_currency, provider=provider,
    start_date=start_date, end_date=end_date,
)
```

`import_rates` imports exactly the requested interval and returns an upsert count.
`synchronize` inspects this quote/source's bounds, plans backfill/inclusive forward
refresh ranges, applies provider request chunking, and returns `HistoricalSyncResult`.
It does not audit every interior historical gap, matching the established strategy.
The start date is explicit in the generic service; there is no generic HUF or MNB
configuration default.

The provider contract in `app/domain/historical_rates.py` requires:

- `source`: an explicit provider identifier; no default or source fallback.
- `quote_currencies`: advertised supported quote codes.
- `history_policy`: lower-bound publication tolerance and request chunking policy.
- `fetch_rates(quote_currency=..., start_date=..., end_date=...)`: observations,
  without persistence or conversion side effects.

Each observation identifies its date, EUR base, quote currency, Decimal rate,
unit `"1"`, and source. The core normalizes codes to uppercase, checks capability,
orientation/source/date range and numeric validity, and validates the complete
response before persisting any of that response. Providers must normalize their
own native pair orientations/units before returning observations; the core never
inverts or computes cross-rates automatically.

MNB's `HistoryPolicy` retains a ten-calendar-day lower-bound tolerance and yearly
request chunks. Other providers explicitly choose their own publication/request
policy. Inclusive latest-observation refresh and latest-on-or-before lookup remain
unchanged; the latter has no maximum-age cap.

`MnbExchangeRateImportService` inherits the provider's fetch/parser methods so its
existing convenience import path uses the same shared persistence. The legacy
`import_rates(currency=...)` argument means the MNB-requested **base**, and only
EUR is accepted. The startup wrapper now accepts `provider_factory` for testing
instead of a DB-writing `importer_factory`.

## Persistence and migration

The existing table already had `rate_date`, `base_currency`, `quote_currency`,
`rate`, `unit`, `source`, IDs, and timestamps. No currency backfill or row recreation
is needed: existing EUR/HUF observations already explicitly identify HUF.

`init_db()` now adds unique index `uq_exchange_rate_date_pair` on
`(rate_date, base_currency, quote_currency)`. The old source-inclusive uniqueness
constraint can remain alongside it. This additive, transactional, repeatable
upgrade preserves IDs, amounts, dates, source, and timestamps. If an old database
contains multiple providers for one date/pair, initialization stops with a conflict
message; it does not choose, overwrite, or discard an observation.

Same-source upserts use SQLite's atomic ON CONFLICT update, preserving ID and
creation time. Identical observations leave the update timestamp alone. Another
source for an existing date/pair raises `ExchangeRateSourceConflict`. Authoritative
provider replacement is a future explicit policy, not a silent import side effect.
Different quotes on the same date have independent identities.

Repository and service writes/lookups require explicit `base_currency`,
`quote_currency`, and `source`. Supported lookup methods are `get_exact_rate`,
`get_latest_rate_on_or_before`, `get_rate_date_bounds`, and filtered `list_rates`.
The repository also exposes exact/latest ORM-row methods; the service's existing
latest lookup continues returning an ORM row. No missing source is guessed as MNB.

Per-observation commits are preserved: a later failed request does not roll back
already completed observations. Failed writes roll back their active transaction.
Fetch/parse/observation errors raise `ExchangeRateProviderError`; database errors
and provider ownership conflicts remain distinct. The MNB startup wrapper retains
the `MnbExchangeRateProviderError` alias so its nonfatal provider-error handling
continues working.

## EUR/USD provider

`EcbHistoricalRateProvider` implements the supplied official ECB EUR/USD contract
with source `ECB`, USD capability, and normalized observations. It can be passed
to the same service with `quote_currency="USD"`. Production startup now uses
`EcbExchangeRateSyncService` with dedicated `eur_usd_exchange_rates` storage;
see [ECB startup synchronization](ecb_startup_synchronization.md).
See [the isolated ECB provider](ecb_exchange_rate_provider.md) for its public
interface and explicit invocation. Tests use mocked HTTP and deterministic fixtures.

AP/AR amount normalization still explicitly uses the existing MNB HUF→EUR policy.
This refactor does not select an authoritative USD source for tax conversion or
change that accounting policy. MNB transport remains synchronous with its existing
Zeep settings and no newly introduced timeout policy.

Tests cover MNB SOAP/parser integration with mocked responses; history boundaries;
USD/HUF isolation; exact Decimal precision; explicit source/currency lookup;
repeated and concurrent upserts; invalid observations; provider failures; and
preserving legacy rows or rejecting conflicting legacy providers during upgrade.

## EUR/HUF table name

The former `exchange_rates` table is now `eur_huf_exchange_rates`.
`init_db()` first runs `rename_legacy_exchange_rate_table()` before `create_all()`.
The transactional SQLite `ALTER TABLE ... RENAME TO ...` preserves all rows,
IDs, exact rate strings, timestamps and indexes. It is a no-op for new databases
or databases already renamed. If both names exist, initialization stops rather
than guessing which table to keep. EUR/USD storage is unchanged.
