"""Broadcast (moving camera) clip -> a clip the overlays and the AI coach can use, with a quality report.

    result = process_broadcast("highlight.mp4", clip_id="local-my-clip", title="Our attack")

Steps (DECISIONS.md, D28-D29):
1. Keyframes at an exact 5 fps, padded to 1920x1080; each calibrated by PnLCalib and checked by our
   line agreement; one homography per 25 fps frame by interpolation.
2. One pass over the video at 25 fps: people every 2nd frame (12.5 fps) with RF-DETR Base; the ball in
   every frame, searched at full resolution around where a Kalman filter expects it.
3. Tracking, teams and the clip in pitch metres with the drone pipeline's code (positions in metres do
   not depend on where the camera points); players missed for up to 0.5 s are bridged.
4. The ball is linked forwards and backwards in pixels, gaps filled, then placed on the pitch.

Only players the camera shows are in the clip (meta "view": "partial").
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.broadcast.ball import (KalmanBall, MAX_LOST_FRAMES, STATIC_CELL_M, STATIC_MIN_FRAMES, link_ball, painted_spot,
                                   reject_heads, search_window, static_cells)
from tactics.broadcast.calibrate import MIN_AGREEMENT, camera_track, homography_at, line_agreement, run_pnlcalib, to_pitch
from tactics.broadcast.frames import KEY_FPS, MIN_GREEN_SHARE, VIDEO_FPS, extract_keyframes, green_share, iter_frames
from tactics.broadcast.teams import split_by_colour
from tactics.data.clips import Clip
from tactics.video.export import tracks_to_clip
from tactics.video.pipeline import QualityReport
from tactics.video.track import PointTracker, fix_goalkeepers, officials, stitch_tracks, track_points

ROOT = Path(__file__).resolve().parents[3]
MIN_SECONDS = 10.0
MIN_CALIBRATED = 0.7  # share of pitch keyframes with a good calibration
MIN_PLAYERS_IN_VIEW = 8
MIN_BALL_VISIBLE = 0.3
PEOPLE_EVERY = 2  # look for people in every 2nd frame (12.5 fps)
BRIDGE_S = 0.5  # a player missed for up to this long keeps a (interpolated) position
GLOBAL_SEARCH_EVERY = 5  # while the ball is lost, search the whole frame (in tiles) every 5th frame
DETECTION_VERSION = 2  # bump when detection changes, so cached detections are recomputed

Progress = Callable[[float, str], None]


@dataclass
class BroadcastResult:
    clip: Clip | None
    report: QualityReport
    camera: pd.DataFrame | None = None  # frame, valid, h0..h8: pitch metres -> pixels per clip frame
    people: pd.DataFrame | None = None  # every tracked person for the overlay: frame, x_m, y_m, side, px, py
    ball: pd.DataFrame | None = None  # ball in pixels: frame, px, py, detected, visible


def upsample(clip: Clip, factor: int, bridge: int = 0) -> Clip:
    """Interpolate a clip to `factor` times its frame rate.

    A player's position is interpolated between two frames in which they were seen when at most
    `bridge` frames are missing in between (a short occlusion); longer absences are left empty,
    so a player who leaves the view is not dragged across the pitch.
    """
    fps = clip.meta["frame_rate"] * factor
    start_s = clip.meta["start_s"]
    players = _interpolate_rows(clip.players, "player_id", factor, bridge)
    players["time_s"] = start_s + players["frame"] / fps

    ball = clip.ball.sort_values("frame").reset_index(drop=True)
    frames = np.arange(int(ball["frame"].max()) * factor + 1)
    alive_keys = ball.loc[ball["alive"], "frame"].to_numpy()
    x = np.interp(frames / factor, ball["frame"].astype(float), ball["x"].astype(float))
    y = np.interp(frames / factor, ball["frame"].astype(float), ball["y"].astype(float))
    before = np.floor(frames / factor).astype(int)
    exact = frames % factor == 0
    alive = np.isin(before, alive_keys) & (exact | np.isin(before + 1, alive_keys))
    new_ball = pd.DataFrame({"frame": frames, "period": 1, "time_s": start_s + frames / fps, "x": x, "y": y,
                             "z": 0.0, "alive": alive, "owning_team": None})[clip.ball.columns]
    meta = {**clip.meta, "frame_rate": fps}
    return Clip(meta, players.sort_values(["frame", "team", "jersey"]).reset_index(drop=True), new_ball)


def _interpolate_rows(table: pd.DataFrame, key: str, factor: int, bridge: int, x: str = "x", y: str = "y") -> pd.DataFrame:
    """Rows of `table` (one per `key` per frame) at `factor` times the frame rate, bridging gaps <= `bridge` frames."""
    rows = []
    for _, group in table.groupby(key, sort=False):
        group = group.sort_values("frame")
        keys = group["frame"].to_numpy()
        values = group[[x, y]].to_numpy(float)
        for i, frame in enumerate(keys):
            gap = keys[i + 1] - frame if i + 1 < len(keys) else 0
            steps = factor * gap if 0 < gap <= bridge + 1 else 1
            for s in range(steps):
                w = s / steps if steps > 1 else 0.0
                row = group.iloc[i].to_dict()
                if s:
                    row[x], row[y] = (1 - w) * values[i] + w * values[i + 1]
                row["frame"] = int(frame * factor + s)
                rows.append(row)
    out = pd.DataFrame(rows, columns=table.columns)
    out["frame"] = out["frame"].astype(int)
    return out


def process_broadcast(path: Path, clip_id: str, title: str, progress: Progress | None = None,
                      start_s: float = 0.0, work_dir: Path | None = None) -> BroadcastResult:
    """Broadcast video -> clip at 25 fps, quality report, camera per frame, people and ball for the overlay."""
    from tactics.broadcast.detect import BallDetector, PeopleDetector  # heavy imports (PyTorch)

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
        return BroadcastResult(None, report)
    images = [cv2.imread(str(p)) for p in keyframes]
    pitch_view = [green_share(img) >= MIN_GREEN_SHARE for img in images]

    def calibrated(done: int, total: int) -> None:
        progress(0.03 + 0.4 * done / total, f"calibrating the camera: frame {done} of {total}")

    if reuse:
        raw = json.loads((work / "calibration.json").read_text())
        found = {name: None if h is None else np.array(h, dtype=float) for name, h in raw.items()}
    else:
        found = run_pnlcalib(work / "frames", work / "calibration.json", progress=calibrated)
        cached.write_text(json.dumps(source))
    homographies = [found.get(p.stem) if view else None for p, view in zip(keyframes, pitch_view)]
    agreements = [line_agreement(img, h) if h is not None else 0.0 for img, h in zip(images, homographies)]
    good = [h is not None and a >= MIN_AGREEMENT for h, a in zip(homographies, agreements)]
    del images
    share = sum(good) / max(sum(pitch_view), 1)
    median = float(np.median([a for a, g in zip(agreements, good) if g])) if any(good) else 0.0
    report.add("camera calibrated", share >= MIN_CALIBRATED,
               f"{share:.0%} of pitch frames, median line agreement {median:.2f}", f">= {MIN_CALIBRATED:.0%}")
    usable = sum(good) / KEY_FPS
    report.add("usable length", usable >= MIN_SECONDS, f"{usable:.1f} s with a good calibration", f">= {MIN_SECONDS:.0f} s")
    if report.status == "rejected":
        return BroadcastResult(None, report)

    frames = int(round(len(keyframes) * VIDEO_FPS / KEY_FPS))
    camera = camera_track(homographies, [a if g else 0.0 for a, g in zip(agreements, good)], KEY_FPS, VIDEO_FPS, frames)
    # Detections are cached too (the slowest step after calibration), keyed to the video and this code version.
    stamp = {**source, "detection_version": DETECTION_VERSION, "frames": frames}
    people_file, ball_file, stamp_file = work / "people.parquet", work / "ball_candidates.parquet", work / "detections.json"
    if stamp_file.exists() and json.loads(stamp_file.read_text()) == stamp and people_file.exists() and ball_file.exists():
        people, candidates = pd.read_parquet(people_file), pd.read_parquet(ball_file)
    else:
        people, candidates = _detect(path, camera, frames, PeopleDetector(), BallDetector(), progress)
        people.to_parquet(people_file, index=False)
        candidates.to_parquet(ball_file, index=False)
        stamp_file.write_text(json.dumps(stamp))
    in_view = people.groupby("frame").size().median() if len(people) else 0
    report.add("players in view", in_view >= MIN_PLAYERS_IN_VIEW, f"median {in_view:.0f} per frame", f">= {MIN_PLAYERS_IN_VIEW}")
    if report.status == "rejected":
        return BroadcastResult(None, report, camera)

    progress(0.93, "tracking players and the ball")
    clip, overlay_people = _players_to_clip(people, clip_id, title, start_s)
    marks = static_cells(candidates["frame"].to_numpy(), candidates[["x_m", "y_m"]].to_numpy()) if len(candidates) else []
    ball = link_ball(candidates[~np.asarray(marks, dtype=bool)] if len(candidates) else candidates, frames)
    clip = Clip(clip.meta, clip.players[clip.players["frame"] < frames], _ball_on_pitch(ball, camera, clip.meta, start_s))
    clip.meta.update({
        "data_kind": "broadcast",
        "view": "partial",
        "coordinates": "metres, origin at pitch centre; from broadcast video, camera calibrated in every frame",
        "source": "Broadcast footage supplied by the user (not redistributed).",
        "credit": "Video: user-supplied broadcast footage · camera calibration: PnLCalib · positions computed by this project",
    })
    overlay_people = _with_pixels(overlay_people[overlay_people["frame"] < frames], camera)
    visible = float(ball["visible"].mean())
    report.add("ball visible", visible >= MIN_BALL_VISIBLE, f"{visible:.0%} of frames", f">= {MIN_BALL_VISIBLE:.0%}",
               blocking=False)
    progress(1.0, "done")
    return BroadcastResult(clip, report, camera, overlay_people, ball)


def _detect(path: Path, camera: pd.DataFrame, frames: int, people_detector, ball_detector,
            progress: Progress) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One pass over the video: people every PEOPLE_EVERY frames, ball candidates in every frame."""
    people, candidates = [], []
    kalman, missing, boxes = None, MAX_LOST_FRAMES + 1, np.empty((0, 4))
    seen_cells: dict[tuple[int, int], set[int]] = {}  # pitch cell -> frames with a candidate there (painted marks)
    for j, frame in enumerate(iter_frames(Path(path))):
        if j >= frames:
            break
        h = homography_at(camera, j)
        if h is None:  # no trusted camera (cut, replay, close-up): nothing to place on the pitch
            kalman, missing = None, MAX_LOST_FRAMES + 1
            continue
        found = np.empty((0, 3))
        if j % PEOPLE_EVERY == 0:
            table, boxes, found = people_detector.detect(frame, h, j)
            people.append(table)
        predicted = kalman.predict() if kalman is not None else None
        if predicted is not None:
            found = np.vstack([found, ball_detector.in_window(frame, *search_window(predicted, frame.shape))])
        elif j % GLOBAL_SEARCH_EVERY == 0:
            found = np.vstack([found, ball_detector.everywhere(frame)])
        found = reject_heads(found, boxes)
        if len(found):  # drop painted marks: the centre and penalty spots, and any spot that never moves
            xy_m = to_pitch(found[:, :2], h)
            cells = [tuple(c) for c in np.floor(xy_m / STATIC_CELL_M).astype(int)]
            for cell in cells:
                seen_cells.setdefault(cell, set()).add(j)
            still = np.array([len(seen_cells[c]) >= STATIC_MIN_FRAMES for c in cells])
            keep = ~painted_spot(xy_m) & ~still
            found, xy_m = found[keep], xy_m[keep]
            candidates += [(j, x, y, c, mx, my) for (x, y, c), (mx, my) in zip(found, xy_m)]
        # Online, only to steer the search window; the final ball comes from link_ball (both directions).
        if len(found) and (kalman is not None or found[:, 2].max() >= 0.35):
            reference = predicted if predicted is not None else found[int(found[:, 2].argmax()), :2]
            best = found[int(np.linalg.norm(found[:, :2] - reference, axis=1).argmin()), :2]
            if kalman is None:
                kalman = KalmanBall(best)
            else:
                kalman.update(best)
            missing = 0
        else:
            missing += 1
            if missing > MAX_LOST_FRAMES:
                kalman = None
        if j % 25 == 0:
            progress(0.45 + 0.47 * j / frames, f"finding players and the ball: frame {j} of {frames}")
    people = pd.concat(people, ignore_index=True) if people else pd.DataFrame()
    # Frames without detections give empty tables, which would turn the columns into objects.
    people = people.astype(float).astype({"frame": int}) if len(people) else people
    return people, pd.DataFrame(candidates, columns=["frame", "px", "py", "confidence", "x_m", "y_m"])


def _players_to_clip(people: pd.DataFrame, clip_id: str, title: str, start_s: float) -> tuple[Clip, pd.DataFrame]:
    """Track people at 12.5 fps in metres; return the 25 fps clip and every tracked person for the overlay."""
    fps = VIDEO_FPS / PEOPLE_EVERY
    detections = people.assign(frame=people["frame"] // PEOPLE_EVERY)
    tracker = PointTracker(max_distance_m=2.0, max_missing_frames=round(fps), colour_weight=2.0)
    tracks = stitch_tracks(track_points(detections, tracker), max_gap_frames=round(2 * fps), fps=fps)
    tracks, teams = split_by_colour(tracks, min_frames=round(fps))  # cut tracks where the shirt colour changes
    teams = fix_goalkeepers(tracks, teams)
    analysed = tracks[~tracks["track_id"].isin(officials(tracks))]
    empty_ball = pd.DataFrame(columns=["frame", "x_m", "y_m"])
    clip = tracks_to_clip(analysed, teams, empty_ball, fps, clip_id, title, start_s=start_s, min_track_frames=round(fps))
    bridge = round(BRIDGE_S * fps)
    clip = upsample(clip, PEOPLE_EVERY, bridge=bridge)

    # Overlay: every tracked person (also referees, short and unsure pieces), in the video's own coordinates.
    side = {"A": None, "B": None}
    for letter in side:
        rows = clip.players[clip.players["player_id"].str.startswith(letter)]
        side[letter] = rows["team"].iloc[0] if len(rows) else ("home" if letter == "A" else "away")
    everyone = tracks.assign(side=tracks["track_id"].map(teams).map(lambda t: side.get(t, "other")))
    everyone = _interpolate_rows(everyone[["frame", "track_id", "x_m", "y_m", "side"]], "track_id", PEOPLE_EVERY,
                                 bridge, x="x_m", y="y_m")
    return clip, everyone


def _with_pixels(table: pd.DataFrame, camera: pd.DataFrame) -> pd.DataFrame:
    """Add px, py: where each pitch position appears in its frame (for the overlay and the evaluation)."""
    from tactics.broadcast.calibrate import project
    parts = []
    for frame, group in table.groupby("frame"):
        h = homography_at(camera, int(frame))
        if h is None:
            continue
        xy = project(group[["x_m", "y_m"]].to_numpy(float), h)
        parts.append(group.assign(px=xy[:, 0], py=xy[:, 1]))
    return pd.concat(parts, ignore_index=True) if parts else table.assign(px=[], py=[])


def _ball_on_pitch(ball: pd.DataFrame, camera: pd.DataFrame, meta: dict, start_s: float) -> pd.DataFrame:
    """The clip's ball table at 25 fps: the tracked ball placed on the pitch (in the clip's orientation)."""
    x = np.full(len(ball), np.nan)
    y = np.full(len(ball), np.nan)
    for i, row in ball[ball["visible"]].iterrows():
        h = homography_at(camera, int(row["frame"]))
        if h is not None:
            x[i], y[i] = to_pitch(np.array([[row["px"], row["py"]]]), h)[0]
    sign = -1 if meta.get("rotated") else 1
    alive = np.isfinite(x)
    table = pd.DataFrame({"frame": ball["frame"], "period": 1, "time_s": start_s + ball["frame"] / VIDEO_FPS,
                          "x": sign * x, "y": sign * y, "z": 0.0, "alive": alive, "owning_team": None})
    table[["x", "y"]] = table[["x", "y"]].ffill().bfill().fillna(0.0)
    return table
