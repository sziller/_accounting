"""Isolated ECB EXR.D.USD.EUR.SP00.A adapter; no automatic synchronization.

Implements the supplied ECB API contract: 1 EUR = OBS_VALUE USD. Fetches exactly
one bounded CSV request and returns only published observations, without inversion,
calendar filling, persistence, or provider fallback.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from http.client import HTTPException
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.domain.historical_rates import (
    HistoricalRateObservation, HistoryPolicy, currency_code, validate_rate,
)

ECB_SERIES_KEY = "D.USD.EUR.SP00.A"
ECB_DATA_URL = f"https://data-api.ecb.europa.eu/service/data/EXR/{ECB_SERIES_KEY}"
_SERIES_DIMENSIONS = {
    "FREQ": "D", "CURRENCY": "USD", "CURRENCY_DENOM": "EUR",
    "EXR_TYPE": "SP00", "EXR_SUFFIX": "A",
}
_REQUIRED_FIELDS = frozenset((*_SERIES_DIMENSIONS, "TIME_PERIOD", "OBS_VALUE"))
_DECIMAL_TEXT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?\Z")
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


class EcbExchangeRateProviderError(RuntimeError):
    """Explicit ECB transport/response failure, with a diagnostic code."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class EcbHistoricalRateProvider:
    source = "ECB"
    quote_currencies = frozenset({"USD"})
    # Satisfy the shared contract without copying MNB's calendar/request policy.
    history_policy = HistoryPolicy()

    def __init__(self, *, timeout: float = 30.0):
        """Finite socket timeout in seconds. Construction makes no HTTP request."""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("ECB timeout must be a positive finite number of seconds")
        self.timeout = timeout

    def fetch_rates(self, *, quote_currency: str, start_date: date,
                    end_date: date) -> list[HistoricalRateObservation]:
        """Fetch USD observations for inclusive bounds; no DB or calendar effects.

        Invalid caller arguments raise ValueError before network access. Transport
        and response failures raise EcbExchangeRateProviderError. A valid CSV with
        required headers and no data rows returns []; a missing body is an error.
        """
        if currency_code(quote_currency) != "USD":
            raise ValueError("ECB history adapter only supports EUR/USD")
        if type(start_date) is not date or type(end_date) is not date or start_date > end_date:
            raise ValueError("ECB requires calendar dates with start_date <= end_date")
        query = urlencode({"startPeriod": start_date.isoformat(), "endPeriod": end_date.isoformat(), "format": "csvdata"})
        request = Request(f"{ECB_DATA_URL}?{query}", headers={"Accept": "text/csv"}, method="GET")
        try:
            # Standard urllib HTTPS handling retains certificate verification.
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise EcbExchangeRateProviderError("http_error", f"ECB returned HTTP {response.status}; expected CSV with HTTP 200")
                content = response.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise EcbExchangeRateProviderError("http_error", f"ECB returned HTTP {status}") from exc
        except TimeoutError as exc:
            raise EcbExchangeRateProviderError("timeout", "ECB request timed out") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise EcbExchangeRateProviderError("timeout", "ECB request timed out") from exc
            raise EcbExchangeRateProviderError("connection_failed", "Could not connect to the ECB data API") from exc
        except (OSError, HTTPException) as exc:
            raise EcbExchangeRateProviderError("connection_failed", "ECB connection failed while retrieving CSV") from exc
        try:
            csv_text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EcbExchangeRateProviderError("malformed_csv", "ECB CSV is not valid UTF-8") from exc
        return self._parse_csv(csv_text, start_date=start_date, end_date=end_date)

    @staticmethod
    def _parse_csv(csv_text: str, *, start_date: date, end_date: date) -> list[HistoricalRateObservation]:
        if not csv_text.strip():
            raise EcbExchangeRateProviderError("empty_response", "ECB returned an empty body instead of a CSV dataset")
        observations = []
        seen_dates = set()
        try:
            reader = csv.DictReader(StringIO(csv_text, newline=""), strict=True)
            headers = [field.strip() for field in (reader.fieldnames or [])]
            if len(headers) != len(set(headers)) or any(not field for field in headers):
                raise EcbExchangeRateProviderError("malformed_csv", "ECB CSV has duplicate or blank headers")
            missing = _REQUIRED_FIELDS.difference(headers)
            if missing:
                raise EcbExchangeRateProviderError("missing_fields", "ECB CSV missing required fields: " + ", ".join(sorted(missing)))
            reader.fieldnames = headers
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    raise EcbExchangeRateProviderError("malformed_csv", f"ECB CSV row {line} does not match its headers")
                for key, expected in _SERIES_DIMENSIONS.items():
                    if row[key].strip() != expected:
                        raise EcbExchangeRateProviderError("wrong_series", f"ECB CSV row {line}: expected {key}={expected}")
                raw_date = row["TIME_PERIOD"].strip()
                try:
                    if not _DATE_TEXT.fullmatch(raw_date):
                        raise ValueError()
                    observed_date = date.fromisoformat(raw_date)
                except ValueError as exc:
                    raise EcbExchangeRateProviderError("invalid_date", f"ECB CSV row {line}: invalid daily TIME_PERIOD") from exc
                if not start_date <= observed_date <= end_date:
                    raise EcbExchangeRateProviderError("date_out_of_range", f"ECB CSV row {line}: TIME_PERIOD outside requested bounds")
                if observed_date in seen_dates:
                    raise EcbExchangeRateProviderError("duplicate_date", f"ECB CSV repeats observation date {observed_date}")
                raw_rate = row["OBS_VALUE"].strip()
                try:
                    if not _DECIMAL_TEXT.fullmatch(raw_rate):
                        raise ValueError()
                    rate = Decimal(raw_rate)  # Direct textual parsing; never through float.
                    validate_rate(rate, "1")
                except (ValueError, InvalidOperation) as exc:
                    raise EcbExchangeRateProviderError("invalid_rate", f"ECB CSV row {line}: invalid OBS_VALUE") from exc
                observations.append(HistoricalRateObservation(observed_date, "EUR", "USD", rate, "1", "ECB"))
                seen_dates.add(observed_date)
        except csv.Error as exc:
            raise EcbExchangeRateProviderError("malformed_csv", "ECB response is not well-formed CSV") from exc
        return observations
