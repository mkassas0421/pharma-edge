"""NCT matching: noise words, 50% threshold, subsidiary aliases, collaborators."""

from scrapers.company_map import seed_aliases, matches_ticker


def test_lilly_false_negative_fixed(seed_tickers, db):
    """'Eli Lilly Research Laboratories' now matches LLY (was 50% -> rejected)."""
    seed_aliases()  # generates base + subsidiary aliases in the DB
    assert matches_ticker("LLY", "Eli Lilly and Company")
    assert matches_ticker("LLY", "Eli Lilly Research Laboratories")
    assert matches_ticker("LLY", "Lilly USA")  # subsidiary alias


def test_subsidiary_aliases(seed_tickers, db):
    seed_aliases()
    assert matches_ticker("BMY", "Celgene")
    assert matches_ticker("BMY", "Bristol Myers Squibb Research")


def test_single_token_company(seed_tickers, db):
    seed_aliases()
    assert matches_ticker("CRIS", "Curis Inc.")
    assert not matches_ticker("CRIS", "Curium Pharma")


def test_negatives(seed_tickers, db):
    seed_aliases()
    assert not matches_ticker("LLY", "Novartis AG")
    assert not matches_ticker("LLY", "Eli Whitney Industries")
    assert not matches_ticker("ABBV", "Merck & Co.")


def test_collaborator_match(seed_tickers, db):
    """CRO-led study with the pharma company as collaborator must match."""
    import datetime

    seed_aliases()  # LLY needs aliases in the DB to match

    from scrapers.clinical_trials import _study_to_event

    future = (datetime.datetime.utcnow() + datetime.timedelta(days=60)).strftime("%Y-%m-%d")

    def make_study(sponsor, collabs):
        scm = {"leadSponsor": {"name": sponsor}}
        if collabs:
            scm["collaborators"] = [{"name": c} for c in collabs]
        return {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000099", "briefTitle": "Study of Drug X"},
                "sponsorCollaboratorsModule": scm,
                "statusModule": {"overallStatus": "RECRUITING",
                                 "primaryCompletionDateStruct": {"date": future}},
                "designModule": {"phases": ["PHASE2"]},
                "conditionsModule": {"conditions": ["Lung Cancer"]},
                "armsInterventionsModule": {"interventions": [{"name": "DrugX"}]},
                "descriptionModule": {"briefSummary": "A trial."},
            }
        }

    ev = _study_to_event(make_study("Clinical Research Org Inc", ["Eli Lilly and Company"]), "LLY", 1)
    assert ev is not None
    assert ev["source"] == "clinicaltrials_gov"
    assert ev["verified"] is True

    ev2 = _study_to_event(make_study("Clinical Research Org Inc", ["Novartis AG"]), "LLY", 1)
    assert ev2 is None


def test_old_study_rejected(seed_tickers, db):
    import datetime

    from scrapers.clinical_trials import _study_to_event

    past = (datetime.datetime.utcnow() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000101", "briefTitle": "Old Study"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Eli Lilly and Company"}},
            "statusModule": {"overallStatus": "COMPLETED",
                             "primaryCompletionDateStruct": {"date": past}},
            "designModule": {"phases": ["PHASE3"]},
            "conditionsModule": {"conditions": ["Cancer"]},
            "armsInterventionsModule": {"interventions": [{"name": "OldDrug"}]},
            "descriptionModule": {"briefSummary": "Old trial."},
        }
    }
    assert _study_to_event(study, "LLY", 1) is None
