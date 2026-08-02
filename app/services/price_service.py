"""Minimal yfinance wrapper — fetches price + change for a single ticker.

No caching or fallback logic here: the scheduler handles persistence via PriceSnapshot.
"""

import datetime
import logging

import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

# Cloud hosts (Render, Railway, etc.) often get rate-limited by Yahoo Finance.
# Setting a browser-like User-Agent helps avoid blocks.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _make_ticker(ticker: str) -> yf.Ticker:
    """Create a yfinance Ticker with a browser-like User-Agent."""
    t = yf.Ticker(ticker)
    try:
        t.session.headers["User-Agent"] = _UA
    except Exception:
        pass
    return t


def fetch_price_and_change(ticker: str) -> tuple[float | None, float | None]:
    """Return (current_price, 1-day_change_pct) for a single ticker."""
    try:
        hist = _make_ticker(ticker).history(period="5d")
        if hist is None or hist.empty:
            logger.debug("%s: no data", ticker)
            return None, None

        closes = hist["Close"]
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) > 1 else latest

        # Sub-penny stocks get 4 decimal places to prevent $0.00 display
        decimals = 4 if latest < 0.01 else 2
        price = round(latest, decimals)

        # Compute % change normally — big moves on penny stocks are relevant
        if prev and prev > 0:
            change = round(((latest - prev) / prev) * 100, 2)
        else:
            change = None

        return price, change
    except Exception as exc:
        logger.debug("Error fetching %s: %s", ticker, exc)
        return None, None


def get_historical_prices(ticker: str, event_date: datetime.datetime) -> dict:
    """Fetch T-1 / T / T+1 / T+5 trading-day closes around ``event_date``.

    Returns a dict with keys: price_before, price_at_event, price_after_1d,
    price_after_5d. Missing days (event too recent, fetch failure, delisted
    ticker) come back as ``None`` — the caller decides how to handle them.

    The anchor is the first trading day on/after ``event_date`` (yfinance
    history() only contains trading days, so weekend/holiday events naturally
    land on the next market open). Offsets are then applied by position.
    """
    result = {
        "price_before": None,
        "price_at_event": None,
        "price_after_1d": None,
        "price_after_5d": None,
    }
    try:
        # Calendar-day window around the event; end is exclusive in yfinance,
        # so +15 days leaves room for T+5 even across holiday-heavy stretches.
        start = event_date - datetime.timedelta(days=10)
        end = event_date + datetime.timedelta(days=15)
        hist = _make_ticker(ticker).history(start=start.date(), end=end.date())
        if hist is None or hist.empty:
            logger.debug("%s: no history around %s", ticker, event_date.date())
            return result

        closes = hist["Close"]
        # yfinance returns a tz-aware DatetimeIndex — compare by calendar date
        dates = [ts.to_pydatetime().date() for ts in hist.index]

        # Anchor: first trading day on/after the event date
        anchor = None
        target = event_date.date()
        for i, d in enumerate(dates):
            if d >= target:
                anchor = i
                break

        def close_at(i):
            if 0 <= i < len(closes):
                value = float(closes.iloc[i])
                return value if value and value > 0 else None
            return None

        if anchor is not None:
            result["price_before"] = close_at(anchor - 1)
            result["price_at_event"] = close_at(anchor)
            result["price_after_1d"] = close_at(anchor + 1)
            result["price_after_5d"] = close_at(anchor + 5)
        return result
    except Exception as exc:
        logger.debug("Error fetching history for %s: %s", ticker, exc)
        return result
