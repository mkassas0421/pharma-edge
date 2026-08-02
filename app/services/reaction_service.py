"""Capture and aggregate actual price reactions after catalyst events mature.

A catalyst event "matures" once its event_date is far enough in the past that
the T+5 trading-day window is fully available. The scheduler then records the
real price move around the event (yfinance on-demand) and the stats endpoints
aggregate those moves into mean / median / stdev / hit-rate per filter.
"""

import datetime
import logging
import statistics
import time

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import SessionLocal, CatalystEvent, EventReaction
from app.services.price_service import get_historical_prices

logger = logging.getLogger(__name__)


# ── Capture ────────────────────────────────────────────────────────────────

def _capture_one(db: Session, event: CatalystEvent, prices: dict) -> str:
    """Record (or update) the reaction row for one event; returns new status.

    ``prices`` is the dict from ``price_service.get_historical_prices`` —
    all-None values mean the fetch failed (delisted / yfinance error).
    """
    reaction = (
        db.query(EventReaction)
        .filter(EventReaction.event_id == event.id)
        .first()
    )
    if reaction is None:
        reaction = EventReaction(event_id=event.id, ticker=event.ticker)
        db.add(reaction)

    # Denormalise metadata at capture time (reaction data outlives the event)
    reaction.ticker = event.ticker
    reaction.event_type = event.event_type
    reaction.impact_level = event.impact_level

    before = prices["price_before"]
    at_event = prices["price_at_event"]
    after_5d = prices["price_after_5d"]

    reaction.price_before = before
    reaction.price_at_event = at_event
    reaction.price_after_1d = prices["price_after_1d"]
    reaction.price_after_5d = after_5d

    if before is None and at_event is None and after_5d is None:
        # No price data at all — ticker delisted or yfinance failed
        reaction.status = "failed"
        return reaction.status

    if before and before > 0:
        if at_event is not None:
            reaction.reaction_1d_pct = (at_event - before) / before
        if after_5d is not None:
            reaction.reaction_5d_pct = (after_5d - before) / before

    if after_5d is not None:
        # Full window available — done, unless prices were degenerate
        reaction.status = "captured"
        reaction.captured_at = datetime.datetime.utcnow()
    else:
        # T+5 not available yet (event too recent) — retry next cycle
        reaction.status = "pending"
    return reaction.status


def capture_reactions_for_matured_events() -> None:
    """Find matured catalyst events and record their price reactions.

    Runs daily. An event is mature when its event_date is at least
    ``settings.reaction_capture_min_days`` calendar days in the past, so the
    T+5 trading-day window is fully available. Rows already captured are
    skipped; failed fetches are retried next cycle; too-recent events stay
    ``pending`` until the window fills in.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(
            days=settings.reaction_capture_min_days
        )
        events = (
            db.query(CatalystEvent)
            .outerjoin(EventReaction, EventReaction.event_id == CatalystEvent.id)
            .filter(
                CatalystEvent.event_date <= cutoff,
                (EventReaction.id.is_(None)) | (EventReaction.status != "captured"),
            )
            .order_by(CatalystEvent.event_date)
            .all()
        )
        if not events:
            logger.debug("No matured events to capture.")
            return

        captured = failed = pending = 0
        for event in events:
            prices = get_historical_prices(event.ticker, event.event_date)
            status = _capture_one(db, event, prices)
            if status == "captured":
                captured += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1
            # Small delay between tickers to avoid Yahoo rate limits
            # (matches refresh_prices in scheduler.py)
            time.sleep(0.5)

        db.commit()
        logger.info(
            "Reaction capture: %d captured, %d failed, %d pending",
            captured, failed, pending,
        )
    except Exception as exc:
        logger.error("Reaction capture failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ── Aggregation ────────────────────────────────────────────────────────────

def get_reaction_stats(
    db: Session,
    impact_level: str | None = None,
    event_type: str | None = None,
    ticker: str | None = None,
    indication: str | None = None,
) -> dict:
    """Aggregate captured reactions matching the given filters.

    Returns mean / median / stdev / positive-rate for the 1-day and 5-day
    reactions, plus max/min of the 1-day reaction. ``n`` is the number of
    captured reactions in the sample; when ``n`` is below the configured
    minimum, ``low_sample_warning`` is set so the frontend can flag it.
    """
    q = db.query(EventReaction).filter(EventReaction.status == "captured")
    if impact_level:
        q = q.filter(EventReaction.impact_level == impact_level)
    if event_type:
        q = q.filter(EventReaction.event_type == event_type)
    if ticker:
        q = q.filter(EventReaction.ticker == ticker.upper())
    if indication:
        q = q.filter(EventReaction.indication == indication)

    rows = q.all()
    n = len(rows)

    one_day = [r.reaction_1d_pct for r in rows if r.reaction_1d_pct is not None]
    five_day = [r.reaction_5d_pct for r in rows if r.reaction_5d_pct is not None]

    def _summarise(values):
        """Return (mean, median, stdev, positive_rate) or all-None if empty."""
        if not values:
            return None, None, None, None
        mean = statistics.mean(values)
        median = statistics.median(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        positive_rate = sum(1 for v in values if v > 0) / len(values)
        return mean, median, stdev, positive_rate

    mean1, med1, std1, pos1 = _summarise(one_day)
    mean5, med5, std5, _ = _summarise(five_day)

    return {
        "n": n,
        "mean_1d_pct": round(mean1, 4) if mean1 is not None else None,
        "median_1d_pct": round(med1, 4) if med1 is not None else None,
        "stdev_1d_pct": round(std1, 4) if std1 is not None else None,
        "mean_5d_pct": round(mean5, 4) if mean5 is not None else None,
        "median_5d_pct": round(med5, 4) if med5 is not None else None,
        "stdev_5d_pct": round(std5, 4) if std5 is not None else None,
        "positive_rate_1d": round(pos1, 4) if pos1 is not None else None,
        "max_1d_pct": round(max(one_day), 4) if one_day else None,
        "min_1d_pct": round(min(one_day), 4) if one_day else None,
        "low_sample_warning": n < settings.reaction_min_sample_size,
    }
