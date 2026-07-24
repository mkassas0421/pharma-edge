"""CRUD routes for managing catalyst events."""

import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.database import get_db, CatalystEvent, Ticker
from app.models.schemas import EventCreate, EventResponse

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
def list_events(
    ticker: str | None = Query(None),
    upcoming_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    q = db.query(CatalystEvent)
    if ticker:
        q = q.filter(CatalystEvent.ticker == ticker.upper())
    if upcoming_only:
        q = q.filter(CatalystEvent.event_date >= datetime.datetime.utcnow())
    return q.order_by(CatalystEvent.event_date).all()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """Return full details for a single catalyst event."""
    event = db.query(CatalystEvent).filter(CatalystEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(body: EventCreate, db: Session = Depends(get_db)):
    ticker_obj = db.query(Ticker).filter(Ticker.ticker == body.ticker.upper()).first()
    if not ticker_obj:
        raise HTTPException(status_code=404, detail=f"Ticker {body.ticker} not found. Add it first.")
    event = CatalystEvent(
        ticker_id=ticker_obj.id,
        ticker=body.ticker.upper(),
        title=body.title,
        event_type=body.event_type,
        event_date=body.event_date,
        impact_level=body.impact_level,
        description=body.description,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    obj = db.query(CatalystEvent).filter(CatalystEvent.id == event_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(obj)
    db.commit()
