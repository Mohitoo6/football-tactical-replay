"""Phase 7: turn one SoccerTrack top-view segment into player tracks, and measure them.

    uv run --group video python scripts/video_to_tracks.py 0030_0060

Steps: stabilise every frame to frame 0, detect player blobs against the empty
pitch, calibrate automatically from the pitch lines, then track. Detections are
cached in data/processed/. Tracks are scored against the SoccerTrack boxes
(identity switches, coverage), comparing our tracker with supervision's ByteTrack.
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.video.calibration import PitchCalibration
from tactics.video.detect import BackgroundDetector, Stabilizer, pitch_mask, read_frames
from tactics.video.evaluate import identity_metrics
from tactics.video.pitch_lines import auto_calibrate
from tactics.video.soccertrack import load_boxes
from tactics.video.ball import follow_ball_both_ways, is_white
from tactics.video.track import PointTracker, assign_teams, fix_goalkeepers, stitch_tracks, track_points

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "soccertrack"
PROCESSED = ROOT / "data" / "processed"
FPS = 29.97
MATCH_RADIUS_M = 1.5


def detect_all(video: Path, dataset_calibration: PitchCalibration, truth: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every frame: blobs (reference px, auto metres, dataset metres, colour) and ground truth in dataset metres.

    Detection uses only the video (automatic calibration). `dataset_calibration` is used only to express
    detections and ground truth in the dataset's metres for scoring.
    """
    stabilizer = Stabilizer(read_frames(video, [0])[0])
    sample = read_frames(video, list(range(0, 900, 15)))
    shape = sample[0].shape[:2]
    detector = BackgroundDetector([Stabilizer.align(f, stabilizer.warp(f)) for f in sample.values()],
                                  np.full(shape, 255, dtype=np.uint8))
    # Everything the clip uses comes from the video: the pitch area for detection is taken from our
    # automatic calibration, not from the dataset's hand-marked keypoints (those are only for scoring).
    auto = auto_calibrate(detector.background, image_scale=detector.scale)
    detector.mask = detector._resize(pitch_mask(shape, auto))
    stabilizer.last_matrix = np.eye(2, 3, dtype=np.float32)

    capture, rows, real_rows, ball_rows, index = cv2.VideoCapture(str(video)), [], [], [], 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        warp = stabilizer.warp(frame)
        aligned = Stabilizer.align(frame, warp)
        blobs = detector.detect_blobs(aligned)
        small = detector.detect_blobs(aligned, min_area=1, max_area=detector.min_area - 1)
        if len(small):
            xy = small[["x", "y"]].to_numpy()
            small[["x_m", "y_m"]] = auto.to_pitch(xy)
            small[["x", "y"]] = dataset_calibration.to_pitch(xy)
            ball_rows.append(small.assign(frame=index))
        if len(blobs):
            px = blobs[["x", "y"]].to_numpy()
            blobs[["x_m", "y_m"]] = auto.to_pitch(px)
            blobs[["x", "y"]] = dataset_calibration.to_pitch(px)  # for scoring against the dataset's ground truth
            rows.append(blobs.assign(frame=index))
        real = truth[truth["frame"] == index + 1]
        xy = dataset_calibration.to_pitch(Stabilizer.to_reference(real[["cx", "cy"]].to_numpy(), warp))
        real_rows.append(pd.DataFrame({"frame": index, "truth_id": (real["team"] + "-" + real["player_id"]).to_numpy(),
                                       "x": xy[:, 0], "y": xy[:, 1]}))
        index += 1
    capture.release()
    print(f"  {index} frames, stabiliser fallbacks: {stabilizer.failures}")
    pd.concat(ball_rows, ignore_index=True).to_parquet(PROCESSED / f"{video.stem}_small_blobs.parquet")
    return pd.concat(rows, ignore_index=True), pd.concat(real_rows, ignore_index=True)


def bytetrack(detections: pd.DataFrame) -> pd.DataFrame:
    """Baseline: supervision's (deprecated) ByteTrack on small boxes around each blob."""
    import supervision as sv

    tracker, out = sv.ByteTrack(frame_rate=FPS), []
    for frame, group in detections.groupby("frame", sort=True):
        half = np.sqrt(group["area_px"].to_numpy()) / 2 + 4
        boxes = np.column_stack([group["px"] - half, group["py"] - half, group["px"] + half, group["py"] + half])
        result = tracker.update_with_detections(sv.Detections(xyxy=boxes, confidence=np.ones(len(group))))
        if len(result):
            centre = result.get_anchors_coordinates(sv.Position.CENTER)
            out.append(pd.DataFrame({"frame": frame, "track_id": result.tracker_id, "cx": centre[:, 0], "cy": centre[:, 1]}))
    tracks = pd.concat(out, ignore_index=True)
    return tracks


def main(segment: str) -> None:
    name = f"D_20220220_1_{segment}"
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cache, cache_truth = PROCESSED / f"{name}_detections.parquet", PROCESSED / f"{name}_truth.parquet"
    calibration = PitchCalibration.from_file(DATA / "drone_keypoints.json")
    if cache.exists():
        detections, truth = pd.read_parquet(cache), pd.read_parquet(cache_truth)
    else:
        start = time.perf_counter()
        boxes = load_boxes(DATA / "top_view" / "annotations" / f"{name}.csv")
        detections, truth = detect_all(DATA / "top_view" / "videos" / f"{name}.mp4", calibration, boxes)
        detections.to_parquet(cache)
        truth.to_parquet(cache_truth)
        print(f"  detection on all frames: {time.perf_counter() - start:.0f} s")

    ball_truth = truth[truth["truth_id"] == "BALL-BALL"]
    truth = truth[truth["truth_id"] != "BALL-BALL"]

    ours = track_points(detections)
    report("our tracker", ours[["frame", "track_id", "x", "y"]], truth)
    tuned = stitch_tracks(track_points(detections, PointTracker(max_distance_m=1.5, max_missing_frames=30, colour_weight=2.0)))
    report("+ colour + stitching", tuned[["frame", "track_id", "x", "y"]], truth)
    team_accuracy(tuned.assign(team=tuned["track_id"].map(fix_goalkeepers(tuned, assign_teams(tuned)))), truth)
    ball_report(pd.read_parquet(PROCESSED / f"{name}_small_blobs.parquet"), ball_truth)

    pixels = detections.assign(px=calibration.from_pitch(detections[["x", "y"]].to_numpy())[:, 0],
                               py=calibration.from_pitch(detections[["x", "y"]].to_numpy())[:, 1])
    baseline = bytetrack(pixels)
    xy = calibration.to_pitch(baseline[["cx", "cy"]].to_numpy())
    report("ByteTrack", baseline.assign(x=xy[:, 0], y=xy[:, 1])[["frame", "track_id", "x", "y"]], truth)


def team_accuracy(tracks: pd.DataFrame, truth: pd.DataFrame) -> None:
    """Share of matched player-frames whose team label agrees with the truth (best of the two label mappings)."""
    from scipy.optimize import linear_sum_assignment

    pairs = []
    for frame, real in truth.groupby("frame"):
        found = tracks[tracks["frame"] == frame]
        d = np.linalg.norm(found[["x", "y"]].to_numpy()[:, None] - real[["x", "y"]].to_numpy()[None], axis=2)
        rows, cols = linear_sum_assignment(d)
        pairs += [(found["team"].iloc[r], real["truth_id"].iloc[c][0]) for r, c in zip(rows, cols) if d[r, c] <= MATCH_RADIUS_M]
    p = pd.DataFrame(pairs, columns=["ours", "truth"])
    straight = ((p.ours == "A") & (p.truth == "0")).sum() + ((p.ours == "B") & (p.truth == "1")).sum()
    swapped = ((p.ours == "A") & (p.truth == "1")).sum() + ((p.ours == "B") & (p.truth == "0")).sum()
    print(f"  team label correct on {max(straight, swapped) / len(p):.1%} of matched player-frames")


def ball_report(small_blobs: pd.DataFrame, ball_truth: pd.DataFrame) -> None:
    """Ball: candidates per frame, and how often our followed ball is within 1 m of the real one."""
    white = small_blobs[is_white(small_blobs)]
    ball = follow_ball_both_ways(white.assign(x_m=white["x"], y_m=white["y"]), FPS)  # scored in dataset metres
    merged = ball_truth.merge(ball, on="frame", how="left")
    error = np.hypot(merged["x"] - merged["x_m"], merged["y"] - merged["y_m"])
    found = error.notna()
    print(f"  ball: {white.groupby('frame').size().median():.0f} white candidates per frame; position given in "
          f"{found.mean():.1%} of frames; correct (within 1 m) in {(error <= 1.0).sum() / found.sum():.1%} of those; "
          f"ball found correctly in {(error <= 1.0).mean():.1%} of all frames")


def report(label: str, tracks: pd.DataFrame, truth: pd.DataFrame) -> None:
    m = identity_metrics(tracks, truth, MATCH_RADIUS_M, FPS)
    print(f"  {label:12} coverage {m['coverage']:.1%}  id switches {m['id_switches']} "
          f"({m['switches_per_player_minute']:.2f} per player-minute)  purity {m['mean_purity']:.1%}  "
          f"tracks created {m['tracks_created']} (22 real players)")


if __name__ == "__main__":
    for seg in sys.argv[1:] or ["0030_0060"]:
        print(seg)
        main(seg)
