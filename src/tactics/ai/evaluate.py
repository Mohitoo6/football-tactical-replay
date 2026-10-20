"""Checks on the coach's explanation beyond grounding (DECISIONS.md, D34). Pure Python, no LLM calls.

Grounding (grounding.py) asks: is every number, clock and formation somewhere in the facts? These checks ask more:

- claims:   "Bayern's back line went from 42 to 72 metres": is that change in the facts for that team, in that
            order, and does the wording (pushed up / dropped) go the same way as the numbers?
- coverage: did the explanation say the things that matter most (the goal and its scorer, each team's shape,
            each team's biggest change)?
- invented: words for events the coach may not invent (passes, crosses, tackles, shots...) in "What happened",
            the facts section (prompt rule 3); the coach's view may talk about football in general.
"""

import re
from dataclasses import dataclass, field

NUM = r"(?<![\d:.,])(\d+(?:[.,]\d+)?)(?![\d:])"
# "from 42 metres at 87:57 to 72 metres": clocks are skipped because a number touching ":" is not a number here
FROM_TO = re.compile(rf"\bfrom\s+(?:about\s+)?{NUM}\s*(?:m²|m2|m\b|metres|meters|players)?[^.;]*?\bto\s+(?:about\s+)?{NUM}", re.I)
UP = ("push", "rose", "rise", "increas", "expand", "widen", "grew", "grow", "advanc", "higher", "climb", "stretch")
DOWN = ("drop", "fell", "fall", "reduc", "shrank", "shrink", "compress", "narrow", "lower", "retreat", "squeez", "deeper")
INVENTED = re.compile(r"\b(pass(?:es|ed)?|cross(?:es|ed)?|tackl\w*|shots?|header|dribbl\w*|volley\w*|through ball)\b", re.I)
SCORED = re.compile(r"\b(scor\w*|netted)\b", re.I)
NAME_STOPWORDS = {"team", "shirts", "lighter", "darker", "the"}


@dataclass
class Claim:
    sentence: str
    team: str | None
    start: float
    end: float
    ok: bool
    reason: str


@dataclass
class EvalReport:
    claims: list[Claim] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)

    @property
    def claims_ok(self) -> int:
        return sum(c.ok for c in self.claims)

    @property
    def coverage(self) -> float:
        total = len(self.covered) + len(self.missing)
        return 1.0 if total == 0 else len(self.covered) / total

    def as_json(self) -> dict:
        return {"claims_checked": len(self.claims), "claims_ok": self.claims_ok,
                "claim_problems": [f"{c.reason}: {c.sentence}" for c in self.claims if not c.ok],
                "coverage": round(self.coverage, 2), "covered": self.covered, "missing": self.missing,
                "invented_events": self.invented}


def team_aliases(name: str) -> list[str]:
    """Ways the text may name a team: the full name, 'Team A', and its distinctive words ('Bayern', 'Köln')."""
    aliases = [name]
    short = re.match(r"(Team [A-Z])\b", name)
    if short:
        aliases.append(short.group(1))
    for word in re.findall(r"[^\W\d_][\w'-]*", name):
        if len(word) >= 4 and word.lower() not in NAME_STOPWORDS:
            aliases.append(word)
    return aliases


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def _sentences(text: str) -> list[str]:
    plain = re.sub(r"[*_`]", "", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", plain) if s.strip()]


def _team_at(sentence: str, position: int, teams: list[str]) -> str | None:
    """The team named closest before `position` in the sentence (or anywhere in it if none comes before)."""
    best, best_pos = None, -1
    for team in teams:
        for alias in team_aliases(team):
            for m in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", sentence):
                if m.start() <= position and m.start() > best_pos:
                    best, best_pos = team, m.start()
    if best is None:
        mentioned = [t for t in teams if any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", sentence) for a in team_aliases(t))]
        best = mentioned[0] if len(mentioned) == 1 else None
    return best


def _changes(summary: dict, team: str) -> set[tuple[float, float]]:
    """Every (earlier value, later value) pair of one team's metrics in the facts."""
    pairs = set()
    for change in summary.get("notable_changes", []):
        if change.get("team") == team:
            pairs.add((float(change["from"]), float(change["to"])))
    rows = [row[team] for row in summary.get("timeline", []) if isinstance(row.get(team), dict)]
    for metric in {k for row in rows for k in row}:
        values = [row[metric] for row in rows if isinstance(row.get(metric), (int, float))]
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                pairs.add((float(a), float(b)))
    return pairs


def check_claims(text: str, summary: dict) -> list[Claim]:
    teams = [t["name"] for t in summary.get("teams", [])]
    claims = []
    for sentence in _sentences(text):
        for m in FROM_TO.finditer(sentence):
            start, end = _number(m.group(1)), _number(m.group(2))
            team = _team_at(sentence, m.start(), teams)
            if team is None:
                claims.append(Claim(sentence, None, start, end, False, "no team named for this change"))
                continue
            if (start, end) not in _changes(summary, team):
                others = [t for t in teams if t != team and (start, end) in _changes(summary, t)]
                reason = f"this change belongs to {others[0]}" if others else "this change is not in the facts for this team"
                claims.append(Claim(sentence, team, start, end, False, reason))
                continue
            clause = sentence[max(0, m.start() - 60):m.end()].lower()
            says_up, says_down = any(w in clause for w in UP), any(w in clause for w in DOWN)
            if says_up != says_down and says_up != (end > start):
                claims.append(Claim(sentence, team, start, end, False, "the wording goes the other way from the numbers"))
                continue
            claims.append(Claim(sentence, team, start, end, True, "matches the facts"))
    return claims


def key_facts(summary: dict) -> list[tuple[str, list[str]]]:
    """The facts an explanation should not leave out, each with the strings that show it was said."""
    facts = []
    for goal in summary.get("goals", []):
        surname = goal["player"].split()[-1]
        facts.append((f"goal by {goal['player']} at {goal['clock']}", [surname, goal["clock"]]))
    for team in summary.get("teams", []):
        shape = team.get("shape_in_clip") or ""
        if re.fullmatch(r"\d(-\d)+", shape):
            facts.append((f"{team['name']} shape {shape}", [shape]))
    by_team: dict[str, dict] = {}
    for change in summary.get("notable_changes", []):
        size = abs(change["to"] - change["from"]) / max(abs(change["from"]), 1)
        if size > by_team.get(change["team"], {}).get("size", -1):
            by_team[change["team"]] = {**change, "size": size}
    for team, change in by_team.items():
        facts.append((f"{team} {change['metric']} {change['from']} -> {change['to']}", [str(change["from"]), str(change["to"])]))
    return facts


def what_happened(text: str) -> str:
    """The facts section of the explanation (all of it if the sections are missing)."""
    part = re.split(r"\*\*\s*Coach's view\s*\*\*|\n\s*Coach's view\s*:?\s*\n", text, maxsplit=1, flags=re.I)[0]
    return part


def evaluate(text: str, summary: dict) -> EvalReport:
    report = EvalReport(claims=check_claims(text, summary))
    for label, needles in key_facts(summary):
        # a number may carry a unit ("17m"), but must not be part of a longer number or a clock
        said = all(re.search(rf"(?<![\w.:]){re.escape(n)}(?![\d:]|\.\d)", text) for n in needles)
        (report.covered if said else report.missing).append(label)
    facts_part = what_happened(text)
    report.invented = sorted({m.group(0).lower() for m in INVENTED.finditer(facts_part)})
    if not summary.get("goals") and SCORED.search(facts_part):
        report.invented.append("a goal that is not in the facts")
    return report
