# scripts/reprocess_pending_conversions.py

from __future__ import annotations

from app.db.database import create_db_session, init_db
from app.services.conversion_service import ConversionService


def main() -> None:
    """=== script function ====
    Reprocess pending accounting-entry currency conversions.
    === by Sziller & ChatGPT ==="""
    init_db()

    db = create_db_session()

    try:
        service = ConversionService(db=db)
        resolved_count = service.reprocess_pending(limit=100)

        print(f"Resolved pending conversions: {resolved_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
