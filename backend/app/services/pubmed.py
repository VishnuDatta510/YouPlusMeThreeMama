"""NCBI E-utilities client: ESearch, EFetch, and the EFetch XML parser."""

import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from app.config import settings

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# ponytail: process-wide throttle, fine for one backend instance; NCBI limits per IP/key anyway.
_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    interval = 1 / (10 if settings.ncbi_api_key else 3)
    with _lock:
        wait = _last_call + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _call(endpoint: str, params: dict, retries: int = 4) -> httpx.Response:
    params = {**params, "tool": settings.ncbi_tool}
    if settings.ncbi_email:
        params["email"] = settings.ncbi_email
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    for attempt in range(retries):
        _throttle()
        last = attempt == retries - 1
        try:
            r = httpx.post(f"{EUTILS}/{endpoint}", data=params, timeout=30)
        except httpx.TransportError:
            if last:
                raise
        else:
            if r.status_code != 429 and r.status_code < 500:
                return r.raise_for_status()
            if last:
                r.raise_for_status()
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _search_params(term: str, date_from: date | None, date_to: date | None) -> dict:
    params = {"db": "pubmed", "term": term, "retmode": "json"}
    if date_from or date_to:
        params |= {
            "datetype": "pdat",
            "mindate": (date_from or date(1800, 1, 1)).strftime("%Y/%m/%d"),
            "maxdate": (date_to or date(3000, 12, 31)).strftime("%Y/%m/%d"),
        }
    return params


def count(term: str, date_from: date | None = None, date_to: date | None = None) -> int:
    r = _call("esearch.fcgi", {**_search_params(term, date_from, date_to), "rettype": "count"})
    return int(r.json()["esearchresult"]["count"])


def search_ids(term: str, date_from: date | None, date_to: date | None, retmax: int) -> list[str]:
    r = _call("esearch.fcgi", {**_search_params(term, date_from, date_to), "retmax": retmax})
    return r.json()["esearchresult"]["idlist"]


def efetch(pmids: list[str]) -> bytes:
    return _call("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}).content


def _text(el: ET.Element | None) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _year(article: ET.Element, pubmed_article: ET.Element) -> int | None:
    for path, el in (
        ("Journal/JournalIssue/PubDate/Year", article),
        ("Journal/JournalIssue/PubDate/MedlineDate", article),
        ("ArticleDate/Year", article),
        ("PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year", pubmed_article),
    ):
        if m := re.search(r"\d{4}", el.findtext(path) or ""):
            return int(m.group())
    return None


def parse_efetch(xml: bytes | str) -> list[dict]:
    """Parse EFetch PubmedArticleSet XML into dicts shaped like Record columns."""
    out = []
    for pa in ET.fromstring(xml).iter("PubmedArticle"):
        cit = pa.find("MedlineCitation")
        a = cit.find("Article")
        authors, first_author = [], ""
        for i, au in enumerate(a.findall("AuthorList/Author")):
            last = au.findtext("LastName")
            name = (
                f"{last} {au.findtext('Initials') or ''}".strip() if last else au.findtext("CollectiveName")
            )
            if name:
                authors.append(name)
            if i == 0:
                first_author = last or name or ""
        abstract = "\n".join(
            f"{t.get('Label')}: {_text(t)}" if t.get("Label") else _text(t)
            for t in a.findall("Abstract/AbstractText")
        )
        doi_el = pa.find("PubmedData/ArticleIdList/ArticleId[@IdType='doi']")
        if doi_el is None:
            doi_el = a.find("ELocationID[@EIdType='doi']")
        doi = (doi_el.text or "").strip() if doi_el is not None else ""
        out.append(
            {
                "pmid": cit.findtext("PMID"),
                "doi": doi or None,
                "title": _text(a.find("ArticleTitle")),
                "abstract": abstract,
                "authors": authors,
                "first_author": first_author,
                "year": _year(a, pa),
                "journal": a.findtext("Journal/Title") or "",
                "pages": a.findtext("Pagination/MedlinePgn") or "",
                "language": a.findtext("Language") or "",
                "publication_types": [_text(p) for p in a.findall("PublicationTypeList/PublicationType")],
                "mesh_terms": [_text(d) for d in cit.findall("MeshHeadingList/MeshHeading/DescriptorName")],
            }
        )
    return out
