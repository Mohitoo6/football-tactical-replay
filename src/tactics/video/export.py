"""Turn video tracks into a clip in the same format as the DFL clips (DECISIONS.md, D2),
so the existing overlays, facts summary and AI coach work on drone video unchanged.
"""

import numpy as np
import pandas as pd

from tactics.data.clips import Clip, match_clock
from tactics.data.load import BALL_COLUMNS, PLAYER_COLUMNS
from tactics.data.normalize import rotate_180
from tactics.video.track import lab_colours

SOCCERTRACK_ATTRIBUTION = (
    "Scott, A., Uchida, I., Onishi, M., Kameda, Y., Fukui, K. & Fujii, K. SoccerTrack: A Dataset and Tracking "
    "Algorithm for Soccer with Fish-eye and Drone Videos. CVPR Workshops (2022). Data: LGPL-3.0."
)


def shirt_names(lab_by_team: pd.DataFrame) -> dict[str, str]:
    """"lighter" / "darker" shirts per team. Colour names are unreliable under green-tinted
    light (blue shirts measure close to green), but which team is lighter is not."""
    lighter = lab_by_team["L"].idxmax()
    return {team: "lighter" if team == lighter else "darker" for team in lab_by_team.index}


def tracks_to_clip(tracks: pd.DataFrame, teams: pd.Series, ball: pd.DataFrame, fps: float, clip_id: str,
                   title: str, start_s: float, min_track_frames: int = 30) -> Clip:
    """Build a Clip from tracks (frame, track_id, x_m, y_m, b, g, r) and a followed ball (frame, x_m, y_m).

    - Only the two teams' tracks of at least `min_track_frames` are kept, at most 11 per team per frame.
    - The lighter-shirted team is "home" (drawn white); the clip is rotated so it attacks left to right
      (judged from where its keeper stands).
    - Frames where the ball is not visible keep its last known position but are marked not alive,
      so the overlay hides it and the facts summary ignores those frames.
    """
    data = tracks.assign(team=tracks["track_id"].map(teams))
    data = data[data["team"].isin(["A", "B"])]
    lengths = data.groupby("track_id")["frame"].transform("size")
    data = data[lengths >= min_track_frames]
    # At most 11 per team per frame: keep the longest tracks.
    data = data.assign(length=data.groupby("track_id")["frame"].transform("size"))
    data = data.sort_values("length", ascending=False).groupby(["frame", "team"]).head(11)

    keepers = teams.attrs.get("keepers", {})
    shades = shirt_names(pd.DataFrame(lab_colours(data), index=data.index, columns=["L", "A", "B"]).groupby(data["team"]).mean())
    # The lighter-shirted team is "home", which the overlay draws in white, so the picture matches the names.
    side = {team: "home" if shade == "lighter" else "away" for team, shade in shades.items()}
    numbers = {}
    for team, group in data.groupby("team"):
        for n, track_id in enumerate(group.groupby("track_id")["length"].first().sort_values(ascending=False).index, 1):
            numbers[track_id] = n
    players = pd.DataFrame({
        "frame": data["frame"].astype(int),
        "period": 1,
        "time_s": start_s + data["frame"] / fps,
        "team": data["team"].map(side),
        "player_id": data["team"] + data["track_id"].map(numbers).astype(str),
        "player_name": "Player " + data["team"] + data["track_id"].map(numbers).astype(str),
        "jersey": data["track_id"].map(numbers),
        "position": np.where(data["track_id"].isin(keepers.values()), "Goalkeeper", None),
        "x": data["x_m"],
        "y": data["y_m"],
    }).sort_values(["frame", "team", "jersey"]).reset_index(drop=True)[PLAYER_COLUMNS]

    frames = pd.DataFrame({"frame": range(int(tracks["frame"].min()), int(tracks["frame"].max()) + 1)})
    ball_all = frames.merge(ball, on="frame", how="left")
    visible = ball_all["x_m"].notna()
    ball_table = pd.DataFrame({
        "frame": ball_all["frame"],
        "period": 1,
        "time_s": start_s + ball_all["frame"] / fps,
        "x": ball_all["x_m"].ffill().bfill(),
        "y": ball_all["y_m"].ffill().bfill(),
        "z": 0.0,
        "alive": visible,
        "owning_team": None,
    })[BALL_COLUMNS]

    home_keeper_x = players.loc[(players["team"] == "home") & (players["position"] == "Goalkeeper"), "x"].mean()
    rotated = bool(home_keeper_x > 0)
    if rotated:  # home keeper on the right means home attacks right to left: rotate
        players, ball_table = rotate_180(players), rotate_180(ball_table)

    end_s = start_s + float(frames["frame"].max()) / fps
    meta = {
        "clip_id": clip_id,
        "match_id": None,
        "title": title,
        "period": 1,
        "start_s": start_s,
        "end_s": end_s,
        "focus_team": "home",
        "start_clock": match_clock(1, start_s),
        "end_clock": match_clock(1, end_s),
        "frame_rate": fps,
        "rotated": rotated,  # positions were turned 180 degrees from the video's pitch coordinates
        "direction_known": bool(np.isfinite(home_keeper_x)),  # which goal each team attacks comes from its keeper
        "teams": {side[t]: {"name": f"Team {t} ({shades[t]} shirts)", "formation": None}
                  for t in ("A", "B")},
        "goals": [],
        "data_kind": "video",
        "ball_hidden_text": "Ball not visible",
        "coordinates": "metres, origin at pitch centre; from drone video via automatic calibration",
        "source": SOCCERTRACK_ATTRIBUTION,
        "credit": "Video & ground truth: SoccerTrack (Scott et al. 2022), LGPL-3.0 · positions computed by this project",
    }
    return Clip(meta, players, ball_table)
