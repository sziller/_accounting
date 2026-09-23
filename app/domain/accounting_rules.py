# app/domain/accounting_rules.py

from __future__ import annotations

from decimal import Decimal
from app.domain.historical_values import resolve_historical_value


ENTRY_TYPES = {
    "expense",
    "income",
    "tax",
    "private",
    "correction",
}

TAX_SCOPES = {
    "domestic",
    "eu",
    "third_country",
    "not_applicable",
}

PAYMENT_METHODS = {
    "cash",
    "bank_transfer",
    "card",
    "paypal",
    "blockchain",
    "unknown",
}

CURRENCIES = {
    "EUR",
    "HUF",
    "USD",
    "BTC",
}

WRITEOFF_METHODS = {
    "immediate",
    "partial",
    "multi_year",
    "none",
}


CATEGORY_LABELS = {
    "buro": "Büro",
    "steuerberatung": "Steuerberatung",
    "einrichtung": "Einrichtung",
    "betriebsbedarf": "Betriebsbedarf",
    "porto-ohne-ust": "Porto ohne USt",
    "porto-mit-ust": "Porto mit USt",
    "werkzeug": "Werkzeug",
    "werkzeug-mehrjaehrige-abschreibung": "Werkzeug mehrjährige Abschreibung",
    "auto": "Auto",
    "raum": "Raum",
    "betriebskosten": "Betriebskosten",
    "bewirtung": "Bewirtung",
    "werbung": "Werbung",
    "handy-vertrag": "Handy Vertrag",
    "handy-prepaid": "Handy Prepaid",
    "fachliteratur": "Fachliteratur",
    "ubernachtung": "Übernachtung",
    "krankenversicherung": "Krankenversicherung",
    "pfegeversicherung": "Pflegeversicherung",
    "hausratversicherung": "Hausratversicherung",
    "haftpflichtversicherung": "Haftpflichtversicherung",
    "rentenversicherung": "Rentenversicherung",
    "reiseversicherung": "Reiseversicherung",
    "festnetz": "Festnetz",
    "bahn": "Bahn",
    "bvg": "BVG",
    "eingang": "Eingang",
    "honorar": "Honorar",
    "umsatzsteuer-vorauszahlung": "Umsatzsteuer Vorauszahlung",
    "einkommen-kirchen-soli-vorauszahlung": "Einkommen/Kirchen/Soli Vorauszahlung",
    "n/a": "N/A",
}


# Year 1 preserves legacy classification, not verified legislative history.
LEGACY_CATEGORY_VAT_CLASS_COMPATIBILITY_HISTORY = {
    "honorar": {1: "standard"},
    "eingang": {1: "standard"},
    "steuerberatung": {1: "standard"},
    "krankenversicherung": {1: "none"},
    "pfegeversicherung": {1: "none"},
    "rentenversicherung": {1: "none"},
    "hausratversicherung": {1: "none"},
    "haftpflichtversicherung": {1: "none"},
    "reiseversicherung": {1: "none"},
    "raum": {1: "none"},
    "betriebskosten": {1: "none"},
    "buro": {1: "standard"},
    "einrichtung": {1: "standard"},
    "betriebsbedarf": {1: "standard"},
    "werkzeug": {1: "standard"},
    "werkzeug-mehrjaehrige-abschreibung": {1: "multi_year"},
    "porto-ohne-ust": {1: "none"},
    "porto-mit-ust": {1: "standard"},
    "fachliteratur": {1: "reduced"},
    "werbung": {1: "standard"},
    "handy-vertrag": {1: "standard"},
    "handy-prepaid": {1: "none"},
    "festnetz": {1: "none"},
    "auto": {1: "none"},
    "bewirtung": {1: "standard"},
    "ubernachtung": {1: "reduced"},
    "bahn": {1: "standard"},
    "bvg": {1: "none"},
    "umsatzsteuer-vorauszahlung": {1: "not_applicable"},
    "einkommen-kirchen-soli-vorauszahlung": {1: "not_applicable"},
    "n/a": {1: "standard"},
}


# Provisional legacy compatibility, NOT verified legislative effective dates.
# Year 1 preserves accepted-date behavior only. See accounting_rule_contract.md
# for the explicit migration to verified coverage; do not mix verified points here.
LEGACY_VAT_COMPATIBILITY_HISTORY = {
    "standard": {1: Decimal("19")},
    "reduced": {1: Decimal("7")},
    "none": {1: Decimal("0")},
    "not_applicable": {1: Decimal("0")},
    "multi_year": {1: Decimal("19")},
}

# Existing public name retained as an alias, not a second rule dataset.
# All current production VAT history is provisional compatibility coverage.
VAT_RATE_HISTORY = LEGACY_VAT_COMPATIBILITY_HISTORY


# Provisional legacy compatibility, not verified legislative effective years.
# Year 1 preserves all previously accepted AP payment years.
LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY = {
    "n/a": {1: Decimal("100")},
    "werkzeug-mehrjaehrige-abschreibung": {1: Decimal("33.333")},
    "auto": {1: Decimal("0")},
    "raum": {1: Decimal("100")},
    "bewirtung": {1: Decimal("70")},
    "hausratversicherung": {1: Decimal("50")},
    "haftpflichtversicherung": {1: Decimal("50")},
    "festnetz": {1: Decimal("50")},
}


def get_allowed_category_codes() -> list[str]:
    """=== domain function ====
    Return all supported accounting category codes.
    === by Sziller & ChatGPT ==="""
    return sorted(CATEGORY_LABELS.keys())


def get_vat_class(category_code: str, *, tax_year: int) -> str:
    """Resolve the domestic category classification for the explicit tax year."""
    history = LEGACY_CATEGORY_VAT_CLASS_COMPATIBILITY_HISTORY.get(category_code)
    if history is None:
        raise ValueError(f"Unknown category code: {category_code}")
    return resolve_historical_value(history, tax_year)


def resolve_vat_treatment_legacy(*, category_code: str, tax_scope: str, tax_year: int) -> Decimal:
    """Retained legacy treatment; composes static histories, not VAT arithmetic."""
    if tax_scope != "domestic":
        return Decimal("0")

    vat_class = get_vat_class(category_code, tax_year=tax_year)

    return resolve_historical_value(VAT_RATE_HISTORY[vat_class], tax_year)


# Year 1 denotes legacy compatibility, not verified legislative coverage.
# Retain this implementation when a reviewed later behavior is registered.
LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY = {
    1: resolve_vat_treatment_legacy,
}


def get_vat_rate_percent(category_code: str, tax_scope: str, *, tax_year: int) -> Decimal:
    """Select the historical treatment procedure, then resolve its VAT rate."""
    rule = resolve_historical_value(LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY, tax_year)
    return rule(category_code=category_code, tax_scope=tax_scope, tax_year=tax_year)


def get_deductible_percent(category_code: str, *, tax_year: int) -> Decimal:
    """=== domain function ====
    Return the deductible percentage for a category.
    === by Sziller & ChatGPT ==="""
    if category_code not in LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY:
        return Decimal("100")
    return resolve_historical_value(
        LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY[category_code], tax_year)


def get_writeoff_method(category_code: str, *, tax_year: int) -> str:
    """=== domain function ====
    Return the write-off method implied by a category.
    === by Sziller & ChatGPT ==="""
    if category_code == "werkzeug-mehrjaehrige-abschreibung":
        return "multi_year"

    if get_deductible_percent(category_code, tax_year=tax_year) == Decimal("0"):
        return "none"

    if get_deductible_percent(category_code, tax_year=tax_year) != Decimal("100"):
        return "partial"

    return "immediate"
