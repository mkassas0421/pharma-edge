"""Reaction endpoints — actual price reactions after catalyst events mature.

The per-event endpoint lives under /api/events and the aggregate statistics
under /api/reactions; both are grouped here since they share one service.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.database import get_db, CatalystEvent, EventReaction
from app.models.schemas import EventReactionResponse, ReactionStatsResponse
from app.services.reaction_service import get_reaction_stats

router = APIRouter(prefix="/api", tags=["reactions"])


@router.get("/events/{event_id}/reaction", response_model=EventReactionResponse)
def get_event_reaction(event_id: int, db: Session = Depends(get_db)):
    """Return the recorded price reaction for a single event (if any)."""
    reaction = (
        db.query(EventReaction)
        .filter(EventReaction.event_id == event_id)
        .first()
    )
    if not reaction:
        raise HTTPException(status_code=404, detail="No reaction recorded for this event")
    return reaction


@router.get("/reactions/stats", response_model=ReactionStatsResponse)
def reaction_stats(
    impact_level: str | None = Query(None),
    event_type: str | None = Query(None),
    ticker: str | None = Query(None),
    indication: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Aggregate reaction statistics, optionally filtered."""
    return get_reaction_stats(
        db,
        impact_level=impact_level,
        event_type=event_type,
        ticker=ticker,
        indication=indication,
    )


@router.get("/reactions/stats/similar/{event_id}", response_model=ReactionStatsResponse)
def reaction_stats_similar(event_id: int, db: Session = Depends(get_db)):
    """Stats for events like the given one (same impact_level + event_type).

    Convenience endpoint for the event modal — answers "how has the market
    historically reacted to similar catalysts?"
    """
    event = db.query(CatalystEvent).filter(CatalystEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return get_reaction_stats(
        db,
        impact_level=event.impact_level,
        event_type=event.event_type,
    )
