"""Deterministic duplicate detection: exact DOI / PMID, then fuzzy title within (year, first-author surname)."""

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


def find_duplicates(records: list[Candidate]) -> list[Match]:
    """Records are processed by ascending id, so the representative is always the lowest id in its group."""
    rep_by_doi: dict[str, int] = {}
    rep_by_pmid: dict[str, int] = {}
    # ponytail: pairwise compare inside each (year, surname) block; fine while blocks stay small.
    blocks: dict[tuple, list[tuple[int, str]]] = defaultdict(list)
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
            scored = [(fuzz.token_sort_ratio(title, t), -rid) for rid, t in blocks[block]]
            if scored and (best := max(scored))[0] >= REVIEW_THRESHOLD:
                match = (-best[1], "fuzzy", round(best[0], 1))

        if match:
            rep, method, score = match
            matches.append(Match(r.id, rep, method, score, needs_review=score < AUTO_THRESHOLD))
        else:
            rep = r.id
            if block:
                blocks[block].append((r.id, title))
        if doi:
            rep_by_doi.setdefault(doi, rep)
        if pmid:
            rep_by_pmid.setdefault(pmid, rep)
    return matches
