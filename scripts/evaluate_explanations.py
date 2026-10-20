"""Score every cached coach explanation, and run the trap tests (DECISIONS.md, D34).

    uv run python scripts/evaluate_explanations.py            # scoreboard of the cached explanations (no LLM calls)
    uv run python scripts/evaluate_explanations.py --traps    # also the trap tests (one LLM call each, then cached)

Writes evals/llm/scoreboard.md (+ .json) and, with --traps, evals/llm/traps.md (+ the answers in evals/llm/traps/).

The scoreboard checks each explanation against its facts:
  grounding  every number, clock and formation appears in the facts (tactics/ai/grounding.py)
  claims     every "from X to Y" change is the right team's, in the right order and direction
  coverage   the key facts are said: the goal and scorer, each team's shape, each team's biggest change
  invented   no invented events (passes, shots...) in the facts section
  format     the three sections, at most ~220 words

The traps change one fact of a real clip and check the coach does not fall for it.
"""

import argparse
import copy
import json
import re
from pathlib import Path

from tactics.ai.evaluate import evaluate, what_happened
from tactics.ai.grounding import check_grounding
from tactics.ai.prompt import format_problems
from tactics.ai.summary import CAMERA_NOTE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "llm"


def score(text: str, facts: dict) -> dict:
    grounding = check_grounding(text, facts)
    checks = evaluate(text, facts)
    return {
        "grounding_ok": grounding.passed, "numbers_checked": grounding.numbers_checked,
        "grounding_problems": grounding.problems, **checks.as_json(),
        "format_problems": format_problems(text), "words": len(text.split()),
    }


def scoreboard() -> list[dict]:
    rows = []
    for path in sorted((ROOT / "clips").glob("*/explanation.json")):
        folder = path.parent
        facts = json.loads((folder / "summary.json").read_text())
        record = json.loads(path.read_text())
        rows.append({"clip": folder.name, "model": record.get("model"), **score(record["text"], facts)})
    return rows


def write_scoreboard(rows: list[dict]) -> None:
    lines = ["# Coach explanations: scoreboard", "",
             "Automatic checks of every cached explanation against its facts (no LLM calls). "
             "Made by `scripts/evaluate_explanations.py`; see DECISIONS.md D34.", "",
             "| Clip | Grounding | Claims right | Key facts said | Invented events | Format | Words |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['clip']} | {'pass' if r['grounding_ok'] else 'FAIL'} ({r['numbers_checked']} checked) "
                     f"| {r['claims_ok']}/{r['claims_checked']} | {r['coverage']:.0%} | {', '.join(r['invented_events']) or 'none'} "
                     f"| {'ok' if not r['format_problems'] else '; '.join(r['format_problems'])} | {r['words']} |")
    claims = sum(r["claims_checked"] for r in rows)
    lines += ["", f"**Total:** {sum(r['grounding_ok'] for r in rows)}/{len(rows)} grounded; "
              f"{sum(r['claims_ok'] for r in rows)}/{claims} claims right; "
              f"average key-fact coverage {sum(r['coverage'] for r in rows) / max(len(rows), 1):.0%}.", ""]
    for r in rows:
        if r["missing"] or r["claim_problems"] or r["grounding_problems"]:
            lines.append(f"- **{r['clip']}**: " + "; ".join(
                [f"not said: {m}" for m in r["missing"]] + r["claim_problems"] + r["grounding_problems"]))
    (OUT / "scoreboard.md").write_text("\n".join(lines) + "\n")
    (OUT / "scoreboard.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")


# --- traps: one changed fact each, and what a faithful coach must (not) say ------------------------------

def traps(base: dict) -> list[tuple[str, str, dict, callable]]:
    focus, other = base["teams"][0]["name"], base["teams"][1]["name"]

    no_goal = copy.deepcopy(base)
    no_goal["goals"] = []

    little_play = copy.deepcopy(base)
    little_play["clip"]["seconds_ball_in_play"] = 3
    little_play["timeline"], little_play["notable_changes"] = [], []

    no_shape = copy.deepcopy(base)
    no_shape["teams"][0]["shape_in_clip"] = "n/a, under 5 s of open play"
    no_shape["teams"][0]["official_formation"] = None
    hidden_shape = base["teams"][0]["shape_in_clip"]

    camera = copy.deepcopy(base)
    camera["clip"]["camera"] = CAMERA_NOTE

    mirror = copy.deepcopy(base)
    mirror["notable_changes"] = [
        {"team": focus, "metric": "width_m", "from": 35, "to": 44, "from_clock": base["clip"]["from_clock"], "to_clock": base["clip"]["to_clock"]},
        {"team": other, "metric": "width_m", "from": 44, "to": 35, "from_clock": base["clip"]["from_clock"], "to_clock": base["clip"]["to_clock"]},
    ]

    return [
        ("no-goal", "The goal is removed: the coach must not mention a goal or a scorer.", no_goal,
         lambda t, s: not re.search(r"\b(scor\w*|netted)\b", what_happened(t), re.I)),
        ("too-little-play", "Only 3 s of open play and no timeline: the coach must say there is too little play to analyse.",
         little_play, lambda t, s: bool(re.search(r"too little|not enough|very little|too short|limited (open )?play", t, re.I))),
        ("unknown-shape", f"The focus team's shape is unknown: the coach must not name {hidden_shape} for it.", no_shape,
         lambda t, s: hidden_shape not in t),
        ("partial-camera", "The camera shows only part of the pitch: the coach must say so.", camera,
         lambda t, s: bool(re.search(r"part of the pitch|only part|partial view", t, re.I))),
        ("mirror-numbers", "Both teams' width moves between 35 and 44 m, in opposite directions: each number must stay with its team.",
         mirror, lambda t, s: all(c.ok for c in evaluate(t, s).claims) and len(evaluate(t, s).claims) > 0),
    ]


def run_traps() -> list[dict]:
    from tactics.ai.llm import explain

    base = json.loads((ROOT / "clips" / "musiala-winner" / "summary.json").read_text())
    folder = OUT / "traps"
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for name, rule, facts, passes in traps(base):
        record = explain(facts, folder / f"{name}.json", check=lambda t, f=facts: check_grounding(t, f).problems + format_problems(t))
        text = record["text"]
        results.append({"trap": name, "rule": rule, "passed": bool(passes(text, facts)), "grounded": check_grounding(text, facts).passed,
                        "model": record["model"], "from_cache": record.get("from_cache", False), "text": text})
    return results


def write_traps(results: list[dict]) -> None:
    lines = ["# Coach explanations: trap tests", "",
             "Each trap takes the facts of Musiala's winner, changes one thing, and asks the coach again. "
             "A faithful coach must follow the changed facts. Made by `scripts/evaluate_explanations.py --traps`.", "",
             "| Trap | What the coach must do | Result | Grounded | Model |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['trap']} | {r['rule']} | {'PASS' if r['passed'] else 'FAIL'} | {'yes' if r['grounded'] else 'no'} | {r['model']} |")
    lines += ["", f"**{sum(r['passed'] for r in results)}/{len(results)} traps passed.** The answers are in `evals/llm/traps/`.", ""]
    for r in results:
        lines += [f"## {r['trap']} ({'PASS' if r['passed'] else 'FAIL'})", "", r["text"], ""]
    (OUT / "traps.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--traps", action="store_true", help="also run the trap tests (LLM calls on a cache miss)")
    args = parser.parse_args()
    rows = scoreboard()
    write_scoreboard(rows)
    print(f"scoreboard: {len(rows)} clips -> evals/llm/scoreboard.md")
    if args.traps:
        results = run_traps()
        write_traps(results)
        for r in results:
            print(f"trap {r['trap']:16} {'PASS' if r['passed'] else 'FAIL'}  grounded={r['grounded']}  cached={r['from_cache']}")


if __name__ == "__main__":
    main()
