"""Measure a processed broadcast clip against hand labels (scripts/label_frames.py).

    uv run --group video python scripts/evaluate_broadcast.py local-euro-copenhagen [--tag baseline]

What is measured is what the video shows:
- people: the rings drawn in the frame (clips/<id>/detections.parquet when present, otherwise the clip's
  players projected through the camera), matched one-to-one to labelled feet within 25 px;
- ball: our ball in the frame within 15 px of the labelled ball, and how often we show a ball where
  there is none (false-ball rate).
Appends a row to evals/broadcast/<id>.csv.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from tactics.broadcast.calibrate import H_COLUMNS, project
from tactics.data.clips import load_clip

ROOT = Path(__file__).resolve().parents[1]
PERSON_PX, BALL_PX = 25.0, 15.0


def homography(camera: pd.DataFrame, frame: int) -> np.ndarray | None:
    row = camera[camera["frame"] == frame]
    if row.empty or not bool(row["valid"].iloc[0]):
        return None
    return row[H_COLUMNS].to_numpy(dtype=float).reshape(3, 3)


def shown_people(folder: Path, clip, camera: pd.DataFrame, frame: int) -> np.ndarray:
    """Pixel positions of the rings drawn in this frame."""
    detections = folder / "detections.parquet"
    if detections.exists():
        table = pd.read_parquet(detections)
        return table.loc[table["frame"] == frame, ["px", "py"]].to_numpy(dtype=float)
    h = homography(camera, frame)
    players = clip.players[clip.players["frame"] == frame]
    if h is None or players.empty:
        return np.empty((0, 2))
    xy = players[["x", "y"]].to_numpy(dtype=float) * (-1 if clip.meta.get("rotated") else 1)
    return project(xy, h)


def shown_ball(folder: Path, clip, camera: pd.DataFrame, frame: int) -> np.ndarray | None:
    track = folder / "ball_track.parquet"
    if track.exists():
        table = pd.read_parquet(track)
        shown = table["confirmed"] if "confirmed" in table else table["visible"]
        row = table[(table["frame"] == frame) & shown]
        return None if row.empty else row[["px", "py"]].to_numpy(dtype=float)[0]
    h = homography(camera, frame)
    ball = clip.ball[clip.ball["frame"] == frame]
    if h is None or ball.empty or not bool(ball["alive"].iloc[0]):
        return None
    xy = ball[["x", "y"]].to_numpy(dtype=float) * (-1 if clip.meta.get("rotated") else 1)
    return project(xy, h)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clip_id")
    parser.add_argument("--tag", default="", help="a short name for this run, e.g. baseline")
    args = parser.parse_args()

    labels = json.loads((ROOT / "data" / "processed" / "labels" / f"{args.clip_id}.json").read_text())
    folder = ROOT / "clips" / args.clip_id
    clip = load_clip(folder)
    camera = pd.read_parquet(folder / "camera.parquet")

    found = labelled = shown = 0
    for frame, feet in labels["people"].items():
        truth = np.array(feet, dtype=float).reshape(-1, 2)
        ours = shown_people(folder, clip, camera, int(frame))
        labelled += len(truth)
        shown += len(ours)
        if len(truth) and len(ours):
            distance = np.linalg.norm(truth[:, None] - ours[None], axis=2)
            rows, cols = linear_sum_assignment(distance)
            found += int((distance[rows, cols] <= PERSON_PX).sum())

    ball_seen = ball_hit = ball_false = ball_given = shown_right = 0
    for frame, point in labels["ball"].items():
        ours = shown_ball(folder, clip, camera, int(frame))
        ball_given += ours is not None
        if point is None:
            ball_false += ours is not None
            continue
        ball_seen += 1
        right = ours is not None and np.linalg.norm(np.array(point) - ours) <= BALL_PX
        ball_hit += right
        shown_right += right
    not_visible = len(labels["ball"]) - ball_seen

    row = {
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "tag": args.tag,
        "people_labelled": labelled, "people_found": found / max(labelled, 1),
        "people_precision": found / max(shown, 1),
        "ball_frames_visible": ball_seen, "ball_correct": ball_hit / max(ball_seen, 1),
        "false_ball_rate": ball_false / max(not_visible, 1) if not_visible else float("nan"),
        "ball_shown": ball_given / max(len(labels["ball"]), 1),
        "ball_right_when_shown": shown_right / max(ball_given, 1),
    }
    out = ROOT / "evals" / "broadcast" / f"{args.clip_id}.csv"
    table = pd.read_csv(out) if out.exists() else pd.DataFrame()
    pd.concat([table, pd.DataFrame([row])], ignore_index=True).round(4).to_csv(out, index=False)
    print(f"people found {row['people_found']:.1%} of {labelled} labelled (precision {row['people_precision']:.1%}); "
          f"ball correct {row['ball_correct']:.1%} of {ball_seen} visible, false-ball rate {row['false_ball_rate']:.1%}, "
          f"ball shown in {row['ball_shown']:.0%} of labelled frames, right when shown {row['ball_right_when_shown']:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
