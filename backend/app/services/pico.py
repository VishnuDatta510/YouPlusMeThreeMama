"""PICO span tagging. `extract_pico` is the seam: PICO_METHOD=rules today, an LLM method can slot in later."""

import re
from typing import TypedDict

from app.config import settings


class Span(TypedDict):
    type: str  # P / I / C / O
    start: int
    end: int
    text: str


def _clause(stop_words: str = "", stop_chars: str = ".;\n") -> str:
    """Rest of the clause, ending before a stop char or stop word. Decimals like 6.8 don't stop it."""
    guard = rf"(?!\b(?:{stop_words})\b)" if stop_words else ""
    return rf"(?:{guard}(?:[^{stop_chars}]|(?<=\d)\.(?=\d)))*"


# Trigger words are matched but left out of the span: only the named groups (P/I/C/O) are tagged.
_END = ".;,\n"  # I and C also end at a comma; a constant because 3.11 f-strings can't hold a backslash
_ART = r"(?:(?:the|a|an)\s+)?"
_VS = r"or|versus|vs|compared|against"
_TIME = (
    r"(?:for|at|after|over|during)\s+(?:\d+|one|two|three|four|six|eight|twelve|a\b|an\b)"  # "for 12 weeks"
)
_I_STOP = rf"{_VS}|{_TIME}|were|was|and were|with a|in order"
_CMP = (  # comparators that need no trigger
    r"placebo|sham(?:\s+\w+)?|usual care|standard (?:of )?care|standard treatment|no (?:treatment|intervention)"
    r"|wait(?:ing)?[- ]list(?: control)?"
)
_P_STOP = (
    r"were|was|underwent|had|has|have|benefits?|received|receiving|treated|randomi[sz]ed|assigned|(?<!\d\s)to"
)
_TRIAL_AIM = r"evaluate|assess|compare|determine|investigate|examine|test|explore|estimate"

PATTERNS = [
    # Population: "adults with type 2 diabetes", "children aged 6-12 years with asthma"
    re.compile(
        r"\b(?P<P>(?:patients|adults|children|adolescents|infants|women|men|participants|subjects|individuals|people)"
        r"\s+(?:with|who|aged|undergoing|diagnosed)\b" + _clause(rf"{_VS}|{_P_STOP}") + ")",
        re.I,
    ),
    # Intervention, then an optional comparator: "received metformin or placebo", "assigned to X versus Y"
    re.compile(
        r"\b(?:(?:randomi[sz]ed|assigned|allocated)\b[^.;\n]{0,80}?\bto(?:\s+receive)?"
        r"|received|receiving|treated with|administered|given)\s+(?:either\s+)?"
        rf"(?!(?:{_TRIAL_AIM})\b){_ART}"
        rf"(?P<I>\w{_clause(_I_STOP, _END)})"
        rf"(?:,?\s*(?:or|versus|vs\.?|compared (?:with|to))\s+{_ART}(?P<C>\w{_clause(_TIME, _END)}))?",
        re.I,
    ),
    re.compile(
        rf"\b(?:compared (?:with|to)|versus|vs\.?|against)\s+{_ART}(?P<C>\w{_clause(_TIME, _END)})", re.I
    ),
    re.compile(rf"\b(?P<C>{_CMP})\b", re.I),
    # Outcome: "the primary outcome was change in HbA1c", "outcomes included exacerbation rate"
    re.compile(
        r"\b(?:(?:primary|secondary|main) (?:end ?points?|outcomes?(?: measures?)?)|outcomes?)"
        r"\s+(?:was|were|is|are|included|include|includes|comprised)\s+"
        + _ART
        + rf"(?P<O>\w{_clause(_TIME)})",
        re.I,
    ),
    re.compile(rf"\b(?P<O>change (?:in|from baseline in) {_clause(_TIME)})", re.I),
]
MAX_SPAN = 200


def _rules(text: str) -> list[Span]:
    found = []
    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            for kind, value in m.groupdict().items():
                if not value:
                    continue
                start = m.start(kind)
                snippet = value[:MAX_SPAN].rstrip(" ,")
                found.append(Span(type=kind, start=start, end=start + len(snippet), text=snippet))
    # Keep spans non-overlapping so the UI can highlight them: earliest start wins, then longest.
    spans, last_end = [], -1
    for s in sorted(found, key=lambda s: (s["start"], -s["end"])):
        if s["start"] >= last_end and s["text"]:
            spans.append(s)
            last_end = s["end"]
    return spans


def method_version() -> str:
    return f"{settings.pico_method}-v3"  # bump when the rules change so the next run re-tags


def extract_pico(text: str) -> list[Span]:
    if settings.pico_method == "rules":
        return _rules(text)
    raise NotImplementedError(f"PICO_METHOD={settings.pico_method} is not implemented yet")
