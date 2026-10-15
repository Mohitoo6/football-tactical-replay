"""Evaluate the drone-video pipeline on SoccerTrack segments (the exact code path that builds clips).

    uv run --group video python scripts/video_to_tracks.py 0600_0630
    uv run --group video python scripts/video_to_tracks.py all        # every downloaded segment

Runs `tactics.video.pipeline` (detection with automatic calibration, tracking,
teams, ball) and only then compares with the SoccerTrack ground truth via
`tactics.video.scoring`. Writes one row per segment to evals/video/segments.csv
and prints the quality report the pipeline produced.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from tactics.video.calibration import PITCH_LENGTH_M, PITCH_WIDTH_M, PitchCalibration
from tactics.video.pipeline import QualityReport, detect_video, track_everything
from tactics.video.scoring import (
    ball_scores, detection_scores, in_dataset_metres, team_correct, tracking_scores, truth_in_dataset_metres,
)
from tactics.video.soccertrack import load_boxes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "soccertrack"
RESULTS = ROOT / "evals" / "video" / "segments.csv"
PREFIX = "D_20220220_1_"  # SoccerTrack's file names; only this evaluation script knows them


def evaluate(segment: str, video: Path | None = None, pixel_map: np.ndarray | None = None,
             frame_map: np.ndarray | None = None) -> dict:
    """Run the pipeline on a segment (or on an edited copy of it, `video`) and score it against the truth.

    For an edited copy (rotated, cropped, resized, re-timed), `pixel_map` is the 2x3 affine map from the
    original pixels to the copy's pixels and `frame_map[k]` is the original frame shown as the copy's frame k.
    Both are applied to the ground truth only, never to what the pipeline sees.
    """
    name = f"{PREFIX}{segment}"
    dataset = PitchCalibration.from_file(DATA / "drone_keypoints.json")  # scoring only
    boxes = load_boxes(DATA / "top_view" / "annotations" / f"{name}.csv")
    if pixel_map is not None:
        moved = lambda xy: np.asarray(xy, dtype=float) @ pixel_map[:, :2].T + pixel_map[:, 2]
        dataset = PitchCalibration(dataset.pitch_m + [PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2], moved(dataset.other))
        boxes[["cx", "cy"]] = moved(boxes[["cx", "cy"]].to_numpy())
    if frame_map is not None:  # annotation frames start at 1
        frames = pd.DataFrame({"frame": np.asarray(frame_map) + 1, "copy_frame": np.arange(len(frame_map)) + 1})
        boxes = boxes.merge(frames, on="frame").drop(columns="frame").rename(columns={"copy_frame": "frame"})

    start = time.perf_counter()
    report = QualityReport()
    detections = detect_video(video or DATA / "top_view" / "videos" / f"{name}.mp4", report)
    print(report.summary())
    failed = "; ".join(c.name for c in report.checks if not c.passed)
    if detections is None:
        return {"segment": segment, "quality": report.status, "failed_checks": failed,
                "seconds": round(time.perf_counter() - start)}

    tracks, teams, ball = track_everything(detections)
    truth = truth_in_dataset_metres(boxes, detections.warps, dataset)
    ball_truth = truth[truth["truth_id"] == "BALL-BALL"]
    truth = truth[truth["truth_id"] != "BALL-BALL"]

    tracks = in_dataset_metres(tracks, dataset).assign(team=lambda t: t["track_id"].map(teams))
    ball_px = detections.calibration.from_pitch(ball[["x_m", "y_m"]].to_numpy()) if len(ball) else ball[[]]
    ball_xy = dataset.to_pitch(ball_px) if len(ball) else None
    ball_dataset = ball.assign(x=ball_xy[:, 0], y=ball_xy[:, 1]) if len(ball) else ball.assign(x=[], y=[])

    row = {"segment": segment, "quality": report.status, "failed_checks": failed,
           **detection_scores(detections.players, truth),
           **tracking_scores(tracks, truth, detections.fps),
           "team_correct": team_correct(tracks, truth),
           **ball_scores(ball_dataset[["frame", "x", "y"]], ball_truth),
           "seconds": round(time.perf_counter() - start)}
    print(f"{segment}: players found {row['recall']:.1%}, error {row['error_m']:.2f} m, purity {row['purity']:.1%}, "
          f"team {row['team_correct']:.1%}, ball {row['ball_correct']:.1%}  ({row['seconds']} s)", flush=True)
    return row


def save_row(row: dict) -> None:
    """Add or replace this segment's results in evals/video/segments.csv."""
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    table = pd.read_csv(RESULTS, dtype={"segment": str}) if RESULTS.exists() else pd.DataFrame()
    if len(table):
        table = table[table["segment"] != row["segment"]]
    table = pd.concat([table, pd.DataFrame([row])], ignore_index=True).sort_values("segment")
    table.round(4).to_csv(RESULTS, index=False)


if __name__ == "__main__":
    args = sys.argv[1:] or ["0600_0630"]
    if args == ["all"]:
        args = sorted(p.stem.removeprefix(PREFIX) for p in (DATA / "top_view" / "videos").glob("*.mp4"))
    for seg in args:
        save_row(evaluate(seg))
