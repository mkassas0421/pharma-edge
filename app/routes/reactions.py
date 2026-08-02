"""Reaction endpoints — actual price reactions after catalyst events mature.

The per-event endpoint lives under /api/events and the aggregate statistics
under /api/reactions; both are grouped here since they share one service.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
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
    """Stats for events like the given one, most specific cohort first.

    Convenience endpoint for the event modal — answers "how did THIS ticker
    react to the same kind of catalyst?" Tiers, from specific to broad:
      1. ticker + event_type  ("BIIB's prior Ph3 readouts")
      2. ticker only          ("BIIB's prior catalysts, any type")
      3. market cohort        (same impact + type across all tickers)
    A tier is used once it has enough samples; the market cohort is the
    last resort and is returned even when small (frontend flags it).
    ``sample_source`` in the response tells the frontend which tier won.
    """
    event = db.query(CatalystEvent).filter(CatalystEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    tiers = (
        (dict(ticker=event.ticker, event_type=event.event_type), "ticker_type"),
        (dict(ticker=event.ticker), "ticker"),
        (
            dict(impact_level=event.impact_level, event_type=event.event_type),
            "market_cohort",
        ),
    )
    for filters, source in tiers:
        stats = get_reaction_stats(db, **filters)
        stats["sample_source"] = source
        if stats["n"] >= settings.reaction_min_sample_size or source == "market_cohort":
            return stats
