"""Minimal yfinance wrapper — fetches price + change for a single ticker.

No caching or fallback logic here: the scheduler handles persistence via PriceSnapshot.
"""

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
