"""NCBI E-utilities client: ESearch, EFetch, and the EFetch XML parser."""

import threading
import time
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
