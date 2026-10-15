"""Where the camera looks, frame by frame: a homography from pitch metres to image pixels.

1. PnLCalib (an external, GPL tool; see tools/pnlcalib/README.md) calibrates each keyframe.
2. We check every result ourselves: draw the calibrated pitch lines and measure the share
   that lands on white paint (`line_agreement`). Good calibrations score ~0.7-0.9, wrong ones
   below 0.1 (DECISIONS.md, D28). Keyframes below MIN_AGREEMENT are dropped.
3. Between keyframes the homography is interpolated, except across a camera cut.
"""

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.video.calibration import PITCH_LENGTH_M, PITCH_WIDTH_M
from tactics.video.pitch_lines import line_pixels

ROOT = Path(__file__).resolve().parents[3]
PNLCALIB = Path(os.environ.get("TACTICS_PNLCALIB", ROOT / "data" / "tools" / "pnlcalib"))
RUNNER = ROOT / "tools" / "pnlcalib" / "run_pnlcalib.py"
MIN_AGREEMENT = 0.5
LINE_TOLERANCE_PX = 4
CUT_JUMP_M = 15.0  # the view's centre moving this far between keyframes (0.2 s) is a camera cut, not a pan
MAX_GAP_KEYFRAMES = 2  # bridge at most this many dropped keyframes by interpolation

H_COLUMNS = [f"h{i}" for i in range(9)]


def pnlcalib_installed(path: Path = PNLCALIB) -> bool:
    return (path / ".venv" / "bin" / "python").exists() and (path / "weights" / "SV_kp").exists()


def run_pnlcalib(frames_dir: Path, out_json: Path, path: Path = PNLCALIB,
                 progress: Callable[[int, int], None] | None = None) -> dict[str, np.ndarray | None]:
    """Calibrate every .jpg in `frames_dir` with the external tool; {frame name: 3x3 homography or None}."""
    if not pnlcalib_installed(path):
        raise RuntimeError("PnLCalib is not installed: run  sh tools/pnlcalib/setup.sh")
    command = [str(path / ".venv" / "bin" / "python"), str(RUNNER), "--pnlcalib", str(path),
               "--frames", str(frames_dir), "--out", str(out_json)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        for line in process.stdout:
            if line.startswith("calibrated") and progress:
                done, total = line.split()[1].split("/")
                progress(int(done), int(total))
    if process.returncode:
        raise RuntimeError(f"PnLCalib failed (exit code {process.returncode})")
    raw = json.loads(out_json.read_text())
    return {name: None if h is None else np.array(h, dtype=float) for name, h in raw.items()}


def pitch_line_points(step_m: float = 0.25) -> list[np.ndarray]:
    """The painted lines as dense point lists in pitch metres (centre origin, x along the length)."""
    half_l, half_w = PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2
    segments = [((-half_l, -half_w), (half_l, -half_w)), ((-half_l, half_w), (half_l, half_w)),
                ((-half_l, -half_w), (-half_l, half_w)), ((half_l, -half_w), (half_l, half_w)),
                ((0, -half_w), (0, half_w))]
    for side in (-1, 1):  # penalty and goal areas
        goal_x = side * half_l
        for depth, half_width in ((16.5, 20.16), (5.5, 9.16)):
            box_x = goal_x - side * depth
            segments += [((goal_x, -half_width), (box_x, -half_width)), ((box_x, -half_width), (box_x, half_width)),
                         ((box_x, half_width), (goal_x, half_width))]
    lines = [np.linspace(a, b, int(np.hypot(b[0] - a[0], b[1] - a[1]) / step_m) + 2) for a, b in segments]
    angle = np.linspace(0, 2 * np.pi, 400)
    circle = np.column_stack([9.15 * np.cos(angle), 9.15 * np.sin(angle)])
    lines.append(circle)
    for side in (-1, 1):  # penalty arcs: the part of the circle around the spot outside the box
        arc = circle + [side * (half_l - 11), 0]
        lines.append(arc[side * arc[:, 0] < half_l - 16.5])
    return lines


def project(points_m: np.ndarray, homography: np.ndarray) -> np.ndarray:
    """Pitch metres -> image pixels."""
    return cv2.perspectiveTransform(np.asarray(points_m, np.float64).reshape(-1, 1, 2), homography).reshape(-1, 2)


def to_pitch(points_px: np.ndarray, homography: np.ndarray) -> np.ndarray:
    """Image pixels -> pitch metres (for points on the ground, e.g. a player's feet)."""
    return project(points_px, np.linalg.inv(homography))


def line_agreement(frame: np.ndarray, homography: np.ndarray, tolerance_px: float = LINE_TOLERANCE_PX) -> float:
    """Share of the calibrated pitch lines (where they fall inside the frame) within `tolerance_px` of white paint."""
    distance = cv2.distanceTransform(255 - line_pixels(frame), cv2.DIST_L2, 3)
    height, width = frame.shape[:2]
    hits = total = 0
    for points in pitch_line_points():
        image = project(points, homography)
        inside = np.isfinite(image).all(axis=1) & (image[:, 0] >= 0) & (image[:, 0] < width) & \
            (image[:, 1] >= 0) & (image[:, 1] < height)
        xy = image[inside].astype(int)
        total += len(xy)
        hits += int((distance[xy[:, 1], xy[:, 0]] <= tolerance_px).sum())
    return hits / total if total else 0.0


def view_centre_m(homography: np.ndarray, width: int = 1920, height: int = 1080) -> np.ndarray:
    """The pitch point at the centre of the image."""
    return to_pitch(np.array([[width / 2, height / 2]]), homography)[0]


def camera_track(homographies: list[np.ndarray | None], agreements: list[float], key_fps: float, video_fps: float,
                 frames: int) -> pd.DataFrame:
    """One homography per output frame (frame, valid, h0..h8), interpolated between good keyframes.

    A keyframe is good if calibrated with line agreement >= MIN_AGREEMENT. Output frame j is at time
    j / video_fps; it is interpolated between the good keyframes around it unless they are more than
    MAX_GAP_KEYFRAMES apart or a camera cut lies between them (then it is not valid).
    """
    good = [k for k, (h, a) in enumerate(zip(homographies, agreements)) if h is not None and a >= MIN_AGREEMENT]
    normalised = {k: homographies[k] / homographies[k][2, 2] for k in good}
    rows = []
    for j in range(frames):
        t = j / video_fps * key_fps  # position in keyframe units
        before = max((k for k in good if k <= t), default=None)
        after = min((k for k in good if k >= t), default=None)
        h, valid = np.full((3, 3), np.nan), False
        if before is not None and after is not None:
            if before == after:
                h, valid = normalised[before], True
            elif after - before <= MAX_GAP_KEYFRAMES + 1:
                jump = np.linalg.norm(view_centre_m(normalised[after]) - view_centre_m(normalised[before]))
                if jump <= CUT_JUMP_M * (after - before):
                    w = (t - before) / (after - before)
                    h, valid = (1 - w) * normalised[before] + w * normalised[after], True
        rows.append([j, valid, *h.ravel()])
    return pd.DataFrame(rows, columns=["frame", "valid", *H_COLUMNS])


def homography_at(camera: pd.DataFrame, frame: int) -> np.ndarray | None:
    row = camera[camera["frame"] == frame]
    if row.empty or not bool(row["valid"].iloc[0]):
        return None
    return row[H_COLUMNS].to_numpy(dtype=float).reshape(3, 3)
