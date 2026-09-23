# Isolated ECB EUR/USD provider

This adapter implements the supplied ECB source contract without external research.
It is used by the dedicated ECB startup service; see `ecb_startup_synchronization.md`.

## Public interface

```python
class EcbHistoricalRateProvider:
    source = "ECB"
    quote_currencies = frozenset({"USD"})
    history_policy = HistoryPolicy()  # no MNB tolerance or yearly chunking

    def __init__(self, *, timeout: float = 30.0): ...

    def fetch_rates(
        self, *, quote_currency: str, start_date: date, end_date: date
    ) -> list[HistoricalRateObservation]: ...
```

`timeout` is a positive finite socket timeout in seconds, exposed on the instance.
Construction performs no I/O. A fetch makes one bounded HTTP request, with no
range planning, persistence, retry, alternate provider, or calendar filling.
Invalid caller arguments raise `ValueError` before network access.

Response/transport failures raise:

```python
class EcbExchangeRateProviderError(RuntimeError):
    code: str
    def __init__(self, code: str, message: str): ...
```

The shared historical service wraps this as its existing
`ExchangeRateProviderError`, retaining the ECB exception as the cause.

## HTTP and response contract

Endpoint: `https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A`

Each GET sends `startPeriod=YYYY-MM-DD`, `endPeriod=YYYY-MM-DD`, and
`format=csvdata`, with `Accept: text/csv`. Python's standard-library `urllib`
provides the transport with normal TLS certificate verification and a default
30-second timeout for blocking socket operations. No dependency was added.

The response must have HTTP 200 and UTF-8 CSV (an initial BOM is accepted).
Parsing uses `csv.DictReader` and named headers, independent of column order.
All seven supplied-contract fields are required:

| Header | Interpretation / required value |
|---|---|
| `FREQ` | `D` |
| `CURRENCY` | `USD` |
| `CURRENCY_DENOM` | `EUR` |
| `EXR_TYPE` | `SP00` |
| `EXR_SUFFIX` | `A` |
| `TIME_PERIOD` | Valid `YYYY-MM-DD` date within the requested interval |
| `OBS_VALUE` | Positive finite decimal text |

Every row's identity is checked, not only the first row. Additional named columns
are allowed and ignored. Duplicate/blank headers, mismatched row widths, malformed
quoting, and duplicate observation dates fail explicitly.

Values pass directly from `OBS_VALUE` text to `Decimal`, preserving precision and
trailing decimal representation. No float or reciprocal calculation occurs. Each
returned observation has base `EUR`, quote `USD`, source `ECB`, and unit `"1"`:
**1 EUR = OBS_VALUE USD**.

## Empty data and errors

A valid CSV containing all required headers and no observation rows returns `[]`.
No absence of a particular calendar date is considered a failure, and no date is
manufactured, filled, or interpolated. The provider does not predict ECB working
days or TARGET holidays.

An empty/whitespace response body is an `empty_response` failure, not a valid empty
dataset. Non-200 HTTP responses (including 204/404) are reported as `http_error`;
the supplied contract does not authorize interpreting those as observation data.
Other diagnostic codes are `timeout`, `connection_failed`, `malformed_csv`,
`missing_fields`, `wrong_series`, `invalid_date`, `date_out_of_range`,
`duplicate_date`, and `invalid_rate`. Missing/non-numeric observation values fail
rather than being silently skipped. No response is repaired or replaced.

## Explicit invocation through the shared service

With an existing SQLAlchemy session `db` and initialized application schema:

```python
from datetime import date
from app.services.ecb_exchange_rate_provider import EcbHistoricalRateProvider
from app.services.historical_exchange_rate_service import HistoricalExchangeRateService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService

processed = HistoricalExchangeRateService(db, exchange_rates=EurUsdExchangeRateService(db)).import_rates(
    quote_currency="USD",
    provider=EcbHistoricalRateProvider(),
    start_date=date(2009, 5, 1),
    end_date=date(2009, 5, 31),
)
```

This is an explicit import: it performs network I/O and persists observations via
the dedicated USD service. Startup now uses `EcbExchangeRateSyncService` for
range planning and synchronization. The frontend and AP/AR conversion are unchanged.

## Verification

`tests/test_ecb_exchange_rate_provider.py` uses mocked HTTP and a **synthetic** CSV
fixture shaped according to the supplied contract. Fixture values are test values,
not a claim about actual May 2009 rates. Tests cover request construction, metadata,
precision, missing dates, malformed data and transport failures, plus real-parser
integration with temporary SQLite storage, HUF preservation, and idempotent upserts.
No live ECB request is made by tests, and no optional live-network runner was added.
