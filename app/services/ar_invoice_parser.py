"""Deterministic parser for the observed one-page Honorarrechnung DE/HU and DE/EN layouts."""
import re
from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from app.schemas.receivables_schema import OutgoingInvoiceCreateSchema


class ArInvoiceParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


MONTHS = dict(zip(
    ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"),
    range(1, 13),
))
AMOUNT = r"(?:[0-9]{1,3}(?: [0-9]{3})+|[0-9]+)(?:\.[0-9]{1,6})?"
# Only the legacy DE/HU aggregate-label variant uses dot-grouped integer HUF.
LEGACY_HU_NET = "Nettohonorar gesammt – nettó összeg"
LEGACY_HU_GROSS = "(siehe Vermerk) – bruttó: (lásd megjegyzés)"
LEGACY_HUF_AMOUNT = r"[1-9][0-9]{0,2}(?:\.[0-9]{3})+"
BARE_CONTACT = r"([^\W\d_]+(?:[-'][^\W\d_]+)*(?: [^\W\d_]+(?:[-'][^\W\d_]+)*)+) \1"


def _one(pattern, text, code, message):
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise ArInvoiceParseError(code, message)
    return matches[0]


def parse_ar_invoice_text(text: str) -> OutgoingInvoiceCreateSchema:
    """Interpret printed values only; do not infer VAT, due date, or corrected years."""
    if len([page for page in text.split("\f") if page.strip()]) != 1:
        raise ArInvoiceParseError("unsupported_layout", "Only the observed single-page invoice layouts are supported")
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    normalized = "\n".join(lines)
    number = _one(r"^Honorarrechnung Nr\.: ([0-9]{4})$", normalized,
                  "invoice_number_not_found", "Expected one four-digit Honorarrechnung number").group(1)
    if lines[0] != f"Honorarrechnung Nr.: {number}" or lines[-1] != number:
        raise ArInvoiceParseError("unsupported_layout", "Invoice header and footer must agree")
    match = re.fullmatch(r"([0-9]{1,2})\. ([A-Za-zä]+) ([0-9]{4})", lines[1])
    try:
        if match is None:
            raise ValueError()
        day, month, year = match.groups()
        invoice_date = date(int(year), MONTHS[month], int(day))
    except (ValueError, KeyError):
        raise ArInvoiceParseError("invoice_date_not_found", "Expected a valid German date immediately below the invoice number") from None

    title = _one(r"^Honorarrechnung (Számla|Invoice)$", normalized,
                 "unsupported_layout", "Expected the bilingual invoice title")
    issuer_end = _one(r"^Ust-IdNr\. - VATIN: [A-Z0-9]+$", normalized,
                      "unsupported_layout", "Issuer VATIN boundary not found")
    if issuer_end.end() >= title.start():
        raise ArInvoiceParseError("customer_not_found", "Recipient block not found after issuer")
    recipient = normalized[issuer_end.end():title.start()].strip().splitlines()
    if len(recipient) < 3 or not (recipient[0].startswith("Herr ")
                                  or re.fullmatch(BARE_CONTACT, recipient[0])):
        raise ArInvoiceParseError("customer_not_found", "Expected recipient contact and bilingual company line")
    # Both observed columns repeat the company verbatim on the same extracted line.
    company = re.fullmatch(r"(.+?) \1", recipient[1])
    if company is None or company.group(1) == lines[2]:
        raise ArInvoiceParseError("customer_not_found", "Customer company must repeat identically in both language columns")
    customer = company.group(1)

    # Recognize this template by its labels, never by the amount punctuation.
    # Seeing either legacy label commits to the complete legacy contract; a
    # missing companion or mixed English totals must not fall back to another one.
    legacy_hu = any(line.startswith((LEGACY_HU_NET, LEGACY_HU_GROSS)) for line in lines)
    if legacy_hu and (title.group(1) != "Számla" or any(
        line.startswith(("Nettohonorar – net amount:", "(siehe Vermerk) – gross amount:"))
        for line in lines
    )):
        raise ArInvoiceParseError("unsupported_layout", "Mixed or unsupported aggregate-total labels")

    def printed_total(label, code):
        match = _one(rf"^{label} ({AMOUNT}) ([A-Z]{{3}}|€)$", normalized,
                     code, f"Expected one unambiguous printed {code.replace('_not_found', '').replace('_', ' ')}")
        return Decimal(match.group(1).replace(" ", "")), "EUR" if match.group(2) == "€" else match.group(2)

    def legacy_total(label, code, *, gross=False):
        # Count label rows before validating values, so a malformed duplicate
        # cannot be ignored merely because its number fails the grammar.
        row = _one(rf"^{re.escape(label)}(?: ([^\n]*))?$", normalized, code,
                   f"Expected one unambiguous legacy {code.replace('_not_found', '')}")
        value = re.fullmatch(rf"({LEGACY_HUF_AMOUNT}) ([A-Z]{{3}})", row.group(1) or "")
        if value is None:
            raise ArInvoiceParseError("invalid_legacy_huf_amount", "Expected dot-grouped integer HUF amount in legacy DE/HU totals")
        if gross and not normalized[:row.start()].endswith("Bruttohonorar\n"):
            raise ArInvoiceParseError(code, "Expected Bruttohonorar immediately before the legacy gross total")
        return Decimal(value.group(1).replace(".", "")), value.group(2)

    if legacy_hu:
        net, currency = legacy_total(LEGACY_HU_NET, "net_amount_not_found")
        gross, gross_currency = legacy_total(LEGACY_HU_GROSS, "gross_amount_not_found", gross=True)
    else:
        net, currency = printed_total(r"Nettohonorar – net amount:", "net_amount_not_found")
        gross, gross_currency = printed_total(r"Bruttohonorar\n\(siehe Vermerk\) – gross amount: \(see Note\)", "gross_amount_not_found")
    if currency != gross_currency:
        raise ArInvoiceParseError("currency_conflict", "Printed net and gross currencies disagree")
    if legacy_hu and currency != "HUF":
        raise ArInvoiceParseError("currency_conflict", "Legacy DE/HU grouped totals must be denominated in HUF")
    if net != gross:
        raise ArInvoiceParseError("totals_inconsistent", "Printed net and gross differ in the supported no-VAT layouts")

    if title.group(1) == "Számla":
        note = "Vermerk: Reverse-Charge-Regelung Megjegyzés: Közösségi adózás – fordított ÁFA"
        terms = ("Bitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tage." if legacy_hu
                 else "Bitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tagen")
    else:
        note = "Vermerk: nicht umsatzsteuerpflichtig -\nLeistung an Kunden ausserhalb der EU"
        terms = "Bitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tage,"
    if normalized.count(note) != 1 or normalized.count(terms) != 1:
        raise ArInvoiceParseError("unsupported_layout", "Expected the observed VAT note and 14-day payment terms")
    if legacy_hu:
        _one(rf"^{re.escape(terms)}$", normalized, "unsupported_layout",
             "Expected exact legacy DE/HU 14-day payment terms")
    # No explicit due date, VAT total, or customer purchase-order reference occurs
    # in either observed template. Company/tax registration IDs are not order IDs.
    try:
        return OutgoingInvoiceCreateSchema(
            invoice_number=number, invoice_date=invoice_date, customer_name=customer,
            currency_original=currency, net_amount=net, amount_original=gross,
            due_date=None, vat_amount=None, customer_reference=None,
            remarks=note.replace("\n", " ") + "\n" + terms.replace("\n", " "),
        )
    except ValidationError:
        raise ArInvoiceParseError("invalid_invoice_values", "Printed invoice values do not satisfy receivables validation") from None
