"""The backend in one place: list and read clips, create them from any input, and explain them (D32).

Two ways in, one analysis:
1. coordinate data: our CSV/Excel template, or a provider format (Metrica, SkillCorner, Sportec) via kloppy;
2. a top-view drone video (needs `uv sync --group video`; heavy, so it runs locally).
Both produce a standard clip, which the same geometry and coach turn into overlays and an explanation.

Bundled clips live in clips/ (committed); clips made from uploads live in data/user_clips/ (git-ignored).
"""

import json
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import numpy as np

from tactics.ai.evaluate import evaluate
from tactics.ai.grounding import check_grounding
from tactics.data.clips import Clip, load_clip, save_clip
from tactics.data.report import QualityReport
from tactics.data.upload import (check_input, from_kloppy, from_template, load_provider, read_table,
                                 to_clip)
from tactics.data.validate import find_problems
from tactics.geometry.shape import hull_vertices, outfield, team_shape

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "clips"
USER = ROOT / "data" / "user_clips"
CLIP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
Progress = Callable[[float, str], None]


class ClipNotFound(LookupError):
    pass


# --- reading clips -----------------------------------------------------------------------------

def clip_folder(clip_id: str) -> Path:
    """The folder of a clip (user clips first, then bundled); ClipNotFound for unknown or unsafe ids."""
    if not CLIP_ID.match(clip_id):
        raise ClipNotFound(clip_id)
    for root in (USER, BUNDLED):
        folder = root / clip_id
        if (folder / "meta.json").exists():
            return folder
    raise ClipNotFound(clip_id)


def list_clips() -> list[dict]:
    """Every clip with what a picker needs: id, title, kind, clock, teams, and whether video/explanation exist."""
    clips = []
    for root, origin in ((BUNDLED, "bundled"), (USER, "uploaded")):
        for meta_path in sorted(root.glob("*/meta.json")) if root.exists() else []:
            meta = json.loads(meta_path.read_text())
            if meta["clip_id"].startswith("local-"):
                continue  # broadcast-experiment outputs, not part of the product
            clips.append({
                "clip_id": meta["clip_id"], "title": meta["title"], "origin": origin,
                "data_kind": meta.get("data_kind", "tracking"),
                "start_clock": meta["start_clock"], "end_clock": meta["end_clock"],
                "teams": {side: meta["teams"][side]["name"] for side in ("home", "away")},
                "has_video": (meta_path.parent / "video.mp4").exists(),
                "has_explanation": (meta_path.parent / "explanation.json").exists(),
            })
    return clips


def clip_payload(clip_id: str, step: int = 1) -> dict:
    """Everything a frontend needs to animate and explain a clip, as JSON-ready data.

    frames[i]: time, ball (or null when not in play/visible), players, and per team the outfield shape
    (hull corners and width, depth, area, back line). `step` keeps every n-th frame (2 = half the data).
    """
    folder = clip_folder(clip_id)
    clip = load_clip(folder)
    meta = clip.meta
    focus = meta["focus_team"]
    players_by_frame = dict(tuple(clip.players.groupby("frame")))
    frames = []
    for row in clip.ball.iloc[::max(step, 1)].itertuples(index=False):
        here = players_by_frame.get(row.frame, clip.players.iloc[:0])
        shapes = {}
        for side in ("home", "away"):
            points = outfield(here[here["team"] == side])[["x", "y"]].to_numpy(float)
            if len(points) >= 3:
                metrics = team_shape(points, attacking_right=side == focus)
                shapes[side] = {"hull": _round(hull_vertices(points)), "width_m": round(metrics.width_m, 1),
                                "depth_m": round(metrics.depth_m, 1), "area_m2": round(metrics.hull_area_m2),
                                "back_line_m": round(metrics.line_height_m, 1)}
        frames.append({
            "frame": int(row.frame), "time_s": round(float(row.time_s), 3),
            "ball": [round(float(row.x), 2), round(float(row.y), 2)] if bool(row.alive) else None,
            "players": [{"id": p.player_id, "team": p.team, "name": p.player_name,
                         "number": None if p.jersey is None or p.jersey != p.jersey else int(p.jersey),
                         "keeper": p.position == "Goalkeeper", "x": round(float(p.x), 2), "y": round(float(p.y), 2)}
                        for p in here.itertuples(index=False)],
            "shapes": shapes,
        })
    summary_path, explanation_path = folder / "summary.json", folder / "explanation.json"
    facts = json.loads(summary_path.read_text()) if summary_path.exists() else None
    explained = json.loads(explanation_path.read_text()) if explanation_path.exists() else None
    return {
        "meta": meta,
        "pitch": {"length_m": 105.0, "width_m": 68.0, "origin": "centre"},
        "frame_rate": meta["frame_rate"] / max(step, 1),
        "frames": frames,
        "facts": facts,
        "explanation": explained,
        # the cached explanation checked against the facts again (pure Python, no LLM call)
        "grounding": grounding_json(check_grounding(explained["text"], facts)) if facts and explained else None,
        # claims (right team, order, direction), key facts said, invented events (tactics/ai/evaluate.py, D34)
        "checks": evaluate(explained["text"], facts).as_json() if facts and explained else None,
        "has_video": (folder / "video.mp4").exists(),
        "has_source": (folder / SOURCE_VIDEO).exists(),  # the original (drone) video, to play beside the replay
    }


def explanation(clip_id: str, providers=None, complete_fn=None) -> dict:
    """The coach's explanation (cached per facts and prompt), with its grounding result."""
    from tactics.ai.coach import coach_explanation

    result, report, facts = coach_explanation(clip_folder(clip_id), providers=providers, complete_fn=complete_fn)
    return {**result, "grounding": grounding_json(report), "checks": evaluate(result["text"], facts).as_json()}


def grounding_json(report) -> dict:
    """A grounding report as JSON: did every number, clock and formation come from the facts?"""
    return {"passed": report.passed, "numbers_checked": report.numbers_checked, "problems": report.problems}


# --- creating clips ----------------------------------------------------------------------------

def report_json(report: QualityReport) -> dict:
    return {"status": report.status, "checks": [asdict(c) for c in report.checks]}


def create_from_table(path: Path, title: str, units: str = "metres", focus_team: str = "home",
                      team_names: dict[str, str] | None = None, start_s: float = 0.0) -> tuple[str | None, dict]:
    """Our template (CSV/Excel) -> saved user clip. Returns (clip id or None, quality report)."""
    report = QualityReport()
    try:
        table = read_table(path)
    except Exception as error:  # an unreadable file is the user's input, not a server error
        report.add("file readable", False, str(error)[:200], "a CSV or Excel file")
        return None, report_json(report)
    data = from_template(table, report, units=units, team_names=team_names)
    return _finish(data, report, title, focus_team, start_s)


def create_from_provider(provider: str, files: dict[str, Path], title: str, period: int, start_s: float,
                         end_s: float, focus_team: str = "home") -> tuple[str | None, dict]:
    """A provider's files (via kloppy), cut to [start_s, end_s] of `period` -> saved user clip."""
    report = QualityReport()
    try:
        dataset = load_provider(provider, files)
    except Exception as error:
        report.add("file readable", False, f"{type(error).__name__}: {str(error)[:200]}", f"{provider} files")
        return None, report_json(report)
    data = from_kloppy(dataset, period, start_s, end_s, source=f"{provider} data uploaded by the user")
    return _finish(data, report, title, focus_team, start_s, period)


def create_from_drone_video(path: Path, title: str, start_s: float = 0.0, pitch_m: tuple[float, float] = (105.0, 68.0),
                            progress: Progress | None = None) -> tuple[str | None, dict]:
    """A top-view drone video -> saved user clip (minutes of processing; needs the video dependency group)."""
    from tactics.video.pipeline import process_video

    clip_id = new_clip_id(title)
    clip, report = process_video(Path(path), clip_id, title, *pitch_m, progress=progress, start_s=start_s)
    if clip is None:
        return None, report_json(report)
    save_clip(clip, USER)
    if progress:
        progress(0.99, "preparing the original video to play beside the replay")
    save_source_video(Path(path), USER / clip_id)
    return clip_id, report_json(report)


SOURCE_VIDEO = "source.mp4"


def save_source_video(video: Path, folder: Path, max_width: int = 1920) -> bool:
    """Keep the original video next to its clip, re-encoded for browsers (H.264, at most 1920 px wide so players stay
    visible, no sound), so the replay can play it under the 2D pitch. Needs ffmpeg; without it the clip simply has no
    video (returns False)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    out = Path(folder) / SOURCE_VIDEO
    command = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-an",
               "-vf", f"scale='min({max_width},iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    try:
        subprocess.run(command, check=True, timeout=1800)
    except (subprocess.SubprocessError, OSError):
        out.unlink(missing_ok=True)
        return False
    return True


def new_clip_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "clip"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def _finish(data, report: QualityReport, title: str, focus_team: str, start_s: float, period: int = 1):
    if data is None:
        return None, report_json(report)
    check_input(data, report)
    if report.status == "rejected":
        return None, report_json(report)
    clip: Clip = to_clip(data, new_clip_id(title), title, focus_team=focus_team, start_s=start_s, period=period)
    problems = find_problems(clip.players, clip.ball)
    report.add("clip consistent", not problems, "; ".join(problems) or "no problems", "no problems", blocking=False)
    save_clip(clip, USER)
    return clip.meta["clip_id"], report_json(report)


def _round(points: np.ndarray) -> list[list[float]]:
    return [[round(float(x), 2), round(float(y), 2)] for x, y in points]
