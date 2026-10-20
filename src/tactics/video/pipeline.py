"""Any top-view drone clip -> a clip the overlays and the AI coach can use, with a quality report.

    clip, report = process_video("my_clip.mp4", clip_id="my-clip", title="Goal from the drone")

Everything comes from the video itself: frame rate and length are read from the
file, the pitch is calibrated from its painted lines, and no dataset files are
used. The quality report says when a clip is not suitable (camera moving too
much, pitch outline not found, implausible player counts) so the system can
refuse instead of producing wrong positions.

Assumptions (checked by the report where possible): a top-down camera that
hovers in place, the whole pitch outline visible, a pitch of known size
(105 x 68 m by default) and a clip of roughly 10-60 seconds.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pandas as pd

from tactics.data.clips import Clip
from tactics.data.report import Check, QualityReport  # noqa: F401  (re-exported for older imports)
from tactics.video.ball import follow_ball_both_ways, is_white
from tactics.video.calibration import PITCH_LENGTH_M, PITCH_WIDTH_M, PitchCalibration
from tactics.video.detect import BackgroundDetector, Stabilizer, pitch_mask, read_frames
from tactics.video.export import tracks_to_clip
from tactics.video.pitch_lines import auto_calibrate, outline_ratio_error, outline_support, pitch_corners, view_rotation
from tactics.video.track import PointTracker, assign_teams, fix_goalkeepers, officials, stitch_tracks, track_points

BACKGROUND_SAMPLES = 60
MIN_SECONDS = 10.0
MAX_DRIFT_PX = 200  # camera shift relative to the first frame (4K: ~7 m on the pitch)
MAX_RATIO_ERROR = 0.05
MAX_CALIBRATION_DISAGREEMENT_M = 2.0
PLAYERS_ON_PITCH = (14, 30)  # median player-sized blobs per frame we accept (22 players, some merged, some extra)
MIN_BALL_VISIBLE = 0.3
# Blob sizes in BackgroundDetector were tuned on 4K SoccerTrack at half resolution: ~14 px per metre.
# Each clip is processed at the scale that gives it about the same, so 1080p or a higher drone also works.
WORKING_PX_PER_M = 14.0
MIN_PX_PER_M = 10.0  # 720p of a full pitch (9.3 px/m) found only 76% of players, so refuse below this (D27)

Progress = Callable[[float, str], None]


@dataclass
class Detections:
    """Everything detected in a video, before tracking (also used by the evaluation scripts)."""
    players: pd.DataFrame  # frame, px, py (reference pixels), x_m, y_m (pitch metres), area_px, b, g, r
    small: pd.DataFrame  # same columns, blobs smaller than a player (ball candidates)
    warps: np.ndarray  # (frames, 2, 3): reference -> frame pixel mapping per frame
    calibration: PitchCalibration
    fps: float
    frames: int


def video_info(path: Path) -> tuple[float, int, tuple[int, int]]:
    """(frames per second, frame count, (height, width)) read from the file."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    size = (int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    capture.release()
    return fps, count, size


def detect_video(path: Path, report: QualityReport, length_m: float = PITCH_LENGTH_M, width_m: float = PITCH_WIDTH_M,
                 progress: Progress | None = None) -> Detections | None:
    """Stabilise, build the empty pitch, calibrate, then detect player blobs and ball candidates in every frame.

    Returns None when a blocking check already fails (no point detecting on a clip we will reject).
    """
    progress = progress or (lambda fraction, message: None)
    fps, count, (height, width) = video_info(path)
    seconds = count / fps if fps else 0.0
    report.add("clip length", seconds >= MIN_SECONDS, f"{seconds:.1f} s at {fps:.2f} fps", f">= {MIN_SECONDS:.0f} s")
    if report.status == "rejected":
        return None

    progress(0.02, "building the empty-pitch image")
    sample_indices = np.linspace(0, count - 1, min(BACKGROUND_SAMPLES, count)).astype(int).tolist()
    sample = read_frames(path, sample_indices)
    first = sample[sample_indices[0]]
    stabilizer = Stabilizer(first)
    aligned = [Stabilizer.align(f, stabilizer.warp(f)) for f in sample.values()]
    no_mask = np.full((height, width), 255, dtype=np.uint8)
    detector = BackgroundDetector(aligned, no_mask, scale=min(1.0, 1920 / max(height, width)))  # first guess

    progress(0.08, "calibrating from the pitch lines")
    try:
        corners = pitch_corners(detector.background, aspect=length_m / width_m) / detector.scale
        calibration = auto_calibrate(detector.background, length_m, width_m, image_scale=detector.scale)
    except ValueError as error:
        report.add("pitch outline found", False, str(error), "the whole pitch outline visible")
        return None
    ratio_error = outline_ratio_error(corners, length_m, width_m)
    report.add("pitch outline shape", ratio_error <= MAX_RATIO_ERROR, f"{ratio_error:.1%} off {length_m:g}:{width_m:g}",
               f"<= {MAX_RATIO_ERROR:.0%}")
    sides = np.linalg.norm(corners - np.roll(corners, -1, axis=0), axis=1)
    px_per_m = float(sides.sum() / (2 * (length_m + width_m)))  # full-resolution pixels per metre
    scale = min(1.0, WORKING_PX_PER_M / px_per_m)
    if abs(scale - detector.scale) > 0.02:
        detector = BackgroundDetector(aligned, no_mask, scale=scale)
    report.add("pitch resolution", px_per_m >= MIN_PX_PER_M, f"{px_per_m:.1f} px per metre", f">= {MIN_PX_PER_M:.0f}")
    report.add("calibration stable over the clip", *_calibration_agreement(aligned, detector, calibration, corners))
    detector.mask = detector._resize(pitch_mask((height, width), calibration))
    del aligned, sample
    if report.status == "rejected":
        return None

    stabilizer.last_matrix = np.eye(2, 3, dtype=np.float32)
    capture = cv2.VideoCapture(str(path))
    players, small, warps, index = [], [], [], 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        warp = stabilizer.warp(frame)
        warps.append(warp)
        big, little = detector.split_blobs(Stabilizer.align(frame, warp))
        for table, rows in ((big, players), (little, small)):
            if len(table):
                xy = calibration.to_pitch(table[["x", "y"]].to_numpy())
                rows.append(table.rename(columns={"x": "px", "y": "py"}).assign(frame=index, x_m=xy[:, 0], y_m=xy[:, 1]))
        index += 1
        if index % 30 == 0:
            progress(0.1 + 0.8 * index / max(count, 1), f"detecting players: frame {index} of {count}")
    capture.release()

    warps = np.array(warps)
    drift = float(np.abs(warps[:, :, 2]).max()) if len(warps) else 0.0
    report.add("camera holds still", drift <= MAX_DRIFT_PX and stabilizer.failures <= 0.05 * index,
               f"max drift {drift:.0f} px, {stabilizer.failures} frames could not be aligned",
               f"<= {MAX_DRIFT_PX} px and <= 5% unaligned frames")
    players = pd.concat(players, ignore_index=True) if players else pd.DataFrame()
    small = pd.concat(small, ignore_index=True) if small else pd.DataFrame()
    per_frame = players.groupby("frame").size().reindex(range(index), fill_value=0).median() if len(players) else 0
    low, high = PLAYERS_ON_PITCH
    report.add("player count plausible", low <= per_frame <= high, f"median {per_frame:.0f} player blobs per frame",
               f"{low}-{high}")
    return Detections(players, small, warps, calibration, fps, index)


MIN_SIDE_SUPPORT = 0.4  # a side of the outline counts as found when at least 40% of it lies on painted line


def _calibration_agreement(aligned: list[np.ndarray], detector: BackgroundDetector, calibration: PitchCalibration,
                           corners: np.ndarray) -> tuple[bool, str, str]:
    """Does the outline found for the whole clip still hold, in the same place, in each half of the sample frames?

    Each half gets its own empty-pitch image; every side of the outline is searched a little either way, and how far
    it moved is measured in metres. (Searching each half for its own best outline mistook the halfway line for a goal
    line when players hid part of the real one, D35.)
    """
    half = len(aligned) // 2
    need = f"each side found (>= {MIN_SIDE_SUPPORT:.0%} on line) and moved <= {MAX_CALIBRATION_DISAGREEMENT_M} m"
    worst_m, weakest = 0.0, 1.0
    for part in (aligned[:half], aligned[half:]):
        if len(part) < 5:
            return True, "too few frames to compare", need
        background = np.median(np.stack([detector._resize(f) for f in part]), axis=0).astype(np.uint8)
        scaled = corners * detector.scale
        for k, (support, offset) in enumerate(outline_support(background, scaled)):
            weakest = min(weakest, support)
            a, b = scaled[k], scaled[(k + 1) % 4]
            direction = (b - a) / max(np.linalg.norm(b - a), 1e-6)
            normal = np.array([-direction[1], direction[0]])
            middle = (a + b) / 2
            moved = calibration.to_pitch(np.array([middle, middle + offset * normal]) / detector.scale)
            worst_m = max(worst_m, float(np.linalg.norm(moved[1] - moved[0])))
    if weakest < MIN_SIDE_SUPPORT:
        return False, f"a side of the outline is lost in one half ({weakest:.0%} on line)", need
    return worst_m <= MAX_CALIBRATION_DISAGREEMENT_M, f"outline moved up to {worst_m:.2f} m between halves", need


def track_everything(detections: Detections) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Tracks (officials removed), team per track, and the followed ball, from frame-by-frame detections."""
    fps = detections.fps
    # Time limits are set in seconds and converted with this clip's frame rate (25, 30 or 60 fps all behave alike).
    tracks = stitch_tracks(track_points(detections.players, PointTracker(max_distance_m=1.5, max_missing_frames=round(fps),
                                                                         colour_weight=2.0)),
                           max_gap_frames=round(2 * fps), fps=fps)
    teams = fix_goalkeepers(tracks, assign_teams(tracks))  # teams first: officials help form the "other" group
    tracks = tracks[~tracks["track_id"].isin(officials(tracks))]
    small = detections.small
    ball = follow_ball_both_ways(small[is_white(small)], fps, max_lost_frames=round(1.5 * fps)) if len(small) \
        else pd.DataFrame(columns=["frame", "x_m", "y_m"])
    return tracks, teams, ball


def process_video(path: Path, clip_id: str, title: str, length_m: float = PITCH_LENGTH_M,
                  width_m: float = PITCH_WIDTH_M, progress: Progress | None = None,
                  start_s: float = 0.0) -> tuple[Clip | None, QualityReport]:
    """Drone video -> (clip in the standard format, quality report). The clip is None when the report rejects it.

    `start_s` sets the match clock of the first frame (e.g. 600 for a clip starting at 10:00).
    """
    progress = progress or (lambda fraction, message: None)
    report = QualityReport()
    detections = detect_video(Path(path), report, length_m, width_m, progress)
    if detections is None or report.status == "rejected":
        return None, report

    progress(0.92, "tracking players and the ball")
    tracks, teams, ball = track_everything(detections)
    fps = detections.fps

    clip = tracks_to_clip(tracks, teams, ball, fps, clip_id, title, start_s=start_s, min_track_frames=round(fps),
                          view_rotation=view_rotation(detections.calibration))
    visible = float(clip.ball["alive"].mean())
    report.add("ball visible", visible >= MIN_BALL_VISIBLE, f"{visible:.0%} of frames", f">= {MIN_BALL_VISIBLE:.0%}",
               blocking=False)
    keepers = int((clip.players["position"] == "Goalkeeper").groupby(clip.players["team"]).any().sum())
    report.add("one goalkeeper per team found", keepers == 2, f"{keepers} of 2", "2", blocking=False)
    progress(1.0, "done")
    return clip, report
