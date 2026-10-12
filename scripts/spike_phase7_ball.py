"""Phase 7 ball spike: does a full-resolution, no-closing detector find the ball more often?

    uv run --group video python scripts/video_to_tracks.py 0300_0330    # first: caches truth + old candidates
    uv run --group video python scripts/spike_phase7_ball.py 0030_0060 0300_0330 0600_0630

For each segment it compares the current ball candidates (half resolution, from
the player detector) with `BallDetector` (full resolution, round white blobs):
how often a candidate lies within 1 m of the real ball (the ceiling), how many
candidates per frame, and how often the followed ball is correct. Detection
uses only the video (automatic calibration); ground truth is used only to score.
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.video.ball import BallDetector, follow_ball_both_ways, is_white, mark_candidates, median_background
from tactics.video.calibration import PitchCalibration
from tactics.video.detect import Stabilizer, pitch_mask, read_frames
from tactics.video.pitch_lines import auto_calibrate

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "soccertrack"
PROCESSED = ROOT / "data" / "processed"
FPS = 29.97


def score(candidates: pd.DataFrame, ball_truth: pd.DataFrame) -> dict:
    """candidates: frame, x, y in dataset metres (for scoring only); optional reliable / penalty_m columns."""
    near = []
    for frame, (bx, by) in ball_truth.set_index("frame")[["x", "y"]].iterrows():
        c = candidates[candidates["frame"] == frame]
        near.append(bool(len(c)) and bool((np.hypot(c["x"] - bx, c["y"] - by) <= 1.0).any()))
    followed = follow_ball_both_ways(candidates.assign(x_m=candidates["x"], y_m=candidates["y"]), FPS)
    # (x_m / y_m here are the dataset metres, used only for scoring)
    merged = ball_truth.merge(followed, on="frame", how="left")
    correct = np.hypot(merged["x"] - merged["x_m"], merged["y"] - merged["y_m"]) <= 1.0
    return {"ceiling": float(np.mean(near)), "per_frame": candidates.groupby("frame").size().reindex(
        ball_truth["frame"], fill_value=0).mean(), "correct": float(correct.mean())}


def main(segment: str) -> None:
    name = f"D_20220220_1_{segment}"
    video = DATA / "top_view" / "videos" / f"{name}.mp4"
    dataset = PitchCalibration.from_file(DATA / "drone_keypoints.json")  # scoring only
    truth = pd.read_parquet(PROCESSED / f"{name}_truth.parquet")
    ball_truth = truth[truth["truth_id"] == "BALL-BALL"]

    start = time.perf_counter()
    stabilizer = Stabilizer(read_frames(video, [0])[0])
    sample = [Stabilizer.align(f, stabilizer.warp(f)) for f in read_frames(video, list(range(0, 900, 15))).values()]
    background = median_background(sample)
    del sample
    auto = auto_calibrate(cv2.resize(background, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), image_scale=0.5)
    detector = BallDetector(background, pitch_mask(background.shape[:2], auto))
    stabilizer.last_matrix = np.eye(2, 3, dtype=np.float32)

    capture, rows, index = cv2.VideoCapture(str(video)), [], 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        found = detector.candidates(Stabilizer.align(frame, stabilizer.warp(frame)))
        if len(found):
            xy = dataset.to_pitch(found[["x", "y"]].to_numpy())
            rows.append(found.assign(frame=index, x=xy[:, 0], y=xy[:, 1]))
        index += 1
    capture.release()
    new = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["frame", "x", "y"])
    new.to_parquet(PROCESSED / f"{name}_ball_candidates_fullres.parquet")
    players = pd.read_parquet(PROCESSED / f"{name}_detections.parquet")
    marked = mark_candidates(new, players, near_player_m=0.3, penalty_m=8.0, x="x", y="y")

    old = pd.read_parquet(PROCESSED / f"{name}_small_blobs.parquet")
    old = old[is_white(old)]
    for label, cands in (("old (half-res small blobs)", old[["frame", "x", "y"]]),
                         ("new (full-res round white)", new[["frame", "x", "y"]]),
                         ("new + near-player demotion", marked[["frame", "x", "y", "reliable", "penalty_m"]])):
        s = score(cands, ball_truth)
        print(f"{segment} {label:28} ceiling {s['ceiling']:.1%}  candidates/frame {s['per_frame']:.1f}  "
              f"ball correct {s['correct']:.1%}")
    print(f"  ({index} frames in {time.perf_counter() - start:.0f} s)")


if __name__ == "__main__":
    for seg in sys.argv[1:] or ["0300_0330"]:
        main(seg)
