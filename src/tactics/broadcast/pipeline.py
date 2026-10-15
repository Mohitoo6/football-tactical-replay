"""Broadcast (moving camera) clip -> a clip the overlays and the AI coach can use, with a quality report.

    clip, report, camera = process_broadcast("highlight.mp4", clip_id="local-my-clip", title="Our attack")

Steps (DECISIONS.md, D28):
1. Frames at an exact 5 fps (keyframes), padded to 1920x1080.
2. Each keyframe calibrated by PnLCalib and checked by our line agreement.
3. RF-DETR people and ball on the good keyframes, feet placed on the pitch.
4. Tracking, teams and ball follower in pitch metres: the same code as the drone pipeline,
   because positions in metres do not depend on where the camera points.
5. Interpolated to 25 fps; one homography per output frame for the on-video overlay.

Only players the camera shows are in the clip (meta "view": "partial").
"""

import json
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.broadcast.calibrate import MIN_AGREEMENT, camera_track, line_agreement, run_pnlcalib
from tactics.broadcast.detect import BroadcastDetector
from tactics.broadcast.frames import KEY_FPS, MIN_GREEN_SHARE, VIDEO_FPS, extract_keyframes, green_share
from tactics.data.clips import Clip
from tactics.video.ball import follow_ball_both_ways
from tactics.video.export import tracks_to_clip
from tactics.video.pipeline import QualityReport
from tactics.broadcast.teams import split_by_colour
from tactics.video.track import PointTracker, fix_goalkeepers, officials, stitch_tracks, track_points

ROOT = Path(__file__).resolve().parents[3]
MIN_SECONDS = 10.0
MIN_CALIBRATED = 0.7  # share of pitch keyframes with a good calibration
MIN_PLAYERS_IN_VIEW = 8
MIN_BALL_VISIBLE = 0.3
BALL_START_CONFIDENCE = 0.3  # the ball follower may (re)start only from a detection this confident

Progress = Callable[[float, str], None]


def upsample(clip: Clip, factor: int) -> Clip:
    """Interpolate a clip to `factor` times its frame rate.

    Positions are interpolated only between consecutive keyframes in which the player (or the ball)
    was seen, so a player who leaves the view is not dragged across the pitch.
    """
    fps = clip.meta["frame_rate"] * factor
    start_s = clip.meta["start_s"]
    rows = []
    for _, group in clip.players.groupby("player_id"):
        group = group.sort_values("frame")
        keys = group["frame"].to_numpy()
        for i, key in enumerate(keys):
            steps = factor if i + 1 < len(keys) and keys[i + 1] == key + 1 else 1
            for s in range(steps):
                w = s / factor
                row = group.iloc[i].copy()
                if s:
                    nxt = group.iloc[i + 1]
                    row["x"], row["y"] = (1 - w) * row["x"] + w * nxt["x"], (1 - w) * row["y"] + w * nxt["y"]
                row["frame"] = key * factor + s
                rows.append(row)
    players = pd.DataFrame(rows, columns=clip.players.columns)
    players["frame"] = players["frame"].astype(int)
    players["time_s"] = start_s + players["frame"] / fps

    ball = clip.ball.sort_values("frame").reset_index(drop=True)
    frames = np.arange(int(ball["frame"].max()) * factor + 1)
    alive_keys = ball.loc[ball["alive"], "frame"].to_numpy()
    x = np.interp(frames / factor, ball["frame"], ball["x"])
    y = np.interp(frames / factor, ball["frame"], ball["y"])
    before = np.floor(frames / factor).astype(int)
    exact = frames % factor == 0
    alive = np.isin(before, alive_keys) & (exact | np.isin(before + 1, alive_keys))
    new_ball = pd.DataFrame({"frame": frames, "period": 1, "time_s": start_s + frames / fps, "x": x, "y": y,
                             "z": 0.0, "alive": alive, "owning_team": None})[clip.ball.columns]
    meta = {**clip.meta, "frame_rate": fps}
    return Clip(meta, players.sort_values(["frame", "team", "jersey"]).reset_index(drop=True), new_ball)


def process_broadcast(path: Path, clip_id: str, title: str, progress: Progress | None = None,
                      start_s: float = 0.0, work_dir: Path | None = None) -> tuple[Clip | None, QualityReport, pd.DataFrame | None]:
    """Broadcast video -> (clip at 25 fps, quality report, camera: one homography per clip frame)."""
    progress = progress or (lambda fraction, message: None)
    report = QualityReport()
    work = Path(work_dir or ROOT / "data" / "processed" / "broadcast" / clip_id)

    # Frames and calibration are cached per video file: re-running (e.g. after a code change further down)
    # skips the slowest step and keeps the laptop cool.
    source = {"video": str(Path(path).resolve()), "bytes": Path(path).stat().st_size,
              "modified": Path(path).stat().st_mtime}
    cached = work / "source.json"
    reuse = cached.exists() and json.loads(cached.read_text()) == source and (work / "calibration.json").exists()
    progress(0.01, "reading frames")
    if reuse:
        keyframes = sorted((work / "frames").glob("*.jpg"))
    else:
        (work / "calibration.json").unlink(missing_ok=True)
        keyframes = extract_keyframes(Path(path), work / "frames")
    seconds = len(keyframes) / KEY_FPS
    report.add("clip length", seconds >= MIN_SECONDS, f"{seconds:.1f} s", f">= {MIN_SECONDS:.0f} s")
    if report.status == "rejected":
        return None, report, None
    images = [cv2.imread(str(p)) for p in keyframes]
    pitch_view = [green_share(img) >= MIN_GREEN_SHARE for img in images]

    def calibrated(done: int, total: int) -> None:
        progress(0.03 + 0.6 * done / total, f"calibrating the camera: frame {done} of {total}")

    if reuse:
        raw = json.loads((work / "calibration.json").read_text())
        found = {name: None if h is None else np.array(h, dtype=float) for name, h in raw.items()}
    else:
        found = run_pnlcalib(work / "frames", work / "calibration.json", progress=calibrated)
        cached.write_text(json.dumps(source))
    homographies = [found.get(p.stem) if view else None for p, view in zip(keyframes, pitch_view)]
    agreements = [line_agreement(img, h) if h is not None else 0.0 for img, h in zip(images, homographies)]
    good = [h is not None and a >= MIN_AGREEMENT for h, a in zip(homographies, agreements)]
    share = sum(good) / max(sum(pitch_view), 1)
    median = float(np.median([a for a, g in zip(agreements, good) if g])) if any(good) else 0.0
    report.add("camera calibrated", share >= MIN_CALIBRATED,
               f"{share:.0%} of pitch frames, median line agreement {median:.2f}", f">= {MIN_CALIBRATED:.0%}")
    usable = sum(good) / KEY_FPS
    report.add("usable length", usable >= MIN_SECONDS, f"{usable:.1f} s with a good calibration", f">= {MIN_SECONDS:.0f} s")
    if report.status == "rejected":
        return None, report, None

    detector = BroadcastDetector()
    players, balls = [], []
    for k, (img, h, ok) in enumerate(zip(images, homographies, good)):
        if ok:
            p, b = detector.detect(img, h, k)
            players.append(p)
            balls.append(b)
        if k % 10 == 0:
            progress(0.65 + 0.25 * k / len(images), f"finding players: frame {k} of {len(images)}")
    # Frames without detections give empty tables, which would turn the columns into objects.
    players = pd.concat(players, ignore_index=True).astype(float).astype({"frame": int})
    balls = pd.concat(balls, ignore_index=True).astype(float).astype({"frame": int})
    in_view = players.groupby("frame").size().median() if len(players) else 0
    report.add("players in view", in_view >= MIN_PLAYERS_IN_VIEW, f"median {in_view:.0f} per frame", f">= {MIN_PLAYERS_IN_VIEW}")
    if report.status == "rejected":
        return None, report, None

    progress(0.92, "tracking players and the ball")
    fps = KEY_FPS
    tracker = PointTracker(max_distance_m=3.0, max_missing_frames=round(fps), colour_weight=2.0)
    tracks = stitch_tracks(track_points(players, tracker), max_gap_frames=round(2 * fps), fps=fps)
    tracks, teams = split_by_colour(tracks, min_frames=round(2 * fps))  # cut tracks where the shirt colour changes
    teams = fix_goalkeepers(tracks, teams)
    tracks = tracks[~tracks["track_id"].isin(officials(tracks))]
    candidates = balls.assign(reliable=balls["confidence"] >= BALL_START_CONFIDENCE)[["frame", "x_m", "y_m", "reliable"]]
    ball = follow_ball_both_ways(candidates, fps, max_lost_frames=round(1.5 * fps)) if len(candidates) \
        else pd.DataFrame(columns=["frame", "x_m", "y_m"])

    clip = tracks_to_clip(tracks, teams, ball, fps, clip_id, title, start_s=start_s, min_track_frames=round(fps))
    clip = upsample(clip, round(VIDEO_FPS / KEY_FPS))
    clip.meta.update({
        "data_kind": "broadcast",
        "view": "partial",
        "coordinates": "metres, origin at pitch centre; from broadcast video, camera calibrated in every frame",
        "source": "Broadcast footage supplied by the user (not redistributed).",
        "credit": "Video: user-supplied broadcast footage · camera calibration: PnLCalib · positions computed by this project",
    })
    camera = camera_track(homographies, [a if g else 0.0 for a, g in zip(agreements, good)], KEY_FPS, VIDEO_FPS,
                          len(clip.ball))
    visible = float(clip.ball["alive"].mean())
    report.add("ball visible", visible >= MIN_BALL_VISIBLE, f"{visible:.0%} of frames", f">= {MIN_BALL_VISIBLE:.0%}",
               blocking=False)
    progress(1.0, "done")
    return clip, report, camera
