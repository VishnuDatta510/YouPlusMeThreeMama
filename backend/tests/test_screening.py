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
    assert out == {"label": "exclude", "reason": "case report"}


def test_simulation():
    out = screen(rec(abstract="An in silico analysis of dosing."), ALL)
    assert out == {"label": "exclude", "reason": "simulation study (keyword: in silico)"}


def test_maybe_without_signals_and_include_otherwise():
    assert screen(rec(abstract="", mesh_terms=[]), ALL)["label"] == "maybe"
    assert screen(rec(), ALL)["label"] == "include"


def test_criteria_are_configurable():
    assert screen(rec(language="fre"), ["case_report"])["label"] == "include"
