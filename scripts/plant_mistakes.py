"""Test the tester: plant known mistakes in the real explanations and count how many the checks catch (D39).

    uv run python scripts/plant_mistakes.py         # writes evals/llm/checker_mutations.md (+ .json); no LLM calls

The scoreboard (D34) says the coach's explanations are grounded and their claims right. That is only worth
something if the checks would fail on a wrong explanation. So each correct explanation is copied, one mistake
of a kind an LLM makes is planted in the copy, and the checks run again. A mistake is caught when the copy gets a
problem the original did not have. Every place a mistake can go is used, not a chosen few.
"""

import json
import re
from pathlib import Path

from tactics.ai.evaluate import FROM_TO, evaluate, team_aliases, what_happened
from tactics.ai.grounding import CLOCK, FORMATION, NUMBER, check_grounding

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "llm"
TEMPLATES = ["4-4-2", "4-3-3", "4-2-3-1", "4-1-4-1", "3-5-2", "3-4-3", "5-3-2", "5-4-1"]
EVENTS = ["{p} then played a pass into the box.", "{p} whipped in a cross from the left.",
          "{p} made a sliding tackle to win the ball.", "{p} took a shot from the edge of the area.",
          "{p} won a header in the middle."]


def problems(text: str, facts: dict) -> dict[str, list[str]]:
    """Everything the checks flag: hard grounding problems, wrong claims, invented events, unknown names (soft)."""
    grounding, report = check_grounding(text, facts), evaluate(text, facts)
    return {"grounding": grounding.problems, "claims": [c.reason + ": " + c.sentence for c in report.claims if not c.ok],
            "invented": report.invented, "names (soft)": grounding.unknown_capitalised}


def caught_by(original: dict, mutated: dict) -> list[str]:
    return [kind for kind in mutated if len(mutated[kind]) > len(original[kind])]


def plain_numbers(text: str) -> list[re.Match]:
    """Numbers that are not part of a clock or a formation, with their positions in the text."""
    masked = FORMATION.sub(lambda m: "#" * len(m.group(0)), CLOCK.sub(lambda m: "#" * len(m.group(0)), text))
    return list(NUMBER.finditer(masked))


def fact_values(facts: dict) -> set[float]:
    masked = FORMATION.sub(" ", CLOCK.sub(" ", json.dumps(facts, ensure_ascii=False)))
    return {float(n.replace(",", "")) for n in NUMBER.findall(masked)}


def mutations(text: str, facts: dict):
    """(kind, description, mutated text) for every place each kind of mistake can go."""
    values = sorted(fact_values(facts))
    for m in plain_numbers(text):
        n = float(m.group(0).replace(",", ""))
        wrong = n + 17
        while wrong in values:
            wrong += 1
        yield "number not in the facts", f"{m.group(0)} -> {wrong:g}", text[:m.start()] + f"{wrong:g}" + text[m.end():]
        others = [v for v in values if v != n and v >= 1]
        if others:  # the hard case: a real value of the clip, put in the wrong place
            other = min(others, key=lambda v: abs(v - n))
            yield "a real value in the wrong place", f"{m.group(0)} -> {other:g}", text[:m.start()] + f"{other:g}" + text[m.end():]
    for m in FROM_TO.finditer(text):
        a, b = m.span(1), m.span(2)
        swapped = text[:a[0]] + m.group(2) + text[a[1]:b[0]] + m.group(1) + text[b[1]:]
        yield "change reversed (from/to swapped)", m.group(0)[:60], swapped
    teams = [t["name"] for t in facts.get("teams", [])]
    if len(teams) == 2:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if not FROM_TO.search(sentence):
                continue
            for i, team in enumerate(teams):
                for alias in sorted(team_aliases(team), key=len, reverse=True):
                    hit = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", sentence)
                    if hit:
                        other = team_aliases(teams[1 - i])[-1]
                        new = sentence[:hit.start()] + other + sentence[hit.end():]
                        yield "change given to the other team", f"{alias} -> {other}", text.replace(sentence, new, 1)
                        break
                else:
                    continue
                break
    for m in CLOCK.finditer(text):
        minute, second = m.group(0).split(":")
        wrong = f"{int(minute) + 3}:{second}"
        yield "wrong match clock", f"{m.group(0)} -> {wrong}", text[:m.start()] + wrong + text[m.end():]
    for m in FORMATION.finditer(text):
        wrong = next(t for t in TEMPLATES if t not in json.dumps(facts))
        yield "wrong formation", f"{m.group(0)} -> {wrong}", text[:m.start()] + wrong + text[m.end():]
    facts_part = what_happened(text)
    carriers = facts.get("ball_carriers") or [{"player": "the striker"}]
    for event in EVENTS:
        sentence = " " + event.format(p=carriers[0]["player"])
        cut = facts_part.rfind(".") + 1 or len(facts_part)
        yield "invented event in What happened", event.format(p="(carrier)"), text[:cut] + sentence + text[cut:]
    yield "invented player name", "Lewandowski", text.replace(".", ", with Lewandowski close by.", 1)


def main() -> None:
    rows = []
    for path in sorted((ROOT / "clips").glob("*/explanation.json")):
        facts = json.loads((path.parent / "summary.json").read_text())
        text = json.loads(path.read_text())["text"]
        original = problems(text, facts)
        for kind, what, mutated in mutations(text, facts):
            if mutated == text:
                continue
            by = caught_by(original, problems(mutated, facts))
            rows.append({"clip": path.parent.name, "kind": kind, "mistake": what, "caught_by": by})

    kinds = list(dict.fromkeys(r["kind"] for r in rows))
    lines = ["# Testing the checks: planted mistakes", "",
             "Each correct explanation was copied with one planted mistake, at every place that mistake can go, and "
             "checked again (`scripts/plant_mistakes.py`, no LLM calls; D39). *Caught* means the copy got a problem "
             "the original did not have. Names are a soft check: flagged for review, not failed.", "",
             "| Planted mistake | Copies | Caught | Rate | Caught by |", "|---|---|---|---|---|"]
    for kind in kinds:
        group = [r for r in rows if r["kind"] == kind]
        caught = [r for r in group if r["caught_by"]]
        by = sorted({b for r in caught for b in r["caught_by"]})
        lines.append(f"| {kind} | {len(group)} | {len(caught)} | {len(caught) / len(group):.0%} | {', '.join(by) or '-'} |")
    lines += ["", f"**Total:** {sum(bool(r['caught_by']) for r in rows)}/{len(rows)} planted mistakes caught.", ""]
    missed = [r for r in rows if not r["caught_by"]]
    if missed:
        lines += ["## Missed (examples)", ""] + [f"- {r['clip']}: {r['kind']}: {r['mistake']}" for r in missed[:25]] + [""]
    (OUT / "checker_mutations.md").write_text("\n".join(lines) + "\n")
    (OUT / "checker_mutations.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print("\n".join(lines[6:6 + len(kinds) + 3]))


if __name__ == "__main__":
    main()
