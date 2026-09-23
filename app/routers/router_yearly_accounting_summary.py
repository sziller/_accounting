"""Read-only adapter for the downstream yearly aggregation service."""
from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.db.database import get_db_session
from app.schemas.yearly_accounting_summary_schema import YearlyAccountingSummaryReadSchema
from app.services.yearly_accounting_summary_service import YearlyAccountingSummaryService


class YearlyAccountingSummaryRouter(APIRouter):
    def __init__(self, *, prefix="/acct", **kwargs):
        super().__init__(prefix=prefix, tags=["reporting"], **kwargs)
        self.add_api_route(
            "/v0/yearly-accounting-summary/{tax_year}", self.summary,
            methods=["GET"], response_model=YearlyAccountingSummaryReadSchema,
        )

    def summary(self, tax_year: int = Path(..., ge=1, le=9999),
                db: Session = Depends(get_db_session)):
        return YearlyAccountingSummaryService(db).build(tax_year)
