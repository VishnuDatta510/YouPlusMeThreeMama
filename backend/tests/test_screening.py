from app.models import Record
from app.services.screening import RULES, screen

ALL = list(RULES)


def rec(**kw):
    base = dict(
        title="Metformin in adults",
        abstract="Adults with diabetes were randomized.",
        language="eng",
        mesh_terms=["Humans", "Metformin"],
        publication_types=["Journal Article"],
    )
    return Record(**{**base, **kw})


def test_non_english():
    assert screen(rec(language="fre"), ALL) == {"label": "exclude", "reason": "non-English (fre)"}


def test_non_human_mesh():
    out = screen(rec(mesh_terms=["Animals", "Mice"]), ALL)
    assert out["label"] == "exclude" and "non-human" in out["reason"]
    assert screen(rec(mesh_terms=["Animals", "Humans"]), ALL)["label"] == "include"


def test_non_human_keyword_fallback_without_mesh():
    out = screen(rec(mesh_terms=[], abstract="Murine models were treated."), ALL)
    assert out == {"label": "exclude", "reason": "non-human (keyword: murine)"}


def test_case_report():
    out = screen(rec(publication_types=["Case Reports", "Journal Article"]), ALL)
    assert out == {"label": "exclude", "reason": "case report (publication type: case reports)"}
    fallback = screen(
        rec(publication_types=[], abstract="We report a case of lactic acidosis in adults."), ALL
    )
    assert fallback["reason"] == "case report (keyword: we report a case)"


def test_language_detected_from_text_when_field_missing():
    french = (
        "Les patients avec un diabète de type 2 ont été traités par la metformine pour une durée de un an"
    )
    assert (
        screen(rec(language="", title="", abstract=french), ALL)["reason"]
        == "non-English (detected from text)"
    )
    english = (
        "Adults with type 2 diabetes were treated with metformin for one year and the outcome was measured"
    )
    assert screen(rec(language="", abstract=english), ALL)["label"] == "include"


def test_secondary_research_and_non_research_types():
    assert "secondary research" in screen(rec(publication_types=["Meta-Analysis"]), ALL)["reason"]
    assert (
        "secondary research"
        in screen(rec(publication_types=[], title="A systematic review of X"), ALL)["reason"]
    )
    assert "not original research" in screen(rec(publication_types=["Editorial"]), ALL)["reason"]
    assert screen(rec(publication_types=["Retracted Publication"]), ALL)["reason"] == "retracted publication"
    assert "protocol" in screen(rec(title="Study protocol for a randomised trial"), ALL)["reason"]


def test_several_reasons_are_all_shown():
    out = screen(rec(language="ger", publication_types=["Case Reports"]), ALL)
    assert out["reason"].count(";") == 1 and "non-English" in out["reason"] and "case report" in out["reason"]


def test_simulation():
    out = screen(rec(abstract="An in silico analysis of dosing."), ALL)
    assert out == {"label": "exclude", "reason": "simulation study (keyword: in silico)"}


def test_maybe_without_signals_and_include_otherwise():
    assert screen(rec(abstract="", mesh_terms=[]), ALL)["label"] == "maybe"
    unclear = screen(
        rec(mesh_terms=[], title="Metformin dosing", abstract="Dosing was safe and effective."), ALL
    )
    assert unclear == {"label": "maybe", "reason": "population unclear: no human participants mentioned"}
    assert screen(rec(), ALL)["label"] == "include"


def test_criteria_are_configurable():
    assert screen(rec(language="fre"), ["case_report"])["label"] == "include"
