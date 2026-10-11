"""Define, build, save and load short clips (see DECISIONS.md, D2).

A clip lives in its own folder:
    clips/<clip_id>/players.parquet   one row per player per frame
    clips/<clip_id>/ball.parquet      one row per frame
    clips/<clip_id>/meta.json         teams, formations, times, attribution
"""

import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from tactics.data.load import Match, frame_at, get_frames
from tactics.data.normalize import orient_for_team

DFL_ATTRIBUTION = (
    "Bassek, M., Rein, R., Weber, H. & Memmert, D. An integrated dataset of spatiotemporal "
    "and event data in elite soccer. Scientific Data 12, 195 (2025). CC-BY 4.0."
)


@dataclass
class ClipSpec:
    clip_id: str
    match_id: str
    title: str
    period: int
    start_s: float  # seconds since the start of the period
    end_s: float
    focus_team: str  # "home" or "away"; this team attacks left to right in the clip


@dataclass
class Clip:
    meta: dict
    players: pd.DataFrame
    ball: pd.DataFrame


def load_clip_specs(path: Path) -> list[ClipSpec]:
    """Read clip definitions from a TOML file with one [[clip]] table per clip."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return [ClipSpec(**{"clip_id": c.pop("id"), **c}) for c in data["clip"]]


def build_clip(match: Match, spec: ClipSpec, goals: pd.DataFrame | None = None) -> Clip:
    """Cut one clip out of a loaded match and orient it for the focus team.

    `goals` (from `load.find_goals`) adds the goals that happen inside the clip to its metadata.
    """
    start = frame_at(match, spec.period, spec.start_s)
    end = frame_at(match, spec.period, spec.end_s)
    players, ball = get_frames(match, start, end)
    players, ball = orient_for_team(players, ball, spec.focus_team)

    meta = {
        **asdict(spec),
        "start_clock": match_clock(spec.period, spec.start_s),
        "end_clock": match_clock(spec.period, spec.end_s),
        "start_frame": start,
        "end_frame": end,
        "frame_rate": match.frame_rate,
        "teams": {
            team.side: {"name": team.name, "formation": team.formation} for team in (match.home, match.away)
        },
        "goals": _goals_in_clip(goals, spec),
        "coordinates": "metres, origin at pitch centre; focus_team attacks left to right",
        "source": DFL_ATTRIBUTION,
    }
    return Clip(meta, players, ball)


def save_clip(clip: Clip, clips_dir: Path) -> Path:
    """Write a clip to `clips_dir/<clip_id>/` and return that folder."""
    folder = Path(clips_dir) / clip.meta["clip_id"]
    folder.mkdir(parents=True, exist_ok=True)
    clip.players.to_parquet(folder / "players.parquet", index=False)
    clip.ball.to_parquet(folder / "ball.parquet", index=False)
    (folder / "meta.json").write_text(json.dumps(clip.meta, indent=2, ensure_ascii=False) + "\n")
    return folder


def load_clip(folder: Path) -> Clip:
    """Read a clip folder written by `save_clip`."""
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text())
    return Clip(meta, pd.read_parquet(folder / "players.parquet"), pd.read_parquet(folder / "ball.parquet"))


def _goals_in_clip(goals: pd.DataFrame | None, spec: ClipSpec) -> list[dict]:
    if goals is None:
        return []
    inside = goals[(goals["period"] == spec.period) & goals["time_s"].between(spec.start_s, spec.end_s)]
    return [
        {"time_s": round(float(g.time_s), 2), "clock": match_clock(spec.period, g.time_s), "team": g.team, "player": g.player}
        for g in inside.itertuples()
    ]


def match_clock(period: int, time_s: float) -> str:
    """Format a period-relative time as a match clock, e.g. period 2, 2595 s -> "88:15"."""
    total = int(time_s) + (45 * 60 if period == 2 else 0)
    return f"{total // 60}:{total % 60:02d}"
