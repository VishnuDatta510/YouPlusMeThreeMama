"""PICO span tagging. `extract_pico` is the seam: PICO_METHOD=rules today, an LLM method can slot in later."""

import re
from typing import TypedDict

from app.config import settings


class Span(TypedDict):
    type: str  # P / I / C / O
    start: int
    end: int
    text: str


_I_TRIGGERS = r"randomi[sz]ed to|received|receiving|treated with|administered|assigned to|allocated to"
_C_TRIGGERS = r"compared (?:with|to)|versus|vs\.|placebo"


def _clause(stop_words: str = "", stop_chars: str = ".;\n") -> str:
    """Rest of the clause, ending before a stop char or the next PICO trigger."""
    guard = rf"(?!\b(?:{stop_words})\b)" if stop_words else ""
    return rf"(?:{guard}[^{stop_chars}])*"


PATTERNS = {
    "P": re.compile(
        r"\b(?:patients|adults|children|adolescents|women|men|participants|subjects|individuals|people)"
        r"\s+(?:with|who|aged|undergoing|diagnosed)\b"
        + _clause(rf"{_I_TRIGGERS}|{_C_TRIGGERS}|were|was|underwent"),
        re.I,
    ),
    "I": re.compile(rf"\b(?:{_I_TRIGGERS})\b" + _clause(_C_TRIGGERS, ".;,\n"), re.I),
    "C": re.compile(rf"\b(?:{_C_TRIGGERS})" + _clause(stop_chars=".;,\n"), re.I),
    "O": re.compile(
        r"\b(?:(?:primary|secondary) (?:end ?points?|outcomes?)|outcomes? (?:was|were|included)"
        r"|(?:was|were) measured|change in)\b" + _clause(),
        re.I,
    ),
}
MAX_SPAN = 200


def _rules(text: str) -> list[Span]:
    found = []
    for kind, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            snippet = text[m.start() : min(m.end(), m.start() + MAX_SPAN)].rstrip()
            found.append(Span(type=kind, start=m.start(), end=m.start() + len(snippet), text=snippet))
    # Keep spans non-overlapping so the UI can highlight them: earliest start wins, then longest.
    spans, last_end = [], -1
    for s in sorted(found, key=lambda s: (s["start"], -s["end"])):
        if s["start"] >= last_end:
            spans.append(s)
            last_end = s["end"]
    return spans


def method_version() -> str:
    return f"{settings.pico_method}-v1"


def extract_pico(text: str) -> list[Span]:
    if settings.pico_method == "rules":
        return _rules(text)
    raise NotImplementedError(f"PICO_METHOD={settings.pico_method} is not implemented yet")
