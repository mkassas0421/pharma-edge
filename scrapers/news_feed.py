"""Pharma news feed — fetches latest articles from major biotech news RSS feeds.

Articles are deduplicated by link URL and pushed to the ``#news-feed``
Discord channel every 60 minutes. Seen URLs persist in the
``scraper_dedup`` table so a restart never re-notifies old articles.
"""

import datetime
import logging
import re

import feedparser

from app.config import settings
from app.models.database import SessionLocal
from app.utils.collections import BoundedSet

logger = logging.getLogger(__name__)

# ── RSS feed sources ───────────────────────────────────────────────────────

FEEDS = [
    ("Fierce Biotech", "https://www.fiercebiotech.com/rss/xml"),
    ("Fierce Pharma", "https://www.fiercepharma.com/rss/xml"),
    ("GlobeNewswire (Biotech)", "https://www.globenewswire.com/RssFeed/industry/8/feed"),
]

_MAX_ENTRIES = 6               # recent entries per feed per run
_DEDUP_SOURCE = "news_feed"
_seen_urls = BoundedSet(maxsize=2000)


def _fetch_feed(name: str, url: str, db) -> list[dict]:
    """Parse one RSS feed and return entries with title, url, source, summary.

    Entries already seen (in-memory cache or persisted dedup) are skipped.
    """
    from scrapers.dedup import is_seen

    entries = []
    try:
        parsed = feedparser.parse(url)
        for entry in parsed.entries[:_MAX_ENTRIES]:
            link = (entry.get("link") or "").strip()
            if not link or is_seen(db, _DEDUP_SOURCE, link, _seen_urls):
                continue

            title_raw = (entry.get("title") or "Untitled").strip()
            title = re.sub(r"<[^>]+>", "", title_raw).strip()
            summary_raw = entry.get("summary") or entry.get("description") or ""
            summary = re.sub(r"<[^>]+>", " ", summary_raw).strip()[:300]

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

    Called by APScheduler every 60 minutes.
    """
    if not settings.discord_webhook_news:
        logger.debug("News feed disabled — DISCORD_WEBHOOK_NEWS not set")
        return

    from app.services.notifier import send_news_article
    from scrapers.dedup import is_seen, mark_seen, prune_old

    db = SessionLocal()
    try:
        total_new = 0

        for feed_name, feed_url in FEEDS:
            articles = _fetch_feed(feed_name, feed_url, db)
            for art in articles:
                if is_seen(db, _DEDUP_SOURCE, art["url"], _seen_urls):
                    continue  # persisted by an earlier run
                mark_seen(db, _DEDUP_SOURCE, art["url"], _seen_urls)

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

        # Persist dedup markers + prune old ones (single transaction)
        prune_old(db, _DEDUP_SOURCE)
        db.commit()

        if total_new:
            logger.info("News feed: %d new article(s) sent", total_new)
        else:
            logger.debug("News feed: no new articles")
    except Exception as exc:
        logger.error("News feed error: %s", exc)
        db.rollback()
    finally:
        db.close()
