"""Follow the ball in broadcast video, in image pixels.

A detector run on the whole 1920 px frame shrinks it to the model's input size,
and the ~10 px ball almost vanishes: on Mohit's labelled clip it was found in
32% of frames. Searching a 704 px window around where the ball should be, at
full resolution, found it in 63% (DECISIONS.md, D29). So:

1. A constant-velocity Kalman filter predicts where the ball is in the next frame.
2. The detector searches a window around that prediction (and the whole frame,
   in tiles, when the ball has been lost for a while).
3. Candidates on a player's head or shirt are rejected, and so are painted marks: on the
   first run the tracker locked onto the penalty and centre spots, small white dots that the
   detector scores like a ball (0.4-0.56), and the search window then followed them.
4. Offline, the ball is linked forwards and backwards through all candidates,
   the two passes are combined, and short gaps are filled by interpolation.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

WINDOW_PX = 704  # search window around the predicted ball (the detector's input size: no shrinking)
START_CONFIDENCE = 0.35  # the ball (re)starts only from a detection this confident
GATE_PX = 40.0  # a candidate must be this close to the prediction ...
GATE_GROWTH_PX = 25.0  # ... plus this much per frame the ball has been missing
MAX_LOST_FRAMES = 12  # after ~0.5 s without the ball, search afresh
MAX_GAP_FRAMES = 12  # gaps up to this long are filled by interpolation
AGREE_PX = 15.0  # forward and backward passes must agree this closely
HEAD_SHARE = 0.6  # a candidate in the top 60% of a person's box is a head or shirt, not the ball
PAINTED_SPOTS_M = np.array([[0.0, 0.0], [-41.5, 0.0], [41.5, 0.0]])  # centre and penalty spots
SPOT_RADIUS_M = 1.5
STATIC_CELL_M = 1.5  # a pitch cell that gives candidates in many frames holds a mark, not the ball
STATIC_MIN_FRAMES = 50  # 2 s at 25 fps (a ball standing still that long, e.g. before a penalty, is lost too)


def painted_spot(xy_m: np.ndarray) -> np.ndarray:
    """True for pitch positions on the centre or a penalty spot."""
    xy_m = np.asarray(xy_m, float).reshape(-1, 2)
    distance = np.linalg.norm(xy_m[:, None] - PAINTED_SPOTS_M[None], axis=2)
    return distance.min(axis=1) <= SPOT_RADIUS_M


def static_cells(frame: np.ndarray, xy_m: np.ndarray, min_frames: int = STATIC_MIN_FRAMES) -> np.ndarray:
    """True for candidates in a pitch cell (or its neighbours) that has candidates in >= min_frames frames."""
    cells = np.floor(np.asarray(xy_m, float) / STATIC_CELL_M).astype(int)
    frames_in = {}
    for (cx, cy), f in zip(map(tuple, cells), frame):
        frames_in.setdefault((cx, cy), set()).add(int(f))
    counts = {}
    for (cx, cy) in frames_in:
        near = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near |= frames_in.get((cx + dx, cy + dy), set())
        counts[(cx, cy)] = len(near)
    return np.array([counts[tuple(c)] >= min_frames for c in cells], dtype=bool)


@dataclass
class KalmanBall:
    """Constant-velocity Kalman filter for the ball's image position (state x, y, vx, vy; one step per frame)."""
    position: np.ndarray
    process_noise: float = 30.0  # px^2: the ball changes speed suddenly when kicked
    measurement_noise: float = 9.0  # px^2
    state: np.ndarray = field(init=False)
    covariance: np.ndarray = field(init=False)

    def __post_init__(self):
        self.state = np.array([*self.position, 0.0, 0.0])
        self.covariance = np.diag([25.0, 25.0, 400.0, 400.0])

    F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)

    def predict(self) -> np.ndarray:
        self.state = self.F @ self.state
        self.covariance = self.F @ self.covariance @ self.F.T + self.process_noise * np.eye(4)
        return self.state[:2]

    def update(self, measurement: np.ndarray) -> None:
        innovation = measurement - self.H @ self.state
        s = self.H @ self.covariance @ self.H.T + self.measurement_noise * np.eye(2)
        gain = self.covariance @ self.H.T @ np.linalg.inv(s)
        self.state = self.state + gain @ innovation
        self.covariance = (np.eye(4) - gain @ self.H) @ self.covariance


def search_window(centre: np.ndarray, frame_shape: tuple[int, int], size: int = WINDOW_PX) -> tuple[int, int]:
    """Top-left corner of a size x size window around `centre`, kept inside the frame."""
    height, width = frame_shape[:2]
    x0 = int(np.clip(round(centre[0] - size / 2), 0, max(width - size, 0)))
    y0 = int(np.clip(round(centre[1] - size / 2), 0, max(height - size, 0)))
    return x0, y0


def reject_heads(candidates: np.ndarray, person_boxes: np.ndarray) -> np.ndarray:
    """Drop candidates (rows x, y, confidence) inside the top HEAD_SHARE of any person box (x1, y1, x2, y2)."""
    if len(candidates) == 0 or len(person_boxes) == 0:
        return candidates
    x, y = candidates[:, 0:1], candidates[:, 1:2]
    x1, y1, x2, y2 = (person_boxes[:, i][None] for i in range(4))
    upper = (x >= x1) & (x <= x2) & (y >= y1) & (y <= y1 + HEAD_SHARE * (y2 - y1))
    return candidates[~upper.any(axis=1)]


def _one_pass(candidates: dict[int, np.ndarray], frames: list[int]) -> dict[int, np.ndarray]:
    """Frames -> accepted ball position, following the ball through the candidates in the given frame order."""
    found, kalman, missing = {}, None, 0
    for frame in frames:
        here = candidates.get(frame, np.empty((0, 3)))
        if kalman is not None:
            predicted = kalman.predict()
            if len(here):
                distance = np.linalg.norm(here[:, :2] - predicted, axis=1)
                best = int(distance.argmin())
                if distance[best] <= GATE_PX + GATE_GROWTH_PX * missing:
                    kalman.update(here[best, :2])
                    found[frame], missing = here[best, :2], 0
                    continue
            missing += 1
            if missing > MAX_LOST_FRAMES:
                kalman = None
            continue
        confident = here[here[:, 2] >= START_CONFIDENCE] if len(here) else here
        if len(confident):
            start = confident[int(confident[:, 2].argmax()), :2]
            kalman, missing = KalmanBall(start), 0
            found[frame] = start
    return found


def link_ball(candidates: pd.DataFrame, frames: int) -> pd.DataFrame:
    """One ball position per frame where we are confident: frame, px, py, detected, visible.

    `candidates`: frame, px, py, confidence (heads already rejected). Forward and backward passes
    are combined (where both give a position they must agree within AGREE_PX), then gaps of up to
    MAX_GAP_FRAMES between found positions are filled by straight-line interpolation (not detected).
    """
    by_frame = {f: g[["px", "py", "confidence"]].to_numpy(float) for f, g in candidates.groupby("frame")}
    forward = _one_pass(by_frame, list(range(frames)))
    backward = _one_pass(by_frame, list(range(frames - 1, -1, -1)))
    points = {}
    for frame in sorted(set(forward) | set(backward)):
        a, b = forward.get(frame), backward.get(frame)
        if a is not None and b is not None:
            if np.linalg.norm(a - b) <= AGREE_PX:
                points[frame] = (a + b) / 2
        else:
            points[frame] = a if a is not None else b

    rows = [(f, *xy, True) for f, xy in points.items()]
    known = sorted(points)
    for before, after in zip(known, known[1:]):
        if 1 < after - before <= MAX_GAP_FRAMES + 1:
            for f in range(before + 1, after):
                w = (f - before) / (after - before)
                rows.append((f, *((1 - w) * points[before] + w * points[after]), False))
    table = pd.DataFrame(rows, columns=["frame", "px", "py", "detected"]).sort_values("frame")
    table = pd.DataFrame({"frame": range(frames)}).merge(table, on="frame", how="left")
    table["visible"] = table["px"].notna()
    table["detected"] = table["detected"].fillna(False).astype(bool)
    return table.reset_index(drop=True)
