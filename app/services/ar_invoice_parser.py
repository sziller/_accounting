"""Deterministic parser for the observed one-page Honorarrechnung DE/HU and DE/EN layouts."""
import logging
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
logger = logging.getLogger(__name__)
ZERO_VAT_NOTES = {
    "Számla": ("Vermerk: Reverse-Charge-Regelung Megjegyzés: Közösségi adózás – fordított ÁFA",),
    "Invoice": (
        "Vermerk: nicht umsatzsteuerpflichtig -\nLeistung an Kunden ausserhalb der EU",
        "Vermerk: Reverse-Charge-Regelung Note: Reverse-Charge",
        "Vermerk: In Deutschland nicht steuerbare Leistung Note: Service not taxable in Germany",
    ),
}


def _zero_vat_note(body, language):
    """Recognize complete source notes, allowing ordinary extraction wrapping."""
    if len(re.findall(r"^Vermerk:", body, re.MULTILINE)) != 1:
        return None
    for note in ZERO_VAT_NOTES[language]:
        pattern = r"\s+".join(re.escape(word) for word in note.split())
        # The 2301/2304/2305 extraction splits this label as 'Not e:'.
        pattern = pattern.replace("Note:", r"Not[ \t]*e:")
        if re.search(rf"^{pattern}$", body, re.MULTILINE):
            return note
    return None


def _one(pattern, text, code, message):
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise ArInvoiceParseError(code, message)
    return matches[0]


def parse_ar_invoice_text(text: str) -> OutgoingInvoiceCreateSchema:
    """Use printed gross as net only for explicit zero-German-VAT treatments."""
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
    issuer_end = _one(r"^Ust-IdNr\. - (VATIN|Közösségi adószám): (DE[0-9]{9})$", normalized,
                      "unsupported_layout", "Issuer VATIN boundary not found")
    if issuer_end.end() >= title.start():
        raise ArInvoiceParseError("customer_not_found", "Recipient block not found after issuer")
    issuer = normalized[:issuer_end.start()].splitlines()
    # Both labels mark the end of the issuer header, not a VAT-like value in
    # the recipient or body. Permit only the observed intervening header rows.
    header_row = (r"(?:.+ Bankleitzahl - (?:Bank code|Bank kódja)|"
                  r"Konto-Nr\. - (?:Account number|Számlaszám)|IBAN - IBAN|"
                  r"SWIFT-BIC - SWIFT-BIC|Finanzamt - (?:Finance authority|Adóhatóság)|"
                  r"Steuernummer - (?:National id\.number|Helyi adószám)): .+")
    if (len(issuer) < 4 or sum(line.startswith("Ust-IdNr. -") for line in lines) != 1
            or not re.fullmatch(r"[^\W\d_]+(?:[ '-][^\W\d_]+)+", issuer[2])
            or not re.fullmatch(r".+ Bankverbindung - (?:Name of the Bank|Bank neve): .+", issuer[3])
            or any(not re.fullmatch(header_row, row) for row in issuer[4:])):
        raise ArInvoiceParseError("unsupported_layout", "Expected issuer identity and VATIN in the issuer header")
    recipient = normalized[issuer_end.end():title.start()].strip().splitlines()
    # The HU company-only variant has a repeated company followed by address/
    # tax rows; the EN non-EU reference variant contains only the company.
    hu_tax = bool(recipient
                  and sum(row.startswith("Ust-IdNr.:") for row in recipient) == 1
                  and re.fullmatch(r"Ust-IdNr\.: (HU[0-9]{8}) Köz\.adószám: \1", recipient[-1]))
    sparse = len(recipient) == 1 and title.group(1) == "Invoice"
    hu_company_only = (title.group(1) == "Számla" and hu_tax and len(recipient) >= 2
                       and re.fullmatch(r"(.+? Zrt\.) \1", recipient[0]) is not None)
    company_only = sparse or hu_company_only
    if sparse:
        following = normalized[title.end():].strip().splitlines()
        if (len(following) < 3 or lines[-2].casefold() != lines[2].casefold()
                or not re.fullmatch(r".+ Bankverbindung - Name of the Bank: .+", issuer[3])
                or following[0] != "Platzhalter: (UpWork Referenz) Placeholder: (Referece to Upwork)"
                or not re.fullmatch(r"- (T[0-9]+) - \1", following[1])):
            raise ArInvoiceParseError("customer_not_found", "Company-only recipient requires the observed issuer and reference structure")
    elif not hu_company_only and (len(recipient) < 2 or not (recipient[0].startswith("Herr ")
                                  or re.fullmatch(BARE_CONTACT, recipient[0]))):
        raise ArInvoiceParseError("customer_not_found", "Expected recipient contact and bilingual company line")
    # The company belongs on this exact row, never elsewhere in the document.
    company = re.fullmatch(r"(.+?) \1", recipient[0] if company_only else recipient[1])
    # 2102/2103 translate only the legal suffix, retaining the company stem.
    translated = None
    if not company_only and title.group(1) == "Számla" and hu_tax:
        translated = re.fullmatch(r"((.+?) AG) \2 Zrt\.", recipient[1])
    customer = company.group(1) if company else (translated.group(1) if translated else None)
    if customer is None or customer.casefold() == lines[2].casefold() or not any(c.isalpha() for c in customer):
        raise ArInvoiceParseError("customer_not_found", "Expected matching customer company identities in both language columns")

    # Gross labels determine the total grammar; optional net rows do not.
    legacy_hu = any(line.startswith(LEGACY_HU_GROSS) for line in lines)
    if legacy_hu and (title.group(1) != "Számla" or any(
        line.startswith("(siehe Vermerk) – gross amount:")
        for line in lines
    )):
        raise ArInvoiceParseError("unsupported_layout", "Mixed or unsupported aggregate-total labels")

    # A tax note in the header/footer is not an invoice-body treatment anchor.
    body = normalized[title.end():].split("\nBruttohonorar\n", 1)[0]
    note = _zero_vat_note(body, title.group(1))
    if sum(line.startswith("Vermerk:") for line in lines) != 1:
        note = None

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
        gross, gross_currency = legacy_total(LEGACY_HU_GROSS, "gross_amount_not_found", gross=True)
    else:
        gross, gross_currency = printed_total(r"Bruttohonorar\n\(siehe Vermerk\) – gross amount: \(see Note\)", "gross_amount_not_found")
    if note is not None:
        net, currency = gross, gross_currency
        # An optional, single explicit aggregate may be checked. Component
        # rows, missing values, and multiple net rows never determine net.
        label = LEGACY_HU_NET if legacy_hu else "Nettohonorar – net amount:"
        rows = [line for line in lines if line.startswith(label)]
        grammar = LEGACY_HUF_AMOUNT if legacy_hu else AMOUNT
        aggregate = re.fullmatch(rf"{re.escape(label)} ({grammar}) ([A-Z]{{3}}|€)", rows[0]) if len(rows) == 1 else None
        if aggregate:
            value = Decimal(aggregate.group(1).replace("." if legacy_hu else " ", ""))
            unit = "EUR" if aggregate.group(2) == "€" else aggregate.group(2)
            if unit != currency:
                raise ArInvoiceParseError("currency_conflict", "Printed net and gross currencies disagree")
            if value != gross:
                raise ArInvoiceParseError("totals_inconsistent", "Printed net and gross differ in the supported no-VAT layouts")
    elif legacy_hu:
        net, currency = legacy_total(LEGACY_HU_NET, "net_amount_not_found")
    else:
        net, currency = printed_total(r"Nettohonorar – net amount:", "net_amount_not_found")
    if currency != gross_currency:
        raise ArInvoiceParseError("currency_conflict", "Printed net and gross currencies disagree")
    if legacy_hu and currency != "HUF":
        raise ArInvoiceParseError("currency_conflict", "Legacy DE/HU grouped totals must be denominated in HUF")
    if net != gross:
        raise ArInvoiceParseError("totals_inconsistent", "Printed net and gross differ in the supported no-VAT layouts")

    if title.group(1) == "Számla":
        terms = ("Bitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tage." if legacy_hu
                 else "Bitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tagen")
    else:
        terms = "Bitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tage,"
    if note is None or normalized.count(terms) != 1:
        raise ArInvoiceParseError("unsupported_layout", "Expected the observed VAT note and 14-day payment terms")
    if legacy_hu:
        _one(rf"^{re.escape(terms)}$", normalized, "unsupported_layout",
             "Expected exact legacy DE/HU 14-day payment terms")
    # No explicit due date, VAT total, or customer purchase-order reference occurs
    # in either observed template. Company/tax registration IDs are not order IDs.
    try:
        parsed = OutgoingInvoiceCreateSchema(
            invoice_number=number, invoice_date=invoice_date, customer_name=customer,
            currency_original=currency, net_amount=net, amount_original=gross,
            due_date=None, vat_amount=None, customer_reference=None,
            remarks=note.replace("\n", " ") + "\n" + terms.replace("\n", " "),
        )
    except ValidationError:
        raise ArInvoiceParseError("invalid_invoice_values", "Printed invoice values do not satisfy receivables validation") from None
    if sparse or (hu_company_only and len(recipient) == 2) or (not company_only and len(recipient) == 2):
        logger.warning("AR invoice %s: Recipient address not present in source PDF", number)
    return parsed
