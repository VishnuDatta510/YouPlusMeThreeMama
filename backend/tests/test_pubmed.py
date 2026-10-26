from pathlib import Path

from app.services.pubmed import parse_efetch

FIXTURE = Path(__file__).parent / "fixtures" / "efetch_sample.xml"


def test_parse_fixture():
    records = parse_efetch(FIXTURE.read_bytes())
    assert len(records) == 16
    by_pmid = {r["pmid"]: r for r in records}

    rct = by_pmid["42815506"]
    assert rct["title"].startswith("Cardiovascular safety of orforglipron versus insulin glargine")
    assert rct["doi"] == "10.1016/S0140-6736(26)01865-9"
    assert rct["language"] == "eng"
    assert "Randomized Controlled Trial" in rct["publication_types"]
    assert "Humans" in rct["mesh_terms"]
    assert rct["year"] and rct["journal"] and rct["authors"] and rct["abstract"]
    assert rct["authors"][0].startswith(rct["first_author"])

    assert "Case Reports" in by_pmid["42903999"]["publication_types"]
    assert by_pmid["42533732"]["language"] == "fre"
    assert by_pmid["41987548"]["doi"] is None
    assert "Animals" in by_pmid["42861459"]["mesh_terms"]


def test_pubmed_field_tags_become_europe_pmc_fields():
    from datetime import date

    from app.services.europepmc import build_query, translate

    # Untranslated, "trial[pt]" made Europe PMC drop the date clause and return papers from any year.
    q = build_query("metformin AND randomized controlled trial[pt]", date(2024, 1, 1), date(2024, 3, 31))
    assert (
        q
        == '(metformin AND PUB_TYPE:"randomized controlled trial") AND (FIRST_PDATE:[2024-01-01 TO 2024-03-31])'
    )
    assert translate('"type 2 diabetes"[Title/Abstract] AND (metformin[ti] OR x[mh:noexp]) NOT y[zz]') == (
        'TITLE_ABS:"type 2 diabetes" AND (TITLE:"metformin" OR MESH:"x") NOT "y"'
    )
    assert translate("plain AND query") == "plain AND query"
