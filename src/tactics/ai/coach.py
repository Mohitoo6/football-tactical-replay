"""The coach's explanation for one clip folder: facts -> LLM (cached) -> grounding check.

Used by scripts/generate_explanations.py and by the API, so both write the same files:
    <clip folder>/summary.json       the facts (the only thing the LLM sees)
    <clip folder>/explanation.json   the text, model and cache key
"""

import json
from pathlib import Path

from tactics.ai.grounding import GroundingReport, check_grounding
from tactics.ai.llm import explain
from tactics.ai.prompt import format_problems
from tactics.ai.summary import build_summary
from tactics.data.clips import load_clip


def coach_explanation(folder: Path, providers=None, complete_fn=None) -> tuple[dict, GroundingReport, dict]:
    """(explanation record, grounding report, facts) for the clip in `folder`; raises AllProvidersFailed on a cache miss
    without a working LLM. `providers` / `complete_fn` let tests use a fake model."""
    folder = Path(folder)
    summary = build_summary(load_clip(folder))
    (folder / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    kwargs = {"providers": providers} if providers is not None else {}
    if complete_fn is not None:
        kwargs["complete_fn"] = complete_fn
    result = explain(summary, folder / "explanation.json",
                     check=lambda text: check_grounding(text, summary).problems + format_problems(text), **kwargs)
    return result, check_grounding(result["text"], summary), summary
