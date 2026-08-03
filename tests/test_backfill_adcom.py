"""backfill_historical_adcom script tests: past AdCom import + reaction capture."""

import datetime

import pytest

from app.models.database import CatalystEvent, EventReaction, Ticker

import scripts.backfill_historical_adcom as backfill


def _capr_doc():
    return {
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


def _capr_body(date_text=("The meeting will be held on July 29, 2026, from 9:30 a.m. to 4:50 p.m. "
                          "Eastern Time. The agency is holding this meeting to discuss BLA 125842 "
                          "From Capricor, Inc. for Deramiocel. ADDRESSES: See below.")):
    return date_text


def _prices(ticker, event_date):
    return {"price_before": 10.0, "price_at_event": 12.0,
            "price_after_1d": 13.0, "price_after_5d": 15.0}


def _stats():
    return {"events": 0, "captured": 0, "failed": 0, "pending": 0, "dupes": 0,
            "no_date": 0, "no_match": 0, "body_fail": 0, "future": 0, "pre_window": 0, "errors": 0}


def _seed_capr(db):
    db.add(Ticker(ticker="CAPR", company_name="Capricor Therapeutics"))
    db.commit()
    from scrapers.company_map import seed_aliases
    seed_aliases()


def test_backfill_imports_past_event_and_captures(db, monkeypatch):
    _seed_capr(db)
    monkeypatch.setattr(backfill, "_fetch_body_xml", lambda url: _capr_body())
    monkeypatch.setattr(backfill, "get_historical_prices", _prices)

    aliases, ticker_ids = backfill._load_alias_maps(db)
    stats = _stats()
    backfill._process_document(db, _capr_doc(), aliases, ticker_ids, stats)
    db.flush()  # the real driver commits per document; verify within this transaction

    event = db.query(CatalystEvent).filter(CatalystEvent.ticker == "CAPR").first()
    assert event is not None
    assert event.ticker_id is not None  # NOT NULL regression — the forward scraper bug
    assert event.event_type == "REGULATORY"
    assert event.event_date == datetime.datetime(2026, 7, 29)
    assert event.external_id == "FR-2026-13096"
    assert event.source == "federal_register"
    assert event.impact_level == "High"
    assert event.verified is True

    reaction = db.query(EventReaction).filter(EventReaction.event_id == event.id).first()
    assert reaction is not None
    assert reaction.status == "captured"
    assert reaction.reaction_1d_pct == pytest.approx((12.0 - 10.0) / 10.0)  # (at_event - before) / before
    assert stats["events"] == 1
    assert stats["captured"] == 1


def test_backfill_same_meeting_dedup(db, monkeypatch):
    _seed_capr(db)
    capr = db.query(Ticker).filter(Ticker.ticker == "CAPR").first()
    # The forward scraper already created this meeting (different FR doc number)
    db.add(CatalystEvent(
        ticker="CAPR", ticker_id=capr.id, title="FDA Advisory Committee — already there",
        event_type="REGULATORY", event_date=datetime.datetime(2026, 7, 29),
        impact_level="High", description="existing", source="federal_register",
        external_id="FR-2026-99999", source_url="https://example.com", verified=True,
    ))
    db.commit()

    monkeypatch.setattr(backfill, "_fetch_body_xml", lambda url: _capr_body())
    monkeypatch.setattr(backfill, "get_historical_prices", _prices)

    aliases, ticker_ids = backfill._load_alias_maps(db)
    stats = _stats()
    backfill._process_document(db, _capr_doc(), aliases, ticker_ids, stats)

    assert db.query(CatalystEvent).filter(CatalystEvent.ticker == "CAPR").count() == 1
    assert stats["dupes"] == 1
    assert stats["events"] == 0


def test_backfill_skips_future_and_pre_window(db, monkeypatch):
    _seed_capr(db)
    aliases, ticker_ids = backfill._load_alias_maps(db)
    stats = _stats()

    future = _capr_body("DATES: The meeting will be held on January 15, 2027. "
                        "The agency will discuss BLA 125842 From Capricor, Inc. "
                        "ADDRESSES: See below.")
    monkeypatch.setattr(backfill, "_fetch_body_xml", lambda url: future)
    backfill._process_document(db, _capr_doc(), aliases, ticker_ids, stats)
    assert stats["future"] == 1  # the forward scraper owns upcoming meetings

    old = _capr_body("DATES: The meeting will be held on January 15, 2019. "
                     "The agency will discuss BLA 125842 From Capricor, Inc. "
                     "ADDRESSES: See below.")
    monkeypatch.setattr(backfill, "_fetch_body_xml", lambda url: old)
    backfill._process_document(db, _capr_doc(), aliases, ticker_ids, stats)
    assert stats["pre_window"] == 1

    assert db.query(CatalystEvent).count() == 0


def test_backfill_no_date_counted(db, monkeypatch):
    _seed_capr(db)
    monkeypatch.setattr(backfill, "_fetch_body_xml", lambda url: "No dates here at all. ADDRESSES: x.")
    aliases, ticker_ids = backfill._load_alias_maps(db)
    stats = _stats()
    backfill._process_document(db, _capr_doc(), aliases, ticker_ids, stats)
    assert stats["no_date"] == 1
    assert stats["events"] == 0
