"""Minimal yfinance wrapper — fetches price + change for a single ticker.

No caching or fallback logic here: the scheduler handles persistence via PriceSnapshot.
"""

import logging

import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)


def fetch_price_and_change(ticker: str) -> tuple[float | None, float | None]:
    """Return (current_price, 1-day_change_pct) for a single ticker."""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if hist is None or hist.empty:
            logger.debug("%s: no data", ticker)
            return None, None

        closes = hist["Close"]
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) > 1 else latest
        change = round(((latest - prev) / prev) * 100, 2) if prev else None
        return round(latest, 2), change
    except Exception as exc:
        logger.debug("Error fetching %s: %s", ticker, exc)
        return None, None
