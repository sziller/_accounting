"""Receivables input and non-recursive response contracts."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from app.core import config

Money = Annotated[Decimal, Field(max_digits=24, decimal_places=6, ge=0)]
PositiveMoney = Annotated[Decimal, Field(max_digits=24, decimal_places=6, gt=0)]
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
OptionalText = Annotated[str, Field(max_length=255)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
PdfHash = Annotated[str, StringConstraints(pattern=r"^[a-fA-F0-9]{64}$")]


class ReceivableSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ArRecognitionEventReadSchema(ReceivableSchema):
    invoice_id: str
    recognition_date: date
    tax_year: int
    amount_original: Decimal
    currency_original: str
    net_amount_original: Decimal | None
    vat_amount_original: Decimal | None
    amount_common: Decimal | None
    source: Literal['allocation', 'manual_invoice_payment']
    payment_id: str | None
    allocation_id: str | None


class OutgoingInvoiceSourceSchema(ReceivableSchema):
    """Shared document facts for CRUD and recognition; no accounting state."""
    invoice_number: RequiredText
    invoice_date: date
    due_date: date | None = None
    customer_name: RequiredText
    customer_reference: OptionalText | None = None
    currency: Currency
    net_amount: Money | None = None
    vat_amount: Money | None = None
    gross_amount: PositiveMoney
    pdf_filename: OptionalText | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def validate_totals(self):
        if self.net_amount is not None and self.vat_amount is not None:
            if self.net_amount + self.vat_amount != self.gross_amount:
                raise ValueError("net_amount + vat_amount must equal gross_amount")
        return self


class OutgoingInvoiceCreateSchema(OutgoingInvoiceSourceSchema):
    payment_date: date | None = None
    currency_original: Currency
    amount_original: PositiveMoney
    currency_common: Currency = Field(default_factory=lambda: config.AR_COMMON_CURRENCY, validate_default=True)
    pdf_sha256: PdfHash | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_original_aliases(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            for original, legacy in (("currency_original", "currency"), ("amount_original", "gross_amount")):
                if original not in data and legacy in data:
                    data[original] = data[legacy]
                if legacy not in data and original in data:
                    data[legacy] = data[original]
        return data

    @model_validator(mode="after")
    def validate_components(self):
        if self.currency_original != self.currency or self.amount_original != self.gross_amount:
            raise ValueError("Original currency/amount must agree with legacy currency/gross_amount")
        return self


class OutgoingInvoiceUpdateSchema(ReceivableSchema):
    invoice_number: RequiredText | None = None
    invoice_date: date | None = None
    payment_date: date | None = None
    due_date: date | None = None
    customer_name: RequiredText | None = None
    customer_reference: OptionalText | None = None
    currency: Currency | None = None
    net_amount: Money | None = None
    vat_amount: Money | None = None
    gross_amount: PositiveMoney | None = None
    currency_original: Currency | None = None
    amount_original: PositiveMoney | None = None
    currency_common: Currency | None = None
    pdf_filename: OptionalText | None = None
    pdf_sha256: PdfHash | None = None
    remarks: str | None = None


class IncomingPaymentCreateSchema(ReceivableSchema):
    payment_date: date
    amount: PositiveMoney
    currency: Currency
    payer_name: OptionalText | None = None
    bank_reference: OptionalText | None = None
    payment_method: Annotated[str, Field(max_length=64)] | None = None
    remarks: str | None = None


class IncomingPaymentUpdateSchema(ReceivableSchema):
    payment_date: date | None = None
    amount: PositiveMoney | None = None
    currency: Currency | None = None
    payer_name: OptionalText | None = None
    bank_reference: OptionalText | None = None
    payment_method: Annotated[str, Field(max_length=64)] | None = None
    remarks: str | None = None


class InvoicePaymentAllocationCreateSchema(ReceivableSchema):
    invoice_id: RequiredText
    payment_id: RequiredText
    amount_allocated: PositiveMoney


class InvoicePaymentAllocationReadSchema(InvoicePaymentAllocationCreateSchema):
    id: str
    created_at: datetime


class InvoiceAllocationReadSchema(InvoicePaymentAllocationReadSchema):
    payment_date: date


class PaymentAllocationReadSchema(InvoicePaymentAllocationReadSchema):
    invoice_number: str


class OutgoingInvoiceReadSchema(OutgoingInvoiceCreateSchema):
    amount_common: Money | None = None
    id: str
    created_at: datetime
    updated_at: datetime
    paid_amount: Decimal
    outstanding_amount: Decimal
    payment_status: Literal["open", "partially_paid", "paid", "overdue"]
    allocations: list[InvoiceAllocationReadSchema]


class ArConversionResultSchema(ReceivableSchema):
    id: str
    invoice_number: str
    status: Literal["converted", "pending"]
    amount_common: Money | None = None
    currency_common: Currency
    message: str


class ArConversionReportSchema(ReceivableSchema):
    converted: int
    pending: int
    invoices: list[ArConversionResultSchema]


class IncomingPaymentReadSchema(IncomingPaymentCreateSchema):
    id: str
    created_at: datetime
    updated_at: datetime
    allocated_amount: Decimal
    unallocated_amount: Decimal
    allocations: list[PaymentAllocationReadSchema]


class ArProcessingTraceSchema(ReceivableSchema):
    tax_year: int | None
    fx_date_policy: Literal['invoice_date']
    fx_lookup_date: date
    fx_source: Literal['ECB', 'MNB', 'same_currency']
    amount_common: Money


class ArProcessingResultSchema(ReceivableSchema):
    id: str
    invoice_number: str | None
    status: Literal['processed', 'failed']
    message: str
    entry: OutgoingInvoiceReadSchema | None = None
    trace: ArProcessingTraceSchema | None = None


class ArProcessingReportSchema(ReceivableSchema):
    processed: int
    failed: int
    invoices: list[ArProcessingResultSchema]
