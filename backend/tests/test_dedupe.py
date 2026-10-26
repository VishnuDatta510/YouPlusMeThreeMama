import random

from app.services.dedupe import Candidate, find_duplicates, normalize_doi


def rec(id, title="A study", doi=None, pmid=None, year=2020, author="Smith"):
    return Candidate(id=id, pmid=pmid, doi=doi, title=title, year=year, first_author=author)


def test_doi_match_ignores_case_and_prefix():
    assert normalize_doi(" https://doi.org/10.1000/ABC ") == "10.1000/abc"
    matches = find_duplicates(
        [rec(1, "x", doi="10.1000/abc"), rec(2, "totally different", doi="https://doi.org/10.1000/ABC")]
    )
    assert [(m.record_id, m.representative_id, m.method, m.needs_review) for m in matches] == [
        (2, 1, "doi", False)
    ]


def test_pmid_match():
    matches = find_duplicates([rec(1, "x", pmid="123"), rec(2, "y", pmid="123")])
    assert [(m.record_id, m.method) for m in matches] == [(2, "pmid")]


def test_fuzzy_match_thresholds():
    title = "Metformin and cardiovascular outcomes in adults with type 2 diabetes: a randomized trial"
    records = [
        rec(1, title),
        rec(2, title.upper() + "."),  # punctuation/case only → auto
        rec(
            3, "Metformin and cardiovascular outcomes in older adults with type 2 diabetes: a pragmatic trial"
        ),
        rec(4, title, year=2021),  # different year → not compared
        rec(5, title, author="Jones"),  # different first author → not compared
        rec(6, "Something else entirely about insulin pumps"),
    ]
    got = {m.record_id: m for m in find_duplicates(records)}
    assert set(got) == {2, 3}
    assert got[2].method == "fuzzy" and not got[2].needs_review and got[2].representative_id == 1
    assert 85 <= got[3].score < 95 and got[3].needs_review


def test_deterministic_regardless_of_input_order():
    records = [rec(i, f"Trial of drug {i % 3} in adults", doi=f"10.1/{i % 4}") for i in range(1, 30)]
    first = find_duplicates(records)
    shuffled = records[:]
    random.Random(42).shuffle(shuffled)
    assert find_duplicates(shuffled) == first == find_duplicates(records)
    assert all(m.representative_id < m.record_id for m in first)


def test_later_report_of_the_same_study_is_not_a_duplicate():
    title = "Metformin and cardiovascular outcomes in adults with type 2 diabetes"

    def c(id, **kw):
        return Candidate(
            **{
                "id": id,
                "pmid": None,
                "doi": None,
                "title": title,
                "year": 2020,
                "first_author": "Smith",
                **kw,
            }
        )

    # Same title, different journal (conference abstract vs journal paper) or pages: a further report.
    assert find_duplicates([c(1, journal="Diabetes Care"), c(2, journal="Circulation Supplement")]) == []
    assert find_duplicates([c(1, pages="101-9"), c(2, pages="e2001")]) == []
    assert find_duplicates([c(1, doi="10.1/a"), c(2, doi="10.1/b")]) == []
    # The same record from two sources, with metadata spelled differently, still matches.
    same = find_duplicates([c(1, journal="The Lancet", pages="101-109"), c(2, journal="Lancet", pages="101")])
    assert [(m.record_id, m.representative_id) for m in same] == [(2, 1)]
