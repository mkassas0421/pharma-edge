"""Notification service — sends alerts via Telegram Bot or Discord Webhook.

Messages include Yahoo Finance chart links and a link back to the dashboard.
"""

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _yahoo_link(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{ticker}"

def _dashboard_link() -> str:
    return settings.base_url


# ── Telegram ────────────────────────────────────────────────────────────────

def send_telegram(
    ticker: str,
    company: str,
    title: str,
    event_type: str,
    event_date: str,
    days_until: int,
    impact: str,
    description: str = "",
) -> bool:
    """Send a richly formatted HTML message to the configured Telegram chat."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        logger.warning("Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return False

    lines = [
        f"<b>🔔 {ticker}</b> — {title}",
        "",
        f"🏢 {company}",
        f"📅 {event_date}  |  <b>{days_until} day(s)</b>",
        f"⚡ Impact: {impact}",
    ]
    if description:
        preview = description.strip()[:250]
        lines.append("")
        lines.append(preview)

    lines.append("")
    lines.append(f'<a href="{_yahoo_link(ticker)}">📈 Yahoo Finance</a>  |  <a href="{_dashboard_link()}">📊 Dashboard</a>')

    payload = {
        "chat_id": chat_id,
        "text": "\n".join(lines),
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
            resp.raise_for_status()
            logger.info("Telegram alert sent OK for %s", ticker)
            return True
    except Exception as exc:
        logger.error("Telegram send failed for %s: %s", ticker, exc)
        return False


# ── Discord ─────────────────────────────────────────────────────────────────

def send_discord(
    ticker: str,
    company: str,
    title: str,
    event_type: str,
    event_date: str,
    days_until: int,
    impact: str,
    description: str = "",
) -> bool:
    """Send a rich embed to the configured Discord webhook."""
    webhook_url = settings.discord_webhook_url
    if not webhook_url:
        logger.warning("Discord not configured — set DISCORD_WEBHOOK_URL")
        return False

    color_map = {"High": 0x10b981, "Medium": 0xf59e0b, "Low": 0x6b7280}
    color = color_map.get(impact, 0x6b7280)

    embed = {
        "title": f"🔔 {ticker} — {title}",
        "description": (description.strip()[:500] if description else None),
        "color": color,
        "fields": [
            {"name": "Company", "value": company, "inline": True},
            {"name": "Date", "value": event_date, "inline": True},
            {"name": "Countdown", "value": f"{days_until} day(s)", "inline": True},
            {"name": "Impact", "value": impact, "inline": True},
        ],
        "url": _yahoo_link(ticker),
        "footer": {"text": "Pharma Catalyst Alert System"},
    }

    # Add links field separately (buttons aren't available in simple webhooks)
    link_text = f"[📈 Yahoo Finance]({_yahoo_link(ticker)}) · [📊 Dashboard]({_dashboard_link()})"
    embed["fields"].append({"name": "Links", "value": link_text, "inline": False})

    payload = {"embeds": [embed]}

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
            logger.info("Discord alert sent OK for %s", ticker)
            return True
    except Exception as exc:
        logger.error("Discord send failed for %s: %s", ticker, exc)
        return False


# ── Unified alert ───────────────────────────────────────────────────────────

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
    """Try Telegram, then Discord. Returns True if at least one succeeded."""
    sent_ok = False

    if settings.telegram_bot_token and settings.telegram_chat_id:
        if send_telegram(ticker, company, title, event_type, event_date, days_until, impact, description):
            sent_ok = True

    if settings.discord_webhook_url:
        if send_discord(ticker, company, title, event_type, event_date, days_until, impact, description):
            sent_ok = True

    if not sent_ok:
        logger.warning("No notification channel configured — set Telegram or Discord creds in .env")

    return sent_ok
