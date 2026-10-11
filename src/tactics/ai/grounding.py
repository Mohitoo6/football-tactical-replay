"""Check that an LLM explanation only uses facts from its summary (DECISIONS.md, D6).

Hard checks (must pass): every number, match clock (e.g. "88:15") and formation
label (e.g. "4-2-3-1") in the text must also appear in the summary.
Soft check (for review): capitalised words that appear nowhere in the summary,
which may be names the model brought in from its own knowledge.
"""

import json
import re
from dataclasses import dataclass, field

CLOCK = re.compile(r"\b\d{1,3}:\d{2}\b")
FORMATION = re.compile(r"\b\d(?:-\d){2,4}\b")
NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")
WORD = re.compile(r"[^\W\d_][\w'’.-]*")
SENTENCE_START = re.compile(r"(?:^|[.!?:]\s+|\n\s*[-*•]?\s*)$")
COMMON_WORDS = {
    "Key", "Numbers", "The", "A", "An", "In", "At", "As", "By", "On", "Of", "To", "This", "That", "These",
    "Then", "When", "While", "After", "Before", "Their", "Its", "It", "Meanwhile", "Over", "From", "With",
    "Both", "Ball", "Back", "Area", "Width", "Depth", "Shape", "Here", "By", "Within",
}


@dataclass
class GroundingReport:
    numbers_checked: int = 0
    unsupported_numbers: list[str] = field(default_factory=list)
    unsupported_clocks: list[str] = field(default_factory=list)
    unsupported_formations: list[str] = field(default_factory=list)
    unknown_capitalised: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (self.unsupported_numbers or self.unsupported_clocks or self.unsupported_formations)


def _base_word(word: str) -> str:
    """'Köln's' -> 'Köln', 'J.' -> 'J', so possessives and initials match the facts."""
    for suffix in ("'s", "’s"):
        if word.endswith(suffix):
            word = word[: -len(suffix)]
    return word.rstrip(".’'")


def _number(token: str) -> float:
    return float(token.replace(",", ""))


def _split(text: str) -> tuple[list[str], list[str], list[str]]:
    """Clocks, formations and the remaining plain numbers in a text (each counted once by kind)."""
    clocks = CLOCK.findall(text)
    text = CLOCK.sub(" ", text)
    formations = FORMATION.findall(text)
    text = FORMATION.sub(" ", text)
    return clocks, formations, NUMBER.findall(text)


def check_grounding(text: str, summary: dict) -> GroundingReport:
    facts = json.dumps(summary, ensure_ascii=False)
    fact_clocks, fact_formations, fact_numbers = _split(facts)
    allowed_numbers = {_number(n) for n in fact_numbers}
    fact_words = {_base_word(w) for w in WORD.findall(facts)}

    clocks, formations, numbers = _split(text)
    report = GroundingReport(numbers_checked=len(clocks) + len(formations) + len(numbers))
    report.unsupported_clocks = [c for c in clocks if c not in fact_clocks]
    report.unsupported_formations = [f for f in formations if f not in fact_formations]
    report.unsupported_numbers = [n for n in numbers if _number(n) not in allowed_numbers]

    for match in WORD.finditer(text):
        word = _base_word(match.group(0))
        if not word or not word[0].isupper() or word in COMMON_WORDS or word in fact_words:
            continue
        if SENTENCE_START.search(text[:match.start()]):  # ordinary capital at the start of a sentence
            continue
        if word not in report.unknown_capitalised:
            report.unknown_capitalised.append(word)
    return report
