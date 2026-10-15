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
from tactics.geometry.shape import ball_zone, outfield, players_behind_ball, shape_over_time

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
    "players_behind_ball": ("outfield players between the ball and their own goal (average over the window); "
                            "0 means the ball is closer to their goal than all of them, i.e. the defence has been bypassed"),
    "ball_zone": "where the ball mostly was in the window, seen from the focus team attacking towards the opponent's goal",
    "ball_carriers": "player nearest the ball (within 1.5 m, ball below 1 m) for at least 0.12 s, in time order",
}
# A change from the first to the last window counts as notable at or above these sizes.
NOTABLE_CHANGE = {"width_m": 5, "depth_m": 5, "area_m2": 150, "back_line_m": 5}
CARRIER_RADIUS_M = 1.5
CARRIER_MAX_BALL_HEIGHT_M = 1.0
MIN_CARRIER_FRAMES = 3
# Seconds before the recorded goal time at which the facts stop (roughly the shot's flight time).
GOAL_CUTOFF_S = 1.0
# Below this much open play (e.g. a penalty) a shape estimate would only describe a set-piece line-up.
MIN_OPEN_PLAY_S = 5
# Broadcast clips show only part of the pitch (meta "view": "partial", D28). A team's shape is measured
# only in frames where at least this many of its outfield players are visible.
PARTIAL_MIN_OUTFIELD = 7
# Back line, depth and players behind the ball depend on the deepest players, who are often out of view.
PARTIAL_METRICS = ("width_m", "area_m2")
CAMERA_NOTE = ("broadcast camera that pans and zooms: it shows only part of the pitch, so every shape number "
               "describes the players visible at that moment, not the whole team")


def in_play(clip: Clip) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Players and ball rows for frames where the ball is in play, up to the moment of the shot.

    The DFL goal time is when the ball crosses the line. We stop GOAL_CUTOFF_S
    earlier so the last picture shows the shot, not the ball already in the net
    (which would give "0 players behind the ball") or the celebrations after it.
    """
    ball = clip.ball[clip.ball["alive"]]
    goals = clip.meta.get("goals", [])
    if goals:
        ball = ball[ball["time_s"] <= min(g["time_s"] for g in goals) - GOAL_CUTOFF_S]
    return clip.players[clip.players["frame"].isin(ball["frame"])], ball


def partial_view(clip: Clip) -> bool:
    return clip.meta.get("view") == "partial"


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

    ball_by_frame = ball.set_index("frame")
    zones = ball_by_frame.apply(lambda b: ball_zone(b["x"], b["y"]), axis=1).groupby(window_of_frame)
    per_team, behind, visible = {}, {}, {}
    for side in ("home", "away"):
        team = outfield(players[players["team"] == side])
        counts = team.groupby("frame").size()
        if partial_view(clip):  # measure a shape only when most of the team is in view
            team = team[team["frame"].isin(counts[counts >= PARTIAL_MIN_OUTFIELD].index)]
        if team.empty:  # this team was never (enough) in view: no window can describe both teams
            return []
        metrics = shape_over_time(players[players["frame"].isin(team["frame"])], side, attacking_right(clip, side))
        metrics["window"] = metrics["frame"].map(window_of_frame)
        per_team[side] = metrics.groupby("window")[list(METRICS.values())].mean()
        visible[side] = counts.groupby(counts.index.map(window_of_frame)).mean()
        per_frame = team.groupby("frame").apply(lambda g: players_behind_ball(
            g[["x", "y"]].to_numpy(), ball_by_frame.loc[g.name, "x"], attacking_right(clip, side)))
        behind[side] = per_frame.groupby(per_frame.index.map(window_of_frame)).mean()

    rows = []
    for window in sorted(set(per_team["home"].index) & set(per_team["away"].index)):
        row = {"clock": match_clock(clip.meta["period"], start_s + window * WINDOW_S),
               "ball_zone": zones.get_group(window).mode().iloc[0]}
        for side in ("home", "away"):
            values = per_team[side].loc[window]
            row[team_name(clip, side)] = {key: int(round(values[col])) for key, col in METRICS.items()}
            row[team_name(clip, side)]["players_behind_ball"] = int(round(behind[side].loc[window]))
            if partial_view(clip):  # only what the visible players can show
                row[team_name(clip, side)] = {key: row[team_name(clip, side)][key] for key in PARTIAL_METRICS}
                row[team_name(clip, side)]["visible_players"] = int(round(visible[side].loc[window]))
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
            if key not in first[team]:
                continue
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
        if partial_view(clip):  # a formation needs the whole team in view
            shape = "n/a, the camera shows only part of the team"
        elif open_play_s >= MIN_OPEN_PLAY_S:
            shape = formation_label(*detect_formation(players, side, attacking_right(clip, side)))
        else:
            shape = f"n/a, under {MIN_OPEN_PLAY_S} s of open play"
        teams.append({
            "name": team_name(clip, side),
            "role": "focus team (its move is shown)" if side == meta["focus_team"] else "opponent",
            ("most_players_visible" if partial_view(clip) else "players_on_pitch"):
                int(clip.players[clip.players["team"] == side].groupby("frame").size().max()),
            "official_formation": meta["teams"][side]["formation"],
            "shape_in_clip": shape,
        })

    rows = timeline(clip)
    clip_facts = {
        "title": meta["title"],
        "from_clock": meta["start_clock"],
        "to_clock": meta["end_clock"],
        "clip_seconds": int(round(len(clip.ball) / meta["frame_rate"])),
        "seconds_ball_in_play": int(round(open_play_s)),
    }
    definitions = DEFINITIONS
    if partial_view(clip):
        clip_facts["camera"] = CAMERA_NOTE
        definitions = {
            "width_m": "distance between the team's widest visible outfield players across the pitch",
            "area_m2": "area of the shape around the team's visible outfield players (smaller = more compact)",
            "visible_players": (f"outfield players of the team in view (average over the window); shape numbers use "
                                f"only moments with at least {PARTIAL_MIN_OUTFIELD} in view"),
            "ball_zone": DEFINITIONS["ball_zone"],
            "ball_carriers": DEFINITIONS["ball_carriers"],
        }
    return {
        "clip": clip_facts,
        "teams": teams,
        "goals": [{"clock": g["clock"], "player": g["player"], "team": team_name(clip, g["team"])}
                  for g in meta.get("goals", [])],
        "ball_carriers": ball_carriers(clip),
        "timeline": rows,
        "notable_changes": notable_changes(rows, [t["name"] for t in teams]),
        "definitions": definitions,
    }
