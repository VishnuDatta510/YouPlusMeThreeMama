"""Europe PMC REST client: search (count and core records) and the JSON → record parser. No key needed."""

import html
import re
import time
from datetime import date

import httpx

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PAGE_SIZE = 1000  # the API maximum


def _call(params: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        last = attempt == retries - 1
        try:
            r = httpx.get(SEARCH, params={**params, "format": "json"}, timeout=60)
        except httpx.TransportError:
            if last:
                raise
        else:
            if r.status_code != 429 and r.status_code < 500:
                return r.raise_for_status().json()
            if last:
                r.raise_for_status()
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def build_query(term: str, date_from: date | None, date_to: date | None) -> str:
    """Europe PMC takes the same AND / OR / NOT and "quoted phrase" syntax as PubMed; dates go in the query."""
    if not (date_from or date_to):
        return term
    lo = (date_from or date(1800, 1, 1)).isoformat()
    hi = (date_to or date(3000, 12, 31)).isoformat()
    return f"({term}) AND (FIRST_PDATE:[{lo} TO {hi}])"


def count(term: str, date_from: date | None = None, date_to: date | None = None) -> int:
    body = _call({"query": build_query(term, date_from, date_to), "resultType": "idlist", "pageSize": 1})
    return int(body.get("hitCount", 0))


def search(term: str, date_from: date | None, date_to: date | None, limit: int) -> list[dict]:
    """Core records (abstract, MeSH, publication types included) for the first `limit` hits."""
    query, cursor, out = build_query(term, date_from, date_to), "*", []
    while len(out) < limit:
        body = _call(
            {
                "query": query,
                "resultType": "core",
                "pageSize": min(PAGE_SIZE, limit - len(out)),
                "cursorMark": cursor,
            }
        )
        results = body.get("resultList", {}).get("result", [])
        out += [parse_result(r) for r in results]
        nxt = body.get("nextCursorMark")
        if not results or not nxt or nxt == cursor:
            break
        cursor = nxt
    return out[:limit]


_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"<h\d[^>]*>(.*?)</h\d>", re.I | re.S)


def _clean(text: str | None) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", text or "")).split())


def _abstract(text: str | None) -> str:
    """Section headings (<h4>Methods</h4>) become "METHODS: …" lines, matching the PubMed parser's labels."""
    parts = _HEADING.split(text or "")
    if len(parts) == 1:
        return _clean(text)
    lines = [_clean(parts[0])] if _clean(parts[0]) else []
    for heading, body in zip(parts[1::2], parts[2::2]):
        lines.append(f"{_clean(heading).upper()}: {_clean(body)}")
    return "\n".join(lines)


def parse_result(r: dict) -> dict:
    """One core search result → a dict shaped like Record columns, plus `source_id` for records without a PMID."""
    authors, first_author = [], ""
    for i, a in enumerate(r.get("authorList", {}).get("author", [])):
        last = a.get("lastName")
        name = (
            f"{last} {a.get('initials', '')}".strip()
            if last
            else a.get("collectiveName") or a.get("fullName")
        )
        if name:
            authors.append(name)
        if i == 0:
            first_author = last or name or ""
    journal = r.get("journalInfo", {}).get("journal", {})
    year = r.get("pubYear") or ""
    pmid = r.get("pmid") or None
    return {
        "pmid": pmid,
        "source_id": None if pmid else f"{r.get('source', 'EPMC')}:{r.get('id')}",
        "doi": r.get("doi") or None,
        "title": _clean(r.get("title")),
        "abstract": _abstract(r.get("abstractText")),
        "authors": authors,
        "first_author": first_author,
        "year": int(year) if year.isdigit() else None,
        "journal": journal.get("title") or r.get("bookOrReportDetails", {}).get("publisher", ""),
        "pages": r.get("pageInfo") or "",
        "language": r.get("language") or "",
        "publication_types": r.get("pubTypeList", {}).get("pubType", []),
        "mesh_terms": [m["descriptorName"] for m in r.get("meshHeadingList", {}).get("meshHeading", [])],
    }
