"""Pharma news feed — fetches latest articles from major biotech news RSS feeds.

Articles are deduplicated by link URL and pushed to the ``#news-feed``
Discord channel every 15 minutes.
"""

import datetime
import logging
import re

import feedparser

from app.config import settings

logger = logging.getLogger(__name__)

# ── RSS feed sources ───────────────────────────────────────────────────────

FEEDS = [
    ("Fierce Biotech", "https://www.fiercebiotech.com/rss/xml"),
    ("Fierce Pharma", "https://www.fiercepharma.com/rss/xml"),
    ("GlobeNewswire (Biotech)", "https://www.globenewswire.com/RssFeed/industry/8/feed"),
]

# How many recent entries to check per feed (avoid re-processing old items)
_MAX_ENTRIES = 10

# In-memory dedup set — stores article URLs seen since the last restart.
# A small set is fine because articles older than a few hours won't show
# up in the top-N of the feed anyway.
_seen_urls: set[str] = set()


def _fetch_feed(name: str, url: str) -> list[dict]:
    """Parse one RSS feed and return entries with title, url, source, summary."""
    entries = []
    try:
        parsed = feedparser.parse(url)
        for entry in parsed.entries[: _MAX_ENTRIES]:
            link = (entry.get("link") or "").strip()
            if not link or link in _seen_urls:
                continue

            title_raw = (entry.get("title") or "Untitled").strip()
            title = re.sub(r"<[^>]+>", "", title_raw).strip()
            # Strip HTML tags from summary
            summary_raw = entry.get("summary") or entry.get("description") or ""
            summary = re.sub(r"<[^>]+>", " ", summary_raw).strip()[:300]

            # Published date (fall back to now if missing)
            pub_parsed = entry.get("published_parsed")
            pub_date = datetime.datetime(*pub_parsed[:6]) if pub_parsed else datetime.datetime.utcnow()

            entries.append({
                "title": title,
                "url": link,
                "source": name,
                "summary": summary,
                "published": pub_date,
            })
    except Exception as exc:
        logger.warning("RSS feed %s (%s): %s", name, url, exc)

    return entries


def run_news_feed():
    """Fetch biotech RSS feeds and push new articles to Discord.

    Called by APScheduler every 15 minutes.
    """
    if not settings.discord_webhook_news:
        logger.debug("News feed disabled — DISCORD_WEBHOOK_NEWS not set")
        return

    from app.services.notifier import send_news_article

    total_new = 0

    for feed_name, feed_url in FEEDS:
        articles = _fetch_feed(feed_name, feed_url)
        for art in articles:
            # Dedup by URL
            if art["url"] in _seen_urls:
                continue
            _seen_urls.add(art["url"])

            ok = send_news_article(
                title=art["title"],
                url=art["url"],
                source=art["source"],
                summary=art["summary"],
            )
            if ok:
                total_new += 1
            else:
                logger.warning("Failed to send news article: %s", art["title"][:60])

    if total_new:
        logger.info("News feed: %d new article(s) sent", total_new)
    else:
        logger.debug("News feed: no new articles")
