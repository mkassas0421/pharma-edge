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


# ── Link helpers ─────────────────────────────────────────────────────────────

def _yahoo_link(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}"


def _dashboard_link() -> str:
    return settings.base_url


def _links_field(ticker: str, extra: str = "") -> dict:
    """Standard links field appended to every embed."""
    parts = [
        f"[📈 Yahoo Finance]({_yahoo_link(ticker)})",
        f"[📊 Dashboard]({_dashboard_link()})",
    ]
    if extra:
        parts.append(extra)
    return {"name": "Links", "value": " · ".join(parts), "inline": False}


# ── Colour helpers ───────────────────────────────────────────────────────────

def _impact_color(impact: str) -> int:
    return {"High": 0x10b981, "Medium": 0xf59e0b, "Low": 0x6b7280}.get(impact, 0x6b7280)


def _form_color(form_type: str) -> int:
    return {"8-K": 0x3b82f6, "13D": 0xf59e0b, "13G": 0xf59e0b, "S-1": 0xef4444, "S-3": 0xef4444}.get(form_type, 0x6b7280)


# ── Low-level: send a raw embed to any webhook URL ──────────────────────────

def _send_embed(webhook_url: str, embed: dict, mention_everyone: bool = False) -> bool:
    """Push a Discord embed to *webhook_url*. Returns True on success."""
    if not webhook_url:
        return False
    payload: dict = {"embeds": [embed]}
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


# ── Shared embed helpers ─────────────────────────────────────────────────────

def _catalyst_embed(
    ticker: str,
    title: str,
    description: str | None,
    color: int,
    fields: list[dict],
    footer_text: str,
    url: str | None = None,
    mention_everyone: bool = False,
    extra_link: str = "",
) -> tuple[dict, bool]:
    """Build a standard catalyst embed and return (embed, mention_everyone).

    Callers are responsible for truncating *description* to the channel's
    preferred length before passing it in.
    """
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields + [_links_field(ticker, extra=extra_link)],
        "footer": {"text": footer_text},
    }
    if url:
        embed["url"] = url
    return embed, mention_everyone


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
    embed, mention = _catalyst_embed(
        ticker=ticker,
        title=f"🔔 {ticker} — {title}",
        description=(description.strip()[:500] if description else None),
        color=_impact_color(impact),
        fields=[
            {"name": "Company", "value": company, "inline": True},
            {"name": "Date", "value": event_date, "inline": True},
            {"name": "Countdown", "value": f"{days_until} day(s)", "inline": True},
            {"name": "Impact", "value": impact, "inline": True},
        ],
        footer_text="Pharma Catalyst Alert System",
        url=_yahoo_link(ticker),
        mention_everyone=True,
    )
    return _send_embed(settings.discord_webhook_high_impact, embed, mention_everyone=mention)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #sec-filings-live
# ═══════════════════════════════════════════════════════════════════════════

def send_sec_filing(ticker: str, company: str, form_type: str, description: str, url: str = "") -> bool:
    """Real-time SEC filing alert (8-K, 13D, S-1, …)."""
    embed, mention = _catalyst_embed(
        ticker=ticker,
        title=f"📄 {ticker} — {form_type} Filing",
        description=description[:1000] if description else None,
        color=_form_color(form_type),
        fields=[
            {"name": "Company", "value": company, "inline": True},
            {"name": "Form", "value": form_type, "inline": True},
        ],
        footer_text=f"SEC EDGAR · {_TODAY}",
        url=url or _yahoo_link(ticker),
    )
    return _send_embed(settings.discord_webhook_sec_live, embed, mention_everyone=mention)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #clinical-trials-updates
# ═══════════════════════════════════════════════════════════════════════════

def send_clinical_change(ticker: str, company: str, drug: str, change_desc: str, nct_id: str = "") -> bool:
    """Notify when a trial transitions phase or status."""
    extra_link = f"[🔬 Trial](https://clinicaltrials.gov/study/{nct_id})" if nct_id else ""
    embed, mention = _catalyst_embed(
        ticker=ticker,
        title=f"🧪 {ticker} — {drug}",
        description=change_desc[:500],
        color=0x8b5cf6,
        fields=[
            {"name": "Company", "value": company, "inline": True},
            {"name": "NCT ID", "value": nct_id or "—", "inline": True},
        ],
        footer_text=f"ClinicalTrials.gov · {_TODAY}",
        extra_link=extra_link,
    )
    return _send_embed(settings.discord_webhook_clinical, embed)


# ═══════════════════════════════════════════════════════════════════════════
# CHANNEL: #daily-biotech-briefing
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_briefing_data():
    """Query the DB for today's events, this week's high-impact events, and top movers."""
    from app.models.database import SessionLocal, Ticker, CatalystEvent, PriceSnapshot

    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        today_end = now + datetime.timedelta(days=1)
        week_end = now + datetime.timedelta(days=7)

        today_events = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date >= now, CatalystEvent.event_date < today_end)
            .order_by(CatalystEvent.event_date)
            .all()
        )
        week_high = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date >= now, CatalystEvent.event_date < week_end, CatalystEvent.impact_level == "High")
            .order_by(CatalystEvent.event_date)
            .all()
        )
        snapshots = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.change_percent.isnot(None))
            .order_by(PriceSnapshot.change_percent.desc())
            .limit(5)
            .all()
        )
        return now, today_events, week_high, snapshots
    finally:
        db.close()


def _format_briefing_lines(today_events, week_high, snapshots, db):
    """Format the three sections of the briefing embed."""
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

    return lines_today, lines_week, lines_movers


def send_morning_briefing() -> bool:
    """🌅 Today's radar — PDUFA dates, top catalysts, pre-market movers.

    Called by the cron scheduler at 08:30 local time.
    """
    from app.models.database import SessionLocal, Ticker

    db = SessionLocal()
    try:
        now, today_events, week_high, snapshots = _fetch_briefing_data()
        lines_today, lines_week, lines_movers = _format_briefing_lines(today_events, week_high, snapshots, db)

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
    from app.models.database import SessionLocal, CatalystEvent, PriceSnapshot

    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        tomorrow = now + datetime.timedelta(days=1)

        tomorrow_events = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date >= now, CatalystEvent.event_date < tomorrow + datetime.timedelta(days=1))
            .order_by(CatalystEvent.event_date)
            .all()
        )
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

        lines_tomorrow = [f"• **${ev.ticker}** — {ev.title}" for ev in tomorrow_events[:5]]
        lines_gainers = [f"• **${s.ticker}** +{s.change_percent:.2f}%" for s in top_gainers]
        lines_losers = [f"• **${s.ticker}** {s.change_percent:.2f}%" for s in top_losers]

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
# CHANNEL: #news-feed  (60-min pharma news)
# ═══════════════════════════════════════════════════════════════════════════

def send_news_article(title: str, url: str, source: str, summary: str = "") -> bool:
    """Push a pharma news article to the #news-feed Discord channel."""
    embed = {
        "title": title[:256],
        "url": url,
        "description": (summary[:500] if summary else None),
        "color": 0x0ea5e9,
        "fields": [
            {"name": "Source", "value": source, "inline": True},
        ],
        "footer": {"text": f"PharmaEdge News · {datetime.datetime.utcnow().strftime('%b %d, %H:%M')} UTC"},
    }
    return _send_embed(settings.discord_webhook_news, embed)


# ═══════════════════════════════════════════════════════════════════════════
# Legacy: generic alert (tries high-impact channel, falls back to legacy webhook)
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
        embed, mention = _catalyst_embed(
            ticker=ticker,
            title=f"🔔 {ticker} — {title}",
            description=(description.strip()[:500] if description else None),
            color=_impact_color(impact),
            fields=[
                {"name": "Company", "value": company, "inline": True},
                {"name": "Date", "value": event_date, "inline": True},
                {"name": "Countdown", "value": f"{days_until} day(s)", "inline": True},
                {"name": "Impact", "value": impact, "inline": True},
            ],
            footer_text="Pharma Catalyst Alert System",
            url=_yahoo_link(ticker),
        )
        return _send_embed(settings.discord_webhook_url, embed, mention_everyone=mention)
    return ok
