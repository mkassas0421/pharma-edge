"""Scraper internals with mocked network: SEC Atom parse, news RSS parse."""

import datetime

from app.models.database import Ticker

# ── SEC filings feed (mocked httpx) ────────────────────────────────────────

_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>8-K - Current report - CIK 0000320193 (Eli Lilly and Company) Ticker: LLY</title>
    <summary>Filed: 2026-08-01 AccNo: 0000320193-26-000045</summary>
    <link href="/Archives/edgar/data/320193/000032019326000045/"/>
  </entry>
  <entry>
    <title>8-K - Current report - CIK 0001650106 (Some Unknown Company)</title>
    <summary>Filed: 2026-08-01 AccNo: 0001650106-26-000099</summary>
    <link href="/Archives/edgar/data/1650106/000165010626000099/"/>
  </entry>
</feed>
"""


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, url):
        return _FakeResponse(_ATOM_XML)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_sec_feed_parses_and_matches(seed_tickers, db, monkeypatch):
    import scrapers.sec_filings as sec

    monkeypatch.setattr(sec.httpx, "Client", _FakeClient)

    entries = sec._fetch_feed("8-K")
    assert len(entries) == 2
    assert entries[0]["accession"] == "0000320193-26-000045"
    assert entries[0]["ticker"] == "LLY"
    assert entries[1]["ticker"] is None

    # First run: the LLY filing is new -> marked seen + persisted
    sec.run_sec_feed()
    from app.models.database import ScraperDedup
    db.expire_all()
    assert db.query(ScraperDedup).filter_by(
        source="sec_filings", identifier="0000320193-26-000045"
    ).count() == 1

    # Second run (same entries): deduped via cache, no duplicates in DB
    sec.run_sec_feed()
    assert db.query(ScraperDedup).filter_by(
        source="sec_filings", identifier="0000320193-26-000045"
    ).count() == 1


# ── News feed (mocked feedparser) ──────────────────────────────────────────

class _FakeParsed:
    def __init__(self, entries):
        self.entries = entries


def test_news_feed_parses_and_dedups(seed_tickers, db, monkeypatch):
    import scrapers.news_feed as news

    published = datetime.datetime(2026, 8, 1, 12, 0, 0)
    entries = [
        {"link": "https://fiercebiotech.com/a", "title": "<b>First article</b>",
         "summary": "A summary text", "published_parsed": published.timetuple()},
        {"link": "https://fiercebiotech.com/b", "title": "Second article",
         "summary": "More news", "published_parsed": published.timetuple()},
    ]
    monkeypatch.setattr(news.feedparser, "parse", lambda url: _FakeParsed(entries))
    monkeypatch.setattr(news.settings, "discord_webhook_news", "https://discord.invalid/hook")

    # Capture what would be sent; send_news_article makes real HTTP -> stub it
    sent = []

    def _fake_send_news_article(title, url, source, summary):
        sent.append((title, url))
        return True

    monkeypatch.setattr("app.services.notifier.send_news_article", _fake_send_news_article)

    news.run_news_feed()
    assert len(sent) == 2
    assert sent[0][0] == "First article"  # HTML tags stripped

    # Second run: same entries -> nothing new sent
    news.run_news_feed()
    assert len(sent) == 2


def test_news_feed_disabled_without_webhook(seed_tickers, db, monkeypatch):
    import scrapers.news_feed as news

    monkeypatch.setattr(news.settings, "discord_webhook_news", "")
    # Must return early without touching anything (no error)
    assert news.run_news_feed() is None


# ── PDUFA scraper dedup (regression: autoflush=False blinded the within-run check) ──

def test_pdufa_one_filing_documents_insert_once(seed_tickers, db, monkeypatch):
    """One 8-K with several documents announcing the same date → ONE event."""
    import datetime
    import scrapers.pdufa as pdufa
    from app.models.database import CatalystEvent

    now = datetime.datetime.utcnow()
    target = now + datetime.timedelta(days=21)  # inside the 30-day window

    # Two documents in one filing, both carrying the same PDUFA date
    docs = [
        {"name": "pdufa_ex99.htm", "url": "https://example.com/ex99"},
        {"name": "pdufa_8k.htm", "url": "https://example.com/main"},
    ]
    monkeypatch.setattr(pdufa, "_get_filing_files", lambda cik, adsh: docs)
    monkeypatch.setattr(pdufa, "_check_pdufa", lambda url: {"date": target, "drug": "Deramiocel"})

    ticker = db.query(Ticker).first()
    n1, u1 = pdufa._process_filing(ticker.ticker, ticker.id, "0000320193",
                                   "0000320193-26-000001", db, now)
    assert (n1, u1) == (1, 0)
    count = (db.query(CatalystEvent)
             .filter(CatalystEvent.ticker == ticker.ticker, CatalystEvent.event_type == "PDUFA")
             .count())
    assert count == 1  # second document must NOT insert again

    # A second filing for the same date updates the existing row, never inserts
    n2, u2 = pdufa._process_filing(ticker.ticker, ticker.id, "0000320193",
                                   "0000320193-26-000002", db, now)
    assert (n2, u2) == (0, 0)  # same date + same title → no change
    count = (db.query(CatalystEvent)
             .filter(CatalystEvent.ticker == ticker.ticker, CatalystEvent.event_type == "PDUFA")
             .count())
    assert count == 1
