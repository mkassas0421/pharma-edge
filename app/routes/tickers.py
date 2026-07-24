"""CRUD routes for managing tracked tickers.

When a ticker is created, aliases are auto-generated and the
ClinicalTrials.gov scraper runs immediately for that company.
"""

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db, Ticker, TickerAlias, CatalystEvent
from app.models.schemas import TickerCreate, TickerResponse
from scrapers.clinical_trials import _scrape_company

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("", response_model=list[TickerResponse])
def list_tickers(db: Session = Depends(get_db)):
    return db.query(Ticker).order_by(Ticker.ticker).all()


@router.post("", response_model=TickerResponse, status_code=status.HTTP_201_CREATED)
def create_ticker(body: TickerCreate, db: Session = Depends(get_db)):
    existing = db.query(Ticker).filter(Ticker.ticker == body.ticker.upper()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ticker already tracked")

    ticker = Ticker(
        ticker=body.ticker.upper(),
        company_name=body.company_name,
        sector=body.sector,
        notes=body.notes,
    )
    db.add(ticker)
    db.flush()

    # Auto-generate ClinicalTrials.gov aliases
    aliases = body.aliases if body.aliases else [
        body.company_name,
        body.company_name.replace(" Inc.", "").replace(" Inc", ""),
    ]
    now = datetime.datetime.utcnow()
    for alias in aliases:
        if alias.strip():
            db.add(TickerAlias(ticker_id=ticker.id, alias=alias.strip(), created_at=now))
    db.commit()
    db.refresh(ticker)

    # ── Immediately scrape ClinicalTrials.gov for this ticker ──
    try:
        candidates = _scrape_company(ticker.ticker, ticker.id)
        inserted = 0
        for ev_data in candidates:
            exists = db.query(CatalystEvent).filter(
                CatalystEvent.external_id == ev_data["external_id"],
                CatalystEvent.ticker == ev_data["ticker"],
            ).first()
            if exists:
                continue
            db.add(CatalystEvent(**ev_data))
            inserted += 1
        if inserted:
            db.commit()
            logger.info("Scraped %d event(s) for new ticker %s", inserted, ticker.ticker)
        else:
            logger.info("No events found on ClinicalTrials.gov for %s", ticker.ticker)
    except Exception as exc:
        logger.warning("Scraper failed for new ticker %s: %s", ticker.ticker, exc)

    return ticker


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticker(ticker: str, db: Session = Depends(get_db)):
    obj = db.query(Ticker).filter(Ticker.ticker == ticker.upper()).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Ticker not found")
    db.delete(obj)
    db.commit()
