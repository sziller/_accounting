"""MNB SOAP adapter for EUR/HUF only; fetching/parsing has no DB side effects."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import html
import re
import xml.etree.ElementTree as ET

from zeep import Client, Settings
from zeep.exceptions import Error as ZeepError

from app.domain.historical_rates import HistoricalRateObservation, HistoryPolicy, currency_code

MNB_WSDL_URL = "http://www.mnb.hu/arfolyamok.asmx?WSDL"
LOWER_BOUNDARY_TOLERANCE_DAYS = 10


@dataclass(frozen=True)
class ImportedMnbRate(HistoricalRateObservation):
    source: str = "MNB"


class MnbHistoricalRateProvider:
    """MNB quotes one EUR in HUF; requesting USD from MNB would mean USD/HUF.

    Preserve observed publication days, including gaps on weekends/holidays.
    Lower-bound tolerance and yearly request limits are provider policy.
    """
    source = "MNB"
    quote_currencies = frozenset({"HUF"})
    history_policy = HistoryPolicy(LOWER_BOUNDARY_TOLERANCE_DAYS, chunk_by_year=True)

    def fetch_rates(self, *, quote_currency: str, start_date: date,
                    end_date: date) -> list[ImportedMnbRate]:
        if currency_code(quote_currency) != "HUF":
            raise ValueError("MNB history adapter only supports EUR/HUF")
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        response = self._request_exchange_rates(start_date=start_date, end_date=end_date, currency="EUR")
        return self._parse_exchange_rates(soap_response=response, currency="EUR")

    def _request_exchange_rates(self, *, start_date: date, end_date: date, currency: str) -> str:
        """Call the existing Zeep GetExchangeRates SOAP operation (synchronous)."""
        if currency_code(currency) != "EUR":
            raise ValueError("MNB adapter must request EUR observations quoted in HUF")
        try:
            client = Client(wsdl=MNB_WSDL_URL, settings=Settings(force_https=False, strict=False))
            result = client.service.GetExchangeRates(
                startDate=start_date.isoformat(), endDate=end_date.isoformat(), currencyNames="EUR")
        except ZeepError as exc:
            raise ConnectionError(f"Failed to fetch MNB exchange rates via SOAP/WSDL: {exc}") from exc
        except Exception as exc:
            raise ConnectionError(f"Unexpected MNB exchange-rate fetch error: {exc}") from exc
        if isinstance(result, str):
            return result
        value = getattr(result, "GetExchangeRatesResult", None)
        if isinstance(value, str):
            return value
        raise ValueError(f"Unexpected MNB GetExchangeRates result type: {type(result)!r}")

    def _parse_exchange_rates(self, *, soap_response: str, currency: str) -> list[ImportedMnbRate]:
        if currency_code(currency) != "EUR":
            raise ValueError("MNB adapter only parses EUR observations quoted in HUF")
        xml_text = soap_response.strip()
        if not xml_text:
            return []
        if "GetExchangeRatesResult" in xml_text:
            xml_text = self._extract_get_exchange_rates_result(xml_text)
        xml_text = html.unescape(xml_text).strip()
        root = ET.fromstring(xml_text)
        rates = []
        for day in root.findall(".//Day"):
            date_text = day.attrib.get("date")
            if not date_text:
                continue
            rate_date = date.fromisoformat(date_text)
            for node in day.findall("Rate"):
                if node.attrib.get("curr", "").strip().upper() != "EUR":
                    continue
                unit = node.attrib.get("unit", "1").strip() or "1"
                rate_text = (node.text or "").strip()
                if not rate_text:
                    continue
                rates.append(ImportedMnbRate(rate_date, "EUR", "HUF", self._parse_mnb_decimal(rate_text), unit))
        return rates

    @staticmethod
    def _extract_get_exchange_rates_result(soap_response: str) -> str:
        try:
            root = ET.fromstring(soap_response)
        except ET.ParseError as exc:
            raise ValueError("MNB SOAP response is not valid XML") from exc
        for node in root.iter():
            if node.tag.endswith("GetExchangeRatesResult"):
                return node.text or ""
        match = re.search(r"<GetExchangeRatesResult>(.*?)</GetExchangeRatesResult>", soap_response, flags=re.DOTALL)
        if match:
            return match.group(1)
        raise ValueError("Could not find GetExchangeRatesResult in MNB SOAP response")

    @staticmethod
    def _parse_mnb_decimal(value: str) -> Decimal:
        normalized = value.strip().replace(" ", "").replace(",", ".")
        try:
            return Decimal(normalized)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid MNB decimal rate: {value!r}") from exc
