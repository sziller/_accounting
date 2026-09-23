"""Authoritative policy for canonical accounting invoice numbers.

Populated invoice numbers are stored using uppercase ASCII letters, digits,
and ``/ - . _`` only.  All Python-recognized whitespace is removed before
validation and ASCII lowercase letters are uppercased.  Missing values are
valid: ``None`` remains ``None`` while empty and whitespace-only strings become
``""``.  No punctuation substitution, Unicode transliteration, or OCR repair
is performed; in particular, comma is invalid and is never changed to dot.

The Pydantic schema, service, SQLite model constraint, and recognition contract
all consume the constants and helpers in this module.
"""

from __future__ import annotations

import re
from typing import Any


INVOICE_NUMBER_MAX_LENGTH = 128
INVOICE_NUMBER_ALLOWED_PUNCTUATION = "/-._"
INVOICE_NUMBER_FORBIDDEN_PUNCTUATION = (",",)
INVOICE_NUMBER_PATTERN = (
    rf"^[A-Z0-9{re.escape(INVOICE_NUMBER_ALLOWED_PUNCTUATION)}]*$"
)
INVOICE_NUMBER_DESCRIPTION = (
    "Optional invoice identifier. Populated values are canonical uppercase ASCII "
    "using only A-Z, 0-9, '/', '-', '.', and '_'; all whitespace is removed. "
    "Comma and every other character are invalid. Blank input is allowed."
)

_INVOICE_NUMBER_RE = re.compile(INVOICE_NUMBER_PATTERN, flags=re.ASCII)
_ASCII_UPPER_TRANSLATION = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def canonicalize_invoice_number(value: str | None) -> str | None:
    """Return the canonical storage value for an optional invoice number.

    ``None`` remains ``None``. For strings, every character for which
    ``str.isspace()`` is true is removed, then ASCII ``a-z`` is translated to
    ``A-Z``. An empty result is returned as ``""`` and remains a valid missing
    value. A populated result must be at most 128 characters and match the
    authoritative canonical pattern exactly.

    Forbidden non-whitespace characters fail with ``ValueError``. The function
    never removes or substitutes punctuation, never changes comma to dot, and
    never transliterates non-ASCII letters. Non-string, non-null inputs fail
    with ``TypeError``.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("invoice_number must be a string or null")

    canonical = "".join(character for character in value if not character.isspace())
    canonical = canonical.translate(_ASCII_UPPER_TRANSLATION)
    if not canonical:
        return ""
    if len(canonical) > INVOICE_NUMBER_MAX_LENGTH:
        raise ValueError(
            f"invoice_number exceeds canonical maximum length "
            f"{INVOICE_NUMBER_MAX_LENGTH}"
        )
    if _INVOICE_NUMBER_RE.fullmatch(canonical) is None:
        raise ValueError(
            "invoice_number contains invalid characters; allowed characters are "
            "uppercase ASCII A-Z, digits 0-9, '/', '-', '.', and '_'"
        )
    return canonical


def is_populated_invoice_number(value: str | None) -> bool:
    """Return whether a canonicalized invoice-number value is populated."""
    return value is not None and value != ""


def get_invoice_number_policy_metadata() -> dict[str, Any]:
    """Return machine-readable recognition metadata from authoritative policy.

    The returned values are suitable for direct inclusion in the AI recognition
    contract, avoiding another independently maintained alphabet or length rule.
    """
    example_input = "ab 12 / 2026"
    return {
        "missing_allowed": True,
        "missing_storage": {"null_input": None, "blank_input": ""},
        "canonical_case": "UPPER_ASCII",
        "remove_all_whitespace": True,
        "max_length": INVOICE_NUMBER_MAX_LENGTH,
        "allowed_letters": "A-Z",
        "allowed_digits": "0-9",
        "allowed_punctuation": list(INVOICE_NUMBER_ALLOWED_PUNCTUATION),
        "forbidden_punctuation": list(INVOICE_NUMBER_FORBIDDEN_PUNCTUATION),
        "pattern": INVOICE_NUMBER_PATTERN,
        "examples": {
            "input": example_input,
            "canonical": canonicalize_invoice_number(example_input),
        },
    }


def get_invoice_number_recognizer_rules() -> list[str]:
    """Build AI recognizer guidance from the machine-readable policy metadata.

    The prose deliberately references values obtained from
    ``get_invoice_number_policy_metadata`` so the recognition contract cannot
    drift to a separately hard-coded alphabet, punctuation list, or length.
    """
    policy = get_invoice_number_policy_metadata()
    alphabet = (
        f"{policy['allowed_letters']}, {policy['allowed_digits']}, and "
        + " ".join(policy["allowed_punctuation"])
    )
    forbidden = " ".join(policy["forbidden_punctuation"])
    return [
        "invoice_number may be null or empty when it cannot be reliably recognized; "
        "a missing invoice number must never cause the accounting entry to be omitted.",
        "Never invent an invoice number. If it is uncertain, leave invoice_number "
        "missing and explain the uncertainty in remarks.",
        "When visible and reliable, output invoice_number in the canonical form "
        "specified by invoice_number_policy: remove all whitespace and use uppercase "
        f"ASCII with only {alphabet}.",
        f"The following punctuation is never valid in invoice_number: {forbidden}. "
        "Never guess or convert an uncertain comma/dot reading; prefer a missing "
        "invoice_number and document the uncertainty in remarks.",
    ]


def build_invoice_number_sqlite_check(column_name: str = "invoice_number") -> str:
    """Build SQLite CHECK SQL enforcing the canonical populated representation.

    SQLite has no built-in Python-compatible regular-expression CHECK. The
    generated expression therefore permits null/empty values and uses GLOB's
    negated character class to reject any populated value outside the same
    authoritative alphabet, while separately enforcing the shared maximum
    length. The hyphen is placed last in the GLOB class so it is literal.
    """
    if not column_name.isidentifier():
        raise ValueError("column_name must be a simple SQL identifier")
    glob_punctuation = "".join(
        character
        for character in INVOICE_NUMBER_ALLOWED_PUNCTUATION
        if character != "-"
    ) + "-"
    allowed_glob_class = f"A-Z0-9{glob_punctuation}"
    return (
        f"{column_name} IS NULL OR {column_name} = '' OR ("
        f"length({column_name}) <= {INVOICE_NUMBER_MAX_LENGTH} AND "
        f"{column_name} NOT GLOB '*[^{allowed_glob_class}]*')"
    )
