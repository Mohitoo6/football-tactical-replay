"""Read the SoccerTrack top-view ground truth: bounding boxes per frame and GNSS positions.

Files (from kaggle.com/datasets/atomscott/soccertrack, LGPL-3.0):
    top_view/annotations/D_*.csv   one row per video frame; a 39x39 px box per player and the ball
    GNSS/G_*.csv                   one row per 0.1 s; latitude/longitude per player
Both use a three-row header: team id, player id, attribute.
"""

from pathlib import Path

import pandas as pd

from tactics.video.calibration import PitchCalibration


def load_boxes(path: Path) -> pd.DataFrame:
    """One row per object per frame: frame, team ("0", "1" or "BALL"), player_id, box and box centre in pixels."""
    wide = pd.read_csv(path, header=[0, 1, 2], index_col=0)
    long = wide.stack(level=[0, 1], future_stack=True).reset_index()
    long.columns = ["frame", "team", "player_id", *long.columns[3:]]
    long = long.dropna(subset=["bb_left", "bb_top"])
    long["cx"] = long["bb_left"] + long["bb_width"] / 2
    long["cy"] = long["bb_top"] + long["bb_height"] / 2
    return long.sort_values(["frame", "team", "player_id"]).reset_index(drop=True)


def load_gnss(path: Path, calibration: PitchCalibration) -> pd.DataFrame:
    """One row per player per GNSS sample: sample (0, 1, 2, ...), team, player_id and x, y in pitch metres."""
    wide = pd.read_csv(path, header=[0, 1, 2], index_col=0)
    long = wide.stack(level=[0, 1], future_stack=True).reset_index()
    long.columns = ["time", "team", "player_id", *long.columns[3:]]
    long = long.dropna(subset=["Lat", "Lon"])
    long["sample"] = long["time"].map({t: i for i, t in enumerate(wide.index)})
    # The GNSS keypoints are stored as (lon, lat).
    xy = calibration.to_pitch(long[["Lon", "Lat"]].to_numpy())
    long["x"], long["y"] = xy[:, 0], xy[:, 1]
    return long[["sample", "time", "team", "player_id", "x", "y"]].reset_index(drop=True)
