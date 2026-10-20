"""Vyuh (football tactical replay): pick a clip, watch the shapes move, read the coach's explanation.

    uv run streamlit run app/streamlit_app.py

The app only reads files that were built offline (clips/<id>/): the video, the
facts summary and the cached explanation. It never calls an LLM, so it needs no
API keys and cannot hit free-tier rate limits (DECISIONS.md, D5).
"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
try:
    from tactics.ai.grounding import check_grounding
    from tactics.ai.prompt import format_problems
except ModuleNotFoundError:  # running without the package installed (e.g. plain `streamlit run`)
    sys.path.insert(0, str(ROOT / "src"))
    from tactics.ai.grounding import check_grounding
    from tactics.ai.prompt import format_problems

CLIPS_DIR = ROOT / "clips"
METRICS = {
    "back_line_m": "Back line: distance of the 4 deepest outfield players from their own goal (m)",
    "area_m2": "Team area: space enclosed by the outfield players (m²)",
    "width_m": "Width: widest outfield players across the pitch (m)",
    "depth_m": "Depth: deepest to most advanced outfield player (m)",
    "players_behind_ball": "Outfield players between the ball and their own goal",
}
DATA_CREDIT = (
    "Tracking data: Sportec Open DFL data — Bassek, Rein, Weber & Memmert, *An integrated dataset of "
    "spatiotemporal and event data in elite soccer*, Scientific Data 12, 195 (2025), CC-BY 4.0."
)


@st.cache_data
def load_clip_files(clip_id: str) -> tuple[dict, dict, dict]:
    """meta.json, summary.json and explanation.json of one clip."""
    folder = CLIPS_DIR / clip_id
    return tuple(json.loads((folder / name).read_text()) for name in ("meta.json", "summary.json", "explanation.json"))


def available_clips() -> dict[str, str]:
    """Clip title -> clip id, for clips that have a video and an explanation."""
    clips = {}
    for meta_path in sorted(CLIPS_DIR.glob("*/meta.json")):
        folder = meta_path.parent
        if (folder / "video.mp4").exists() and (folder / "explanation.json").exists():
            meta = json.loads(meta_path.read_text())
            clips[f"{meta['title']} ({meta['start_clock']})"] = folder.name
    return clips


def metric_table(summary: dict, metric: str) -> pd.DataFrame:
    """One column per team, one row per 2-second window, for the chart."""
    teams = [team["name"] for team in summary["teams"]]
    rows = {row["clock"]: {team: row[team][metric] for team in teams} for row in summary["timeline"]}
    return pd.DataFrame.from_dict(rows, orient="index")


def main() -> None:
    st.set_page_config(page_title="Vyuh · football tactical replay", page_icon="⚽", layout="wide")
    st.title("⚽ Vyuh · football tactical replay")
    st.caption("Real player-tracking data → team-shape geometry → a coach's explanation that only uses the measured facts.")

    clips = available_clips()
    if not clips:
        st.error("No clips found. Build them with `scripts/build_clips.py`, `render_clip.py --for-app` and `generate_explanations.py`.")
        return

    with st.sidebar:
        st.header("Choose a clip")
        title = st.selectbox("Clip", list(clips), label_visibility="collapsed")
        st.markdown(
            "**Reading the pitch**\n"
            "- Dots: players (jersey numbers); yellow: ball, hidden when out of play\n"
            "- Shaded shape: each team's outfield players\n"
            "- Lines: team-mates in the same line (back four, midfield, attack)\n"
            "- The team whose move is shown always attacks left → right"
        )

    clip_id = clips[title]
    meta, summary, explanation = load_clip_files(clip_id)
    home, away = meta["teams"]["home"], meta["teams"]["away"]
    st.subheader(title)
    st.markdown(f"**{home['name']}** v **{away['name']}** · clip {meta['start_clock']}–{meta['end_clock']} · "
                f"ball in play for {summary['clip']['seconds_ball_in_play']} of {summary['clip']['clip_seconds']} s")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.video(str(CLIPS_DIR / clip_id / "video.mp4"))
        if summary["timeline"]:
            first = summary["timeline"][0]
            present = [m for m in METRICS if all(m in v for k, v in first.items() if isinstance(v, dict))]
            metric = st.selectbox("Chart", present, format_func=METRICS.get)  # broadcast clips have fewer metrics
            st.line_chart(metric_table(summary, metric), x_label="Match clock", y_label=METRICS[metric].split(":")[0])
        else:
            st.info("The ball was hardly in play in this clip, so there is no shape timeline to chart.")

    with right:
        st.markdown("### Coach's explanation")
        st.markdown(explanation["text"])
        report = check_grounding(explanation["text"], summary)
        problems = report.problems + format_problems(explanation["text"])
        if not problems:
            st.success(f"Checked: all {report.numbers_checked} numbers, match times and formations above appear in "
                       "the tracking facts below.")
        else:
            st.warning("Check found: " + "; ".join(problems))
        st.caption(f"Written by `{explanation['model']}` (prompt {explanation['prompt_version']}) from the facts below. "
                   "General football principles are used only in the coach's view.")
        with st.expander("Facts the AI was given"):
            st.json(summary, expanded=False)

    with st.expander("How this works"):
        st.markdown(
            "1. **Data:** real optical tracking (25 frames per second) from the DFL open dataset, cut into short clips.\n"
            "2. **Geometry:** our tested code computes each team's shape, width, depth, area, back line, "
            "players behind the ball and an estimated shape (e.g. 4-1-4-1).\n"
            "3. **Facts:** those numbers are summarised into a small JSON file for the clip.\n"
            "4. **Explanation:** a free-tier LLM writes the text from that JSON only; a checker verifies every "
            "number, time and formation, and the model gets one rewrite if anything is unsupported.\n\n"
            "Limits: the shape estimate is reliable for a settled defensive block, much less for a team in "
            "possession; the checker confirms numbers exist in the facts, not that each is tied to the right team."
        )
    st.caption(DATA_CREDIT if meta.get("data_kind") != "video" else
               f"{meta['credit']}. Player and ball positions were computed from the drone video by this project "
               "(Phase 7), not supplied by a tracking provider.")


main()
