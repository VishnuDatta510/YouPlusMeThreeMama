"""Deterministic duplicate detection: exact DOI / PMID, then fuzzy title within (year, first-author surname).

A fuzzy title match is only the *same record* when nothing says otherwise. Two different DOIs, two different journals
or two different first pages mean a further report of the study (journal paper vs conference version, preprint vs
article), which is not a duplicate.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz

AUTO_THRESHOLD = 95
REVIEW_THRESHOLD = 85
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")


@dataclass(frozen=True)
class Candidate:
    id: int
    pmid: str | None
    doi: str | None
    title: str
    year: int | None
    first_author: str
    journal: str = ""
    pages: str = ""


@dataclass(frozen=True)
class Match:
    record_id: int
    representative_id: int
    method: str  # doi / pmid / fuzzy
    score: float
    needs_review: bool


def normalize_doi(doi: str | None) -> str:
    d = (doi or "").strip().lower()
    for prefix in _DOI_PREFIXES:
        d = d.removeprefix(prefix)
    return d


def normalize_title(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", title.lower()).split())


def normalize_journal(journal: str) -> str:
    return normalize_title(journal).removeprefix("the ")


def first_page(pages: str) -> str:
    m = re.match(r"\s*([a-z]*\d+)", (pages or "").lower())
    return m.group(1) if m else ""


def same_report(a: Candidate, b: Candidate) -> bool:
    """False when metadata present on both sides shows two different publications."""
    if (da := normalize_doi(a.doi)) and (db := normalize_doi(b.doi)) and da != db:
        return False
    ja, jb = normalize_journal(a.journal), normalize_journal(b.journal)
    if ja and jb and fuzz.token_set_ratio(ja, jb) < 80:
        return False
    pa, pb = first_page(a.pages), first_page(b.pages)
    return not (pa and pb and pa != pb)


def find_duplicates(records: list[Candidate]) -> list[Match]:
    """Records are processed by ascending id, so the representative is always the lowest id in its group."""
    rep_by_doi: dict[str, int] = {}
    rep_by_pmid: dict[str, int] = {}
    # ponytail: pairwise compare inside each (year, surname) block; fine while blocks stay small.
    blocks: dict[tuple, list[tuple[Candidate, str]]] = defaultdict(list)
    matches = []
    for r in sorted(records, key=lambda c: c.id):
        doi, pmid = normalize_doi(r.doi), (r.pmid or "").strip()
        title = normalize_title(r.title)
        surname = re.sub(r"[^\w]", "", r.first_author.lower())
        block = (r.year, surname) if title and r.year and surname else None

        match = None
        if doi and doi in rep_by_doi:
            match = (rep_by_doi[doi], "doi", 100.0)
        elif pmid and pmid in rep_by_pmid:
            match = (rep_by_pmid[pmid], "pmid", 100.0)
        elif block:
            scored = [(fuzz.token_sort_ratio(title, t), -c.id) for c, t in blocks[block] if same_report(r, c)]
            if scored and (best := max(scored))[0] >= REVIEW_THRESHOLD:
                match = (-best[1], "fuzzy", round(best[0], 1))

        if match:
            rep, method, score = match
            matches.append(Match(r.id, rep, method, score, needs_review=score < AUTO_THRESHOLD))
        else:
            rep = r.id
            if block:
                blocks[block].append((r, title))
        if doi:
            rep_by_doi.setdefault(doi, rep)
        if pmid:
            rep_by_pmid.setdefault(pmid, rep)
    return matches
