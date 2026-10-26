"""Rule-based screening. Each rule returns ("exclude", reason) or None.

Every criterion reads the record's metadata field when it has one (language, MeSH, publication type) and falls back
to its own text algorithm when that field is missing. The reviewer picks which criteria are active.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import HumanDecision, Record

Rule = Callable[[Record], tuple[str, str] | None]


def _text(r: Record) -> str:
    return f"{r.title} {r.abstract}"


# --- non-English: metadata `language`, else a stop-word / script check -------------------------------------------
_EN_STOPWORDS = set(
    "the of and in to a with for was were is are on by that this from as at an or be after than which".split()
)
_FOREIGN_STOPWORDS = set(
    "der die das und mit von bei für ist den dem des les une est dans pour avec sur del los las por para una con "
    "che della per sono nel não uma com para dos het een van voor zijn".split()
)
_WORD = re.compile(r"[^\W\d_]+", re.U)


def detect_language(text: str) -> str | None:
    """'eng', 'other' or None when there is too little text to tell."""
    if re.search(r"[Ѐ-ӿ؀-ۿ぀-ヿ一-鿿가-힯]", text):
        return "other"  # Cyrillic, Arabic, Japanese, Chinese or Korean script
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < 12:
        return None
    en = sum(w in _EN_STOPWORDS for w in words)
    foreign = sum(w in _FOREIGN_STOPWORDS for w in words)
    return "eng" if en >= foreign and en / len(words) > 0.06 else "other"


def non_english(r: Record):
    if r.language:
        if r.language != "eng":
            return "exclude", f"non-English ({r.language})"
    elif detect_language(_text(r)) == "other":
        return "exclude", "non-English (detected from text)"


# --- non-human: MeSH Animals without Humans, else animal / lab keywords ------------------------------------------
_ANIMAL_WORDS = re.compile(
    r"\b(rats?|mice|mouse|murine|rodents?|in vitro|porcine|canine|bovine|zebrafish|rabbits?|"
    r"primates?|macaques?|piglets?|sheep|cell lines?)\b",
    re.I,
)


def non_human(r: Record):
    mesh = set(r.mesh_terms or [])
    if mesh:
        if "Animals" in mesh and "Humans" not in mesh:
            return "exclude", "non-human (MeSH: Animals without Humans)"
    elif m := _ANIMAL_WORDS.search(_text(r)):
        return "exclude", f"non-human (keyword: {m.group().lower()})"


# --- publication-type criteria: metadata first, keyword fallback ------------------------------------------------
def _pub_types(r: Record) -> set[str]:
    return {p.lower() for p in (r.publication_types or [])}


def _by_type(r: Record, types: set[str], fallback: re.Pattern, reason: str, title_only: bool = False):
    found = _pub_types(r) & types
    if found:
        return "exclude", f"{reason} (publication type: {sorted(found)[0]})"
    meaningful = _pub_types(r) - {"journal article", "research-article", "research support, non-u.s. gov't"}
    if not meaningful and (m := fallback.search(r.title if title_only else _text(r))):
        return "exclude", f"{reason} (keyword: {m.group().lower().strip()})"


_CASE_WORDS = re.compile(
    r"\b(case reports?|we (?:report|present|describe) (?:a|an|the) (?:case|patient)|"
    r"a case of|\d+[- ]year[- ]old (?:man|woman|male|female|boy|girl|patient))\b",
    re.I,
)


def case_report(r: Record):
    return _by_type(r, {"case reports"}, _CASE_WORDS, "case report")


_SIMULATION_WORDS = re.compile(
    r"\b(simulations?|in silico|modell?ing stud(?:y|ies)|markov model|microsimulation|"
    r"agent-based model|computational model)\b",
    re.I,
)


def simulation(r: Record):
    if m := _SIMULATION_WORDS.search(_text(r)):
        return "exclude", f"simulation study (keyword: {m.group().lower()})"


_REVIEW_WORDS = re.compile(
    r"\b(systematic review|meta-analys[ie]s|narrative review|scoping review|literature review|"
    r"umbrella review|a review)\b",
    re.I,
)


def review_article(r: Record):
    return _by_type(
        r,
        {"review", "systematic review", "meta-analysis", "scoping review", "review-article"},
        _REVIEW_WORDS,
        "secondary research",
        title_only=True,
    )


_NOT_RESEARCH_WORDS = re.compile(
    r"^(?:comment(?:ary)? on|re:|reply|response to|letter|editorial|erratum|correction|corrigendum)\b", re.I
)


def not_research(r: Record):
    return _by_type(
        r,
        {"editorial", "letter", "comment", "news", "published erratum", "interview", "biography"},
        _NOT_RESEARCH_WORDS,
        "not original research",
        title_only=True,
    )


_RETRACTED_WORDS = re.compile(r"^\W*(?:retracted|withdrawn)\b", re.I)


def retracted(r: Record):
    types = _pub_types(r)
    if types & {"retracted publication", "retraction of publication"}:
        return "exclude", "retracted publication"
    if _RETRACTED_WORDS.search(r.title or ""):
        return "exclude", "retracted publication (title)"


_PROTOCOL_WORDS = re.compile(
    r"\b(study protocol|protocol for an?|trial protocol|design and rationale|rationale and design)\b", re.I
)


def protocol(r: Record):
    if m := _PROTOCOL_WORDS.search(r.title or ""):
        return "exclude", f"protocol without results (keyword: {m.group().lower()})"


@dataclass(frozen=True)
class Criterion:
    rule: Rule
    label: str
    why: str  # one-line justification shown to the reviewer
    basis: str  # where the signal comes from


CRITERIA: dict[str, Criterion] = {
    "non_english": Criterion(
        non_english,
        "Non-English",
        "The team cannot check text it cannot read.",
        "Language field; stop-word and script detection when missing",
    ),
    "non_human": Criterion(
        non_human,
        "Non-human",
        "Animal and lab studies do not measure effects in people.",
        "MeSH Animals without Humans; animal / in vitro keywords when MeSH is missing",
    ),
    "case_report": Criterion(
        case_report,
        "Case report",
        "One patient cannot show an average effect.",
        "Publication type; case-report phrasing when missing",
    ),
    "simulation": Criterion(
        simulation,
        "Simulation / modelling",
        "Models predict outcomes instead of measuring patients.",
        "Keyword algorithm on title and abstract (no metadata field exists)",
    ),
    "review_article": Criterion(
        review_article,
        "Review / meta-analysis",
        "Secondary research re-reports primary studies; we screen the primary studies themselves.",
        "Publication type; review keywords in the title when missing",
    ),
    "not_research": Criterion(
        not_research,
        "Editorial, letter, comment",
        "Opinion pieces and errata report no study data.",
        "Publication type; title prefix when missing",
    ),
    "retracted": Criterion(
        retracted,
        "Retracted",
        "Retracted results cannot be trusted as evidence.",
        "Publication type; RETRACTED title prefix",
    ),
    "protocol": Criterion(
        protocol,
        "Protocol without results",
        "A protocol describes a planned study and has no outcome data yet.",
        "Keyword algorithm on the title",
    ),
}
RULES: dict[str, Rule] = {k: c.rule for k, c in CRITERIA.items()}


def active_criteria(db: Session | None = None) -> list[str]:
    """The reviewer's latest criteria choice (an append-only decision), else the SCREENING_CRITERIA default."""
    if db is not None:
        latest = db.scalar(
            select(HumanDecision)
            .where(HumanDecision.target_type == "project", HumanDecision.decision_type == "criteria")
            .order_by(HumanDecision.id.desc())
            .limit(1)
        )
        if latest is not None:
            return [k for k in CRITERIA if k in latest.value["active"]]
    names = [n.strip() for n in settings.screening_criteria.split(",") if n.strip()]
    if unknown := set(names) - CRITERIA.keys():
        raise ValueError(f"Unknown screening criteria: {sorted(unknown)}")
    return names


def method_version(criteria: list[str]) -> str:
    return f"rules-v2:{','.join(criteria)}"


_HUMAN_WORDS = re.compile(
    r"\b(patients?|participants?|adults?|children|adolescents?|infants?|women|men|people|persons?|subjects|"
    r"volunteers?|individuals|cohort|population|residents|students|workers|veterans|cases)\b",
    re.I,
)


def screen(r: Record, criteria: list[str]) -> dict:
    reasons = [hit[1] for name in criteria if (hit := RULES[name](r))]
    if reasons:
        return {"label": "exclude", "reason": "; ".join(reasons)}
    if not r.abstract:
        return {"label": "maybe", "reason": "no abstract to screen; check the full text"}
    if "Humans" not in (r.mesh_terms or []) and not _HUMAN_WORDS.search(_text(r)):
        return {"label": "maybe", "reason": "population unclear: no human participants mentioned"}
    return {"label": "include", "reason": "no exclusion criteria matched"}
