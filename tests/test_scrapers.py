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


# ── Federal Register: allow_past (historical AdCom backfill) ─────────────────

_FR_CAPR_DOC = {
    "document_number": "2026-13096",
    "title": "Cellular, Tissue, and Gene Therapies Advisory Committee; Notice of Meeting; "
             "Establishment of a Public Docket; Request for Comments-Biologics License "
             "Application (BLA) 125842 From Capricor, Inc. for Deramiocel",
    "abstract": "The Food and Drug Administration (FDA) announces a public meeting of the "
                 "Cellular, Tissue, and Gene Therapies Advisory Committee to discuss BLA 125842 "
                 "From Capricor, Inc. for Deramiocel.",
    "html_url": "https://www.federalregister.gov/documents/2026/06/29/2026-13096/x",
    "publication_date": "2026-06-29",
}
_FR_CAPR_BODY = ("DATES: The meeting will be held on July 29, 2026, from 9:30 a.m. to 4:50 p.m. "
                 "Eastern Time. The agency is holding this meeting to discuss BLA 125842 "
                 "From Capricor, Inc. for Deramiocel. ADDRESSES: See below.")


def test_federal_register_doc_to_events_allow_past():
    """A past AdCom notice converts to an event with allow_past=True."""
    import scrapers.federal_register as fr

    events = fr._doc_to_events(_FR_CAPR_DOC, _FR_CAPR_BODY, {"CAPR": ["Capricor Therapeutics"]},
                               allow_past=True)
    assert len(events) == 1
    ev = events[0]
    assert ev["ticker"] == "CAPR"
    assert ev["event_type"] == "REGULATORY"
    assert ev["event_date"] == datetime.datetime(2026, 7, 29)
    assert ev["external_id"] == "FR-2026-13096"
    assert ev["impact_level"] == "High"
    assert ev["verified"] is True
    assert "FDA Advisory Committee" in ev["title"]
    assert "Source: Federal Register" in ev["description"]


def test_federal_register_doc_to_events_default_drops_past():
    """Without allow_past the forward pipeline still drops past meetings."""
    import scrapers.federal_register as fr

    assert fr._doc_to_events(_FR_CAPR_DOC, _FR_CAPR_BODY, {"CAPR": ["Capricor Therapeutics"]}) == []


# ── ClinicalTrials.gov event date: results-first-posted wins ─────────────────

def _study_dict(status_mod: dict) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT03569293", "briefTitle": "A Study of Upadacitinib"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "AbbVie Inc."}},
            "statusModule": status_mod,
            "designModule": {"phases": ["PHASE3"]},
            "conditionsModule": {"conditions": ["Atopic Dermatitis"]},
            "armsInterventionsModule": {"interventions": [{"name": "Upadacitinib"}]},
            "descriptionModule": {"briefSummary": "A Phase 3 study."},
        }
    }


def test_study_to_event_prefers_results_first_posted(seed_tickers, db):
    """The real catalyst is the data release — results-first-posted wins."""
    import datetime
    import scrapers.clinical_trials as ct
    from app.models.database import Ticker

    from scrapers.company_map import seed_aliases
    seed_aliases()
    ticker = db.query(Ticker).filter(Ticker.ticker == "ABBV").first()
    study = _study_dict({
        "resultsFirstPostDateStruct": {"date": "2022-02-03", "type": "ACTUAL"},
        "primaryCompletionDateStruct": {"date": "2021-01-06", "type": "ACTUAL"},
    })
    ev = ct._study_to_event(study, "ABBV", ticker.id, min_event_date=datetime.datetime(2020, 1, 1))
    assert ev is not None
    assert ev["event_date"] == datetime.datetime(2022, 2, 3)
    assert "results first posted" in ev["description"]
    assert "estimated primary completion" not in ev["description"]


def test_study_to_event_falls_back_to_completion(seed_tickers, db):
    """No results posted yet → the (estimated) completion date stays."""
    import datetime
    import scrapers.clinical_trials as ct
    from app.models.database import Ticker

    from scrapers.company_map import seed_aliases
    seed_aliases()
    ticker = db.query(Ticker).filter(Ticker.ticker == "ABBV").first()
    study = _study_dict({"primaryCompletionDateStruct": {"date": "2026-12-01", "type": "ESTIMATED"}})
    ev = ct._study_to_event(study, "ABBV", ticker.id)
    assert ev is not None
    assert ev["event_date"] == datetime.datetime(2026, 12, 1)
    assert "estimated primary completion" in ev["description"]


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
