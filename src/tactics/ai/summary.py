"""Turn a clip into a compact summary of facts for the LLM.

Everything in the summary is computed from tracking data by our own tested
code; the LLM only narrates it (CLAUDE.md, core design principle). We use
ball-in-play frames only: during stoppages the ball position is frozen
(DECISIONS.md, D11) and shape metrics are meaningless (e.g. goal celebrations).
"""

import numpy as np
import pandas as pd

from tactics.data.clips import Clip, match_clock
from tactics.geometry.formation import detect_formation, formation_label
from tactics.geometry.shape import shape_over_time

WINDOW_S = 2.0
METRICS = {  # summary key -> shape_over_time column
    "width_m": "width_m",
    "depth_m": "depth_m",
    "area_m2": "hull_area_m2",
    "back_line_m": "line_height_m",
}
DEFINITIONS = {
    "width_m": "distance between the team's widest outfield players across the pitch",
    "depth_m": "distance between the team's deepest and most advanced outfield players",
    "area_m2": "area of the shape around all outfield players (smaller = more compact)",
    "back_line_m": "average distance of the 4 deepest outfield players from their own goal line",
    "ball_carriers": "player nearest the ball (within 1.5 m, ball below 1 m) for at least 0.12 s, in time order",
}
# A change from the first to the last window counts as notable at or above these sizes.
NOTABLE_CHANGE = {"width_m": 5, "depth_m": 5, "area_m2": 150, "back_line_m": 5}
CARRIER_RADIUS_M = 1.5
CARRIER_MAX_BALL_HEIGHT_M = 1.0
MIN_CARRIER_FRAMES = 3
# Below this much open play (e.g. a penalty) a shape estimate would only describe a set-piece line-up.
MIN_OPEN_PLAY_S = 5


def in_play(clip: Clip) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Players and ball rows for frames where the ball is in play, up to the first goal.

    After a goal the ball can still be flagged "alive" for a moment while players
    run off to celebrate, which would distort the last shape metrics.
    """
    ball = clip.ball[clip.ball["alive"]]
    goals = clip.meta.get("goals", [])
    if goals:
        ball = ball[ball["time_s"] <= min(g["time_s"] for g in goals)]
    return clip.players[clip.players["frame"].isin(ball["frame"])], ball


def team_name(clip: Clip, side: str) -> str:
    return clip.meta["teams"][side]["name"]


def attacking_right(clip: Clip, side: str) -> bool:
    return side == clip.meta["focus_team"]


def timeline(clip: Clip) -> list[dict]:
    """Shape metrics for both teams, averaged over 2-second windows of ball-in-play time."""
    players, ball = in_play(clip)
    if ball.empty:
        return []
    start_s = float(clip.ball["time_s"].iloc[0])
    window_of_frame = ((ball.set_index("frame")["time_s"] - start_s) // WINDOW_S).astype(int)

    per_team = {}
    for side in ("home", "away"):
        metrics = shape_over_time(players, side, attacking_right(clip, side))
        metrics["window"] = metrics["frame"].map(window_of_frame)
        per_team[side] = metrics.groupby("window")[list(METRICS.values())].mean()

    rows = []
    for window in sorted(set(per_team["home"].index) & set(per_team["away"].index)):
        row = {"clock": match_clock(clip.meta["period"], start_s + window * WINDOW_S)}
        for side in ("home", "away"):
            values = per_team[side].loc[window]
            row[team_name(clip, side)] = {key: int(round(values[col])) for key, col in METRICS.items()}
        rows.append(row)
    return rows


def ball_carriers(clip: Clip) -> list[dict]:
    """Who was nearest the ball, in order (see DEFINITIONS["ball_carriers"])."""
    players, ball = in_play(clip)
    ball = ball[ball["z"] <= CARRIER_MAX_BALL_HEIGHT_M]
    merged = players.merge(ball[["frame", "time_s", "x", "y"]], on="frame", suffixes=("", "_ball"))
    merged["distance"] = np.hypot(merged["x"] - merged["x_ball"], merged["y"] - merged["y_ball"])
    nearest = merged.loc[merged.groupby("frame")["distance"].idxmin()].sort_values("frame")
    nearest = nearest[nearest["distance"] <= CARRIER_RADIUS_M]

    # Group consecutive frames with the same nearest player into runs; drop very short runs (noise).
    run_id = (nearest["player_id"] != nearest["player_id"].shift()).cumsum()
    runs = nearest.groupby(run_id).agg(player_id=("player_id", "first"), player=("player_name", "first"),
                                       team=("team", "first"), time_s=("time_s", "first"), frames=("frame", "size"))
    runs = runs[runs["frames"] >= MIN_CARRIER_FRAMES]
    runs = runs[runs["player_id"] != runs["player_id"].shift()]  # merge runs split by a dropped blip

    return [{"clock": match_clock(clip.meta["period"], r.time_s), "player": r.player, "team": team_name(clip, r.team)}
            for r in runs.itertuples()]


def notable_changes(rows: list[dict], teams: list[str]) -> list[dict]:
    """Metrics that changed by at least NOTABLE_CHANGE between the first and last window."""
    if len(rows) < 2:
        return []
    first, last = rows[0], rows[-1]
    changes = []
    for team in teams:
        for key, threshold in NOTABLE_CHANGE.items():
            before, after = first[team][key], last[team][key]
            if abs(after - before) >= threshold:
                changes.append({"team": team, "metric": key, "from": before, "to": after,
                                "from_clock": first["clock"], "to_clock": last["clock"]})
    return changes


def build_summary(clip: Clip) -> dict:
    """All facts the LLM may use for this clip, as a JSON-ready dict."""
    meta = clip.meta
    players, ball = in_play(clip)
    open_play_s = len(ball) / meta["frame_rate"]
    teams = []
    for side in (meta["focus_team"], "home" if meta["focus_team"] == "away" else "away"):
        result, positions = detect_formation(players, side, attacking_right(clip, side))
        teams.append({
            "name": team_name(clip, side),
            "role": "focus team (its move is shown)" if side == meta["focus_team"] else "opponent",
            "players_on_pitch": int(clip.players[clip.players["team"] == side].groupby("frame").size().max()),
            "official_formation": meta["teams"][side]["formation"],
            "shape_in_clip": formation_label(result, positions) if open_play_s >= MIN_OPEN_PLAY_S
            else f"n/a, under {MIN_OPEN_PLAY_S} s of open play",
        })

    rows = timeline(clip)
    return {
        "clip": {
            "title": meta["title"],
            "from_clock": meta["start_clock"],
            "to_clock": meta["end_clock"],
            "clip_seconds": int(round(len(clip.ball) / meta["frame_rate"])),
            "seconds_ball_in_play": int(round(open_play_s)),
        },
        "teams": teams,
        "goals": [{"clock": g["clock"], "player": g["player"], "team": team_name(clip, g["team"])}
                  for g in meta.get("goals", [])],
        "ball_carriers": ball_carriers(clip),
        "timeline": rows,
        "notable_changes": notable_changes(rows, [t["name"] for t in teams]),
        "definitions": DEFINITIONS,
    }
