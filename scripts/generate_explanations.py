"""Generate (or reuse cached) AI explanations for every clip and check their grounding.

    uv run python scripts/generate_explanations.py              # all clips
    uv run python scripts/generate_explanations.py musiala-winner

For each clip this writes, inside clips/<clip_id>/:
    summary.json       the facts we computed (the only thing the LLM sees)
    explanation.json   the LLM's text, model and cache key (reused while the facts and prompt are unchanged)
and an evaluation sheet evals/llm/<clip_id>.md with the grounding report and a
checklist for a human reviewer. Needs API keys in .env (see .env.example) on a cache miss.
"""

import json
import sys
from pathlib import Path

from tactics.ai.grounding import check_grounding
from tactics.ai.llm import AllProvidersFailed, explain
from tactics.ai.prompt import format_problems
from tactics.ai.summary import build_summary
from tactics.data.clips import load_clip

ROOT = Path(__file__).resolve().parents[1]
CLIPS_DIR = ROOT / "clips"
EVALS_DIR = ROOT / "evals" / "llm"

CHECKLIST = [
    "\"What happened\" uses only facts present in summary.json",
    "Names the main tactical change correctly",
    "Coach's view: every point is tied to a stated fact and phrased as interpretation",
    "Coach's view: the football reasoning is sound (would a coach agree?)",
    "Readable for a non-expert (terms explained)",
    "No filler or invented events (passes, tackles, shot types, match context)",
]


def evaluation_sheet(clip_id: str, result: dict, report) -> str:
    def listed(items):
        return ", ".join(items) if items else "none"

    lines = [
        f"# LLM evaluation — {clip_id}", "",
        f"- Model: `{result['model']}` via {result['provider']} (prompt {result['prompt_version']}, {result['created_utc']})",
        f"- Facts: [`clips/{clip_id}/summary.json`](../../clips/{clip_id}/summary.json)", "",
        "## Explanation", "", result["text"], "",
        "## Automatic grounding check", "",
        f"- Result: **{'PASS' if report.passed else 'FAIL'}** ({report.numbers_checked} numbers, clocks and formations checked)",
        f"- Unsupported numbers: {listed(report.unsupported_numbers)}",
        f"- Unsupported clocks: {listed(report.unsupported_clocks)}",
        f"- Unsupported formations: {listed(report.unsupported_formations)}",
        f"- Capitalised words not in the facts (review by hand): {listed(report.unknown_capitalised)}",
        f"- Format problems: {listed(format_problems(result['text']))}",
        f"- Repaired: {'yes, first answer from ' + result['repair']['first_model'] + ' had ' + '; '.join(result['repair']['first_problems']) if result.get('repair') else 'no'}", "",
        "## Human review", "",
        *[f"- [ ] {item}" for item in CHECKLIST], "",
        "Reviewer notes:", "",
    ]
    return "\n".join(lines)


def main(only: list[str]) -> int:
    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for meta_path in sorted(CLIPS_DIR.glob("*/meta.json")):
        folder = meta_path.parent
        if only and folder.name not in only:
            continue
        summary = build_summary(load_clip(folder))
        (folder / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
        try:
            result = explain(summary, folder / "explanation.json",
                             check=lambda text: check_grounding(text, summary).problems + format_problems(text))
        except AllProvidersFailed as error:
            print(f"{folder.name}: no explanation ({error})")
            failures += 1
            continue

        report = check_grounding(result["text"], summary)
        sheet = EVALS_DIR / f"{folder.name}.md"
        if not result["from_cache"] or not sheet.exists():
            sheet.write_text(evaluation_sheet(folder.name, result, report) + "\n")
        source = "cache" if result["from_cache"] else result["model"]
        if result.get("repair"):
            source += f" (repaired; first answer had {result['repair']['first_problems']})"
        print(f"{folder.name}: {len(result['text'].split())} words from {source}; grounding "
              f"{'PASS' if report.passed else 'FAIL'} ({report.numbers_checked} checked; unsupported: "
              f"{report.unsupported_numbers + report.unsupported_clocks + report.unsupported_formations}; "
              f"capitalised to review: {report.unknown_capitalised})")
        shape_problems = format_problems(result["text"])
        if shape_problems:
            print(f"  format problems: {shape_problems}")
        failures += not report.passed or bool(shape_problems)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
