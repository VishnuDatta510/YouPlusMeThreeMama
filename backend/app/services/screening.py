"""Rule-based screening. Each rule returns ("exclude", reason) or None."""

import re
from collections.abc import Callable

from app.config import settings
from app.models import Record

Rule = Callable[[Record], tuple[str, str] | None]

_ANIMAL_WORDS = re.compile(
    r"\b(rats?|mice|mouse|murine|rodents?|in vitro|porcine|canine|bovine|zebrafish|rabbits?)\b", re.I
)
_SIMULATION_WORDS = re.compile(r"\b(simulations?|in silico|modell?ing stud(y|ies))\b", re.I)


def _text(r: Record) -> str:
    return f"{r.title} {r.abstract}"


def non_english(r: Record):
    if r.language and r.language != "eng":
        return "exclude", f"non-English ({r.language})"


def non_human(r: Record):
    mesh = set(r.mesh_terms or [])
    if mesh:
        if "Animals" in mesh and "Humans" not in mesh:
            return "exclude", "non-human (MeSH: Animals without Humans)"
    elif m := _ANIMAL_WORDS.search(_text(r)):
        return "exclude", f"non-human (keyword: {m.group().lower()})"


def case_report(r: Record):
    if "Case Reports" in (r.publication_types or []):
        return "exclude", "case report"


def simulation(r: Record):
    if m := _SIMULATION_WORDS.search(_text(r)):
        return "exclude", f"simulation study (keyword: {m.group().lower()})"


RULES: dict[str, Rule] = {
    "non_english": non_english,
    "non_human": non_human,
    "case_report": case_report,
    "simulation": simulation,
}


def active_criteria() -> list[str]:
    names = [n.strip() for n in settings.screening_criteria.split(",") if n.strip()]
    if unknown := set(names) - RULES.keys():
        raise ValueError(f"Unknown screening criteria: {sorted(unknown)}")
    return names


def method_version(criteria: list[str]) -> str:
    return f"rules-v1:{','.join(criteria)}"


def screen(r: Record, criteria: list[str]) -> dict:
    reasons = [hit[1] for name in criteria if (hit := RULES[name](r))]
    if reasons:
        return {"label": "exclude", "reason": "; ".join(reasons)}
    if not r.abstract and not r.mesh_terms:
        return {"label": "maybe", "reason": "not enough information (no abstract or MeSH)"}
    return {"label": "include", "reason": "no exclusion criteria matched"}
