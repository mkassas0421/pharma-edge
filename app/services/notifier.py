"""Notification service — sends alerts to Discord and Telegram channels.

Supports multiple Discord channels for different event types:
  - high-impact  → PDUFA dates, Phase 3 readouts, FDA decisions
  - sec-filings  → 8-K, 13D/13G, S-1/S-3 filings in real-time
  - briefing     → morning radar / evening summary (cron)
  - clinical     → CT.gov status changes (phase upgrades, completions)

Messages include Yahoo Finance chart links and a link back to the dashboard.
"""

import datetime
import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TODAY = datetime.date.today().strftime("%B %d, %Y")

# ── Helpers ─────────────────────────────────────────────────────────────────

def _yahoo_link(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}"

def _dashboard_link() -> str:
    return settings.base_url


# ── Low-level: send a raw embed to any webhook URL ──────────────────────────

def _send_embed(webhook_url: str, embed: dict, mention_everyone: bool = False) -> bool:
    """Push a Discord embed to *webhook_url*. Returns True on success."""
    if not webhook_url:
        return False
    payload = {"embeds": [embed]}
    if mention_everyone:
        payload["content"] = "@everyone"
        payload["allowed_mentions"] = {"parse": ["everyone"]}
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.debug("Discord send failed: %s", exc)
        return False


# ── Helpers for building embed fields ──────────────────────────────────────

def _impact_color(impact: str) -> int:
    return {"High": 0x10b981, "Medium": 0xf59e0b, "Low": 0x6b7280}.get(impact, 0x6b7280)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #high-impact-catalysts
# ═══════════════════════════════════════════════════════════════════════════

def send_high_impact_alert(
    ticker: str,
    company: str,
    title: str,
    event_type: str,
    event_date: str,
    days_until: int,
    impact: str,
    description: str = "",
) -> bool:
    """PDUFA dates, Phase 3 readouts — uses @everyone."""
    embed = {
        "title": f"🔔 {ticker} — {title}",
        "description": (description.strip()[:500] if description else None),
        "color": _impact_color(impact),
        "fields": [
            {"name": "Company", "value": company, "inline": True},
            {"name": "Date", "value": event_date, "inline": True},
            {"name": "Countdown", "value": f"{days_until} day(s)", "inline": True},
            {"name": "Impact", "value": impact, "inline": True},
        ],
        "url": _yahoo_link(ticker),
        "footer": {"text": "Pharma Catalyst Alert System"},
    }
    embed["fields"].append(
        {"name": "Links", "value": f"[📈 Yahoo Finance]({_yahoo_link(ticker)}) · [📊 Dashboard]({_dashboard_link()})", "inline": False}
    )
    return _send_embed(settings.discord_webhook_high_impact, embed, mention_everyone=True)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #sec-filings-live
# ═══════════════════════════════════════════════════════════════════════════

def send_sec_filing(ticker: str, company: str, form_type: str, description: str, url: str = "") -> bool:
    """Real-time SEC filing alert (8-K, 13D, S-1, …)."""
    color = {"8-K": 0x3b82f6, "13D": 0xf59e0b, "13G": 0xf59e0b, "S-1": 0xef4444, "S-3": 0xef4444}.get(form_type, 0x6b7280)
    embed = {
        "title": f"📄 {ticker} — {form_type} Filing",
        "description": description[:1000] if description else None,
        "color": color,
        "fields": [
            {"name": "Company", "value": company, "inline": True},
            {"name": "Form", "value": form_type, "inline": True},
        ],
        "url": url or _yahoo_link(ticker),
        "footer": {"text": f"SEC EDGAR · {_TODAY}"},
    }
    embed["fields"].append(
        {"name": "Links", "value": f"[📈 Yahoo Finance]({_yahoo_link(ticker)}) · [📊 Dashboard]({_dashboard_link()})", "inline": False}
    )
    return _send_embed(settings.discord_webhook_sec_live, embed)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #clinical-trials-updates
# ═══════════════════════════════════════════════════════════════════════════

def send_clinical_change(ticker: str, company: str, drug: str, change_desc: str, nct_id: str = "") -> bool:
    """Notify when a trial transitions phase or status."""
    embed = {
        "title": f"🧪 {ticker} — {drug}",
        "description": change_desc[:500],
        "color": 0x8b5cf6,
        "fields": [
            {"name": "Company", "value": company, "inline": True},
            {"name": "NCT ID", "value": nct_id or "—", "inline": True},
        ],
        "footer": {"text": f"ClinicalTrials.gov · {_TODAY}"},
    }
    embed["fields"].append(
        {"name": "Links", "value": f"[📈 Yahoo Finance]({_yahoo_link(ticker)}) · [📊 Dashboard]({_dashboard_link()}){' · [🔬 Trial](https://clinicaltrials.gov/study/{nct_id})' if nct_id else ''}", "inline": False}
    )
    return _send_embed(settings.discord_webhook_clinical, embed)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #daily-biotech-briefing
# ═══════════════════════════════════════════════════════════════════════════

def send_morning_briefing() -> bool:
    """🌅 Today's radar — PDUFA dates, top catalysts, pre-market movers.

    Called by the cron scheduler at 08:30 local time.
    """
    from app.models.database import SessionLocal, Ticker, CatalystEvent, PriceSnapshot

    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        today_end = now + datetime.timedelta(days=1)

        # ── Today's events ──
        today_events = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date >= now, CatalystEvent.event_date < today_end)
            .order_by(CatalystEvent.event_date)
            .all()
        )

        # ── This week's high-impact events ──
        week_end = now + datetime.timedelta(days=7)
        week_high = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date >= now, CatalystEvent.event_date < week_end, CatalystEvent.impact_level == "High")
            .order_by(CatalystEvent.event_date)
            .all()
        )

        # ── Pre-market movers (top 5 by price change) ──
        snapshots = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.change_percent.isnot(None))
            .order_by(PriceSnapshot.change_percent.desc())
            .limit(5)
            .all()
        )

        # ── Build fields ──
        lines_today = []
        for ev in today_events[:8]:
            t_obj = db.query(Ticker).filter(Ticker.ticker == ev.ticker).first()
            lines_today.append(f"• **${ev.ticker}** — {ev.title} ({ev.event_date.strftime('%b %d')})")

        lines_week = []
        for ev in week_high[:5]:
            lines_week.append(f"• **${ev.ticker}** — {ev.title} ({ev.event_date.strftime('%b %d')})")

        lines_movers = []
        for s in snapshots:
            ticker_obj = db.query(Ticker).filter(Ticker.ticker == s.ticker).first()
            name = ticker_obj.company_name if ticker_obj else s.ticker
            sign = "+" if s.change_percent and s.change_percent >= 0 else ""
            lines_movers.append(f"• **${s.ticker}** {name} — {sign}{s.change_percent:.2f}%")

        embed = {
            "title": f"🌅 PharmaEdge Daily Radar | {_TODAY}",
            "color": 0x06b6d4,
            "fields": [
                {"name": "🚨 Today's Catalysts", "value": "\n".join(lines_today) if lines_today else "No events scheduled today.", "inline": False},
                {"name": "📅 High-Impact This Week", "value": "\n".join(lines_week) if lines_week else "None this week.", "inline": False},
                {"name": "📈 Top Movers (24h)", "value": "\n".join(lines_movers) if lines_movers else "No price data yet.", "inline": False},
            ],
            "footer": {"text": "Data refreshes every 5 min · pharma-edge.onrender.com"},
        }
        return _send_embed(settings.discord_webhook_briefing, embed)
    except Exception as exc:
        logger.error("Morning briefing failed: %s", exc)
        return False
    finally:
        db.close()


def send_evening_briefing() -> bool:
    """🌙 Daily wrap-up — movers, upcoming watchlist."""
    from app.models.database import SessionLocal, Ticker, CatalystEvent, PriceSnapshot

    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        tomorrow = now + datetime.timedelta(days=1)

        # ── Tomorrow's events ──
        tomorrow_events = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date >= now, CatalystEvent.event_date < tomorrow + datetime.timedelta(days=1))
            .order_by(CatalystEvent.event_date)
            .all()
        )

        # ── Biggest movers today ──
        top_gainers = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.change_percent.isnot(None))
            .order_by(PriceSnapshot.change_percent.desc())
            .limit(3)
            .all()
        )
        top_losers = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.change_percent.isnot(None))
            .order_by(PriceSnapshot.change_percent.asc())
            .limit(3)
            .all()
        )

        lines_tomorrow = []
        for ev in tomorrow_events[:5]:
            lines_tomorrow.append(f"• **${ev.ticker}** — {ev.title}")

        lines_gainers = []
        for s in top_gainers:
            lines_gainers.append(f"• **${s.ticker}** +{s.change_percent:.2f}%")
        lines_losers = []
        for s in top_losers:
            lines_losers.append(f"• **${s.ticker}** {s.change_percent:.2f}%")

        embed = {
            "title": f"🌙 PharmaEdge Market Wrap | {_TODAY}",
            "color": 0x6366f1,
            "fields": [
                {"name": "📈 Top Gainers", "value": "\n".join(lines_gainers) if lines_gainers else "—", "inline": True},
                {"name": "📉 Top Losers", "value": "\n".join(lines_losers) if lines_losers else "—", "inline": True},
                {"name": "📅 Tomorrow's Watchlist", "value": "\n".join(lines_tomorrow) if lines_tomorrow else "No events scheduled.", "inline": False},
                {"name": "🔗 Links", "value": f"[📊 Dashboard]({_dashboard_link()}) · [Yahoo Finance](https://finance.yahoo.com)", "inline": False},
            ],
            "footer": {"text": "pharma-edge.onrender.com"},
        }
        return _send_embed(settings.discord_webhook_briefing, embed)
    except Exception as exc:
        logger.error("Evening briefing failed: %s", exc)
        return False
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# Legacy: generic send (kept for backward compat)
# ═══════════════════════════════════════════════════════════════════════════

def send_alert(
    ticker: str,
    company: str,
    title: str,
    event_type: str,
    event_date: str,
    days_until: int,
    impact: str,
    description: str = "",
) -> bool:
    """Legacy send — tries the new high-impact channel first, falls back to old webhook."""
    ok = send_high_impact_alert(ticker, company, title, event_type, event_date, days_until, impact, description)
    if not ok and settings.discord_webhook_url:
        # Fall back to the original single webhook URL
        embed = {
            "title": f"🔔 {ticker} — {title}",
            "description": (description.strip()[:500] if description else None),
            "color": _impact_color(impact),
            "fields": [
                {"name": "Company", "value": company, "inline": True},
                {"name": "Date", "value": event_date, "inline": True},
                {"name": "Countdown", "value": f"{days_until} day(s)", "inline": True},
                {"name": "Impact", "value": impact, "inline": True},
            ],
            "url": _yahoo_link(ticker),
            "footer": {"text": "Pharma Catalyst Alert System"},
        }
        embed["fields"].append(
            {"name": "Links", "value": f"[📈 Yahoo Finance]({_yahoo_link(ticker)}) · [📊 Dashboard]({_dashboard_link()})", "inline": False}
        )
        return _send_embed(settings.discord_webhook_url, embed)
    return ok
