"""Evaluate the drone-video pipeline on SoccerTrack segments (the exact code path that builds clips).

    uv run --group video python scripts/video_to_tracks.py 0600_0630
    uv run --group video python scripts/video_to_tracks.py all              # every downloaded segment
    uv run --group video python scripts/video_to_tracks.py all --rescore    # score saved runs again (no video work)
    uv run --group video python scripts/video_to_tracks.py all --dataset-truth   # the dataset's one calibration

Runs `tactics.video.pipeline` (detection with automatic calibration, tracking,
teams, ball) and only then compares with the SoccerTrack ground truth via
`tactics.video.scoring`. Writes one row per segment to evals/video/segments.csv
and prints the quality report the pipeline produced.

Ground truth in metres: the dataset's boxes are pixels, turned into metres with a calibration.
SoccerTrack has one calibration for the whole match, but the drone drifts (D30), so by default each
segment uses its own corrected calibration from scripts/truth_calibration.py. With --dataset-truth
the original single calibration is used (results in segments_dataset_truth.csv).
Each run is saved in data/processed/soccertrack/runs/<segment>/ so it can be re-scored cheaply.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from tactics.video.calibration import PITCH_LENGTH_M, PITCH_WIDTH_M, PitchCalibration
from tactics.video.pipeline import Detections, QualityReport, detect_video, track_everything
from tactics.video.scoring import (
    ball_scores, detection_scores, in_dataset_metres, team_correct, tracking_scores, truth_in_dataset_metres,
)
from tactics.video.soccertrack import load_boxes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "soccertrack"
RESULTS = ROOT / "evals" / "video" / "segments.csv"
PREFIX = "D_20220220_1_"  # SoccerTrack's file names; only this evaluation script knows them
PROCESSED = ROOT / "data" / "processed" / "soccertrack"


def truth_calibration(segment: str, dataset_truth: bool = False) -> PitchCalibration:
    """The calibration that turns this segment's ground-truth pixels into metres (scoring only)."""
    corrected = PROCESSED / "truth_calibration" / f"{segment}.json"
    if dataset_truth or not corrected.exists():
        return PitchCalibration.from_file(DATA / "drone_keypoints.json")
    return PitchCalibration.from_file(corrected)


def save_run(segment: str, report: QualityReport, detections: Detections, tracks, teams, ball) -> None:
    folder = PROCESSED / "runs" / segment
    folder.mkdir(parents=True, exist_ok=True)
    detections.players.to_parquet(folder / "players.parquet", index=False)
    np.save(folder / "warps.npy", detections.warps)
    tracks.to_parquet(folder / "tracks.parquet", index=False)
    ball.to_parquet(folder / "ball.parquet", index=False)
    calibration = detections.calibration
    (folder / "run.json").write_text(json.dumps({
        "fps": detections.fps, "frames": detections.frames, "status": report.status,
        "failed": [c.name for c in report.checks if not c.passed], "summary": report.summary(),
        "teams": {str(k): v for k, v in teams.items()},
        "calibration": {"pitch_m": (calibration.pitch_m + [PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2]).tolist(),
                        "image": calibration.other.tolist()}}))


def load_run(segment: str):
    folder = PROCESSED / "runs" / segment
    run = json.loads((folder / "run.json").read_text())
    calibration = PitchCalibration(np.array(run["calibration"]["pitch_m"]), np.array(run["calibration"]["image"]))
    detections = Detections(pd.read_parquet(folder / "players.parquet"), pd.DataFrame(), np.load(folder / "warps.npy"),
                            calibration, run["fps"], run["frames"])
    teams = pd.Series({int(k): v for k, v in run["teams"].items()})
    return run, detections, pd.read_parquet(folder / "tracks.parquet"), teams, pd.read_parquet(folder / "ball.parquet")


def evaluate(segment: str, video: Path | None = None, pixel_map: np.ndarray | None = None,
             frame_map: np.ndarray | None = None, rescore: bool = False, dataset_truth: bool = False) -> dict:
    """Run the pipeline on a segment (or on an edited copy of it, `video`) and score it against the truth.

    For an edited copy (rotated, cropped, resized, re-timed), `pixel_map` is the 2x3 affine map from the
    original pixels to the copy's pixels and `frame_map[k]` is the original frame shown as the copy's frame k.
    Both are applied to the ground truth only, never to what the pipeline sees.
    """
    name = f"{PREFIX}{segment}"
    dataset = truth_calibration(segment, dataset_truth)  # scoring only
    boxes = load_boxes(DATA / "top_view" / "annotations" / f"{name}.csv")
    if pixel_map is not None:
        moved = lambda xy: np.asarray(xy, dtype=float) @ pixel_map[:, :2].T + pixel_map[:, 2]
        dataset = PitchCalibration(dataset.pitch_m + [PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2], moved(dataset.other))
        boxes[["cx", "cy"]] = moved(boxes[["cx", "cy"]].to_numpy())
    if frame_map is not None:  # annotation frames start at 1
        frames = pd.DataFrame({"frame": np.asarray(frame_map) + 1, "copy_frame": np.arange(len(frame_map)) + 1})
        boxes = boxes.merge(frames, on="frame").drop(columns="frame").rename(columns={"copy_frame": "frame"})

    start = time.perf_counter()
    if rescore:
        run, detections, tracks, teams, ball = load_run(segment)
        status, failed = run["status"], "; ".join(run["failed"])
    else:
        report = QualityReport()
        detections = detect_video(video or DATA / "top_view" / "videos" / f"{name}.mp4", report)
        print(report.summary())
        status, failed = report.status, "; ".join(c.name for c in report.checks if not c.passed)
        if detections is None:
            return {"segment": segment, "quality": status, "failed_checks": failed,
                    "seconds": round(time.perf_counter() - start)}
        tracks, teams, ball = track_everything(detections)
        if video is None:  # only the original segment, not edited copies
            save_run(segment, report, detections, tracks, teams, ball)
    truth = truth_in_dataset_metres(boxes, detections.warps, dataset)
    ball_truth = truth[truth["truth_id"] == "BALL-BALL"]
    truth = truth[truth["truth_id"] != "BALL-BALL"]

    tracks = in_dataset_metres(tracks, dataset).assign(team=lambda t: t["track_id"].map(teams))
    ball_px = detections.calibration.from_pitch(ball[["x_m", "y_m"]].to_numpy()) if len(ball) else ball[[]]
    ball_xy = dataset.to_pitch(ball_px) if len(ball) else None
    ball_dataset = ball.assign(x=ball_xy[:, 0], y=ball_xy[:, 1]) if len(ball) else ball.assign(x=[], y=[])

    row = {"segment": segment, "quality": status, "failed_checks": failed,
           **detection_scores(detections.players, truth),
           **tracking_scores(tracks, truth, detections.fps),
           "team_correct": team_correct(tracks, truth),
           **ball_scores(ball_dataset[["frame", "x", "y"]], ball_truth),
           "seconds": round(time.perf_counter() - start)}
    print(f"{segment}: players found {row['recall']:.1%}, error {row['error_m']:.2f} m, purity {row['purity']:.1%}, "
          f"team {row['team_correct']:.1%}, ball {row['ball_correct']:.1%}  ({row['seconds']} s)", flush=True)
    return row


def save_row(row: dict, results: Path = RESULTS) -> None:
    """Add or replace this segment's results in the results table."""
    results.parent.mkdir(parents=True, exist_ok=True)
    table = pd.read_csv(results, dtype={"segment": str}) if results.exists() else pd.DataFrame()
    if len(table):
        table = table[table["segment"] != row["segment"]]
    table = pd.concat([table, pd.DataFrame([row])], ignore_index=True).sort_values("segment")
    table.round(4).to_csv(results, index=False)


if __name__ == "__main__":
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")] or ["0600_0630"]
    if args == ["all"]:
        args = sorted(p.stem.removeprefix(PREFIX) for p in (DATA / "top_view" / "videos").glob("*.mp4"))
    dataset_truth = "--dataset-truth" in flags
    results = RESULTS.with_name("segments_dataset_truth.csv") if dataset_truth else RESULTS
    for seg in args:
        save_row(evaluate(seg, rescore="--rescore" in flags, dataset_truth=dataset_truth), results)
