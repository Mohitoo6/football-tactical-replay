"""Find the ball: small white blobs, linked over time by a speed limit.

The ball is ~12 px across in 4K top-view video: a small, bright, low-saturation
blob. Several such blobs may appear (noise, boots), so we follow the one that
moves plausibly. When the ball is hidden (at a player's feet, merged with the
player's blob), we report no position rather than guessing (DECISIONS.md, D11).
"""

import cv2
import numpy as np
import pandas as pd

MAX_BALL_SPEED_MPS = 35.0  # a hard shot; anything faster is a different blob


def is_white(blobs: pd.DataFrame, min_value: int = 150, max_saturation: int = 70) -> np.ndarray:
    """True for blobs whose mean colour is bright and nearly colourless (a white ball on grass)."""
    bgr = blobs[["b", "g", "r"]].to_numpy().round().clip(0, 255).astype(np.uint8).reshape(-1, 1, 3)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    return (hsv[:, 2] >= min_value) & (hsv[:, 1] <= max_saturation)


def drop_static(candidates: pd.DataFrame, radius_m: float = 0.3, max_share: float = 0.3) -> pd.DataFrame:
    """Remove white spots that stay in one place for much of the clip (cones, paint marks), which are not the ball."""
    cells = (candidates["x_m"] / radius_m).round().astype(int).astype(str) + ":" + \
            (candidates["y_m"] / radius_m).round().astype(int).astype(str)
    share = cells.map(candidates.groupby(cells)["frame"].nunique()) / candidates["frame"].nunique()
    return candidates[share <= max_share]


def follow_ball(candidates: pd.DataFrame, fps: float, max_lost_frames: int = 45) -> pd.DataFrame:
    """One ball position per frame where we are confident (columns frame, x_m, y_m).

    candidates: frame, x_m, y_m for every ball-like blob (static spots removed). Optional columns:
    - `reliable` (bool): only reliable candidates may start or restart the ball (e.g. away from players);
    - `penalty_m` (float): added to the distance when choosing between candidates, so a candidate
      near a player's body (often a shirt fragment) loses to a clean one but still wins if it is alone.
    We follow the candidate nearest the last known ball position, within the distance a ball could
    travel since it was last seen.
    """
    candidates = drop_static(candidates)
    if "reliable" not in candidates:
        candidates = candidates.assign(reliable=True)
    if "penalty_m" not in candidates:
        candidates = candidates.assign(penalty_m=0.0)
    by_frame = {f: g for f, g in candidates.groupby("frame")}
    rows, last, last_frame = [], None, None
    for frame in sorted(by_frame):
        group = by_frame[frame]
        points = group[["x_m", "y_m"]].to_numpy()
        if last is not None and frame - last_frame > max_lost_frames:
            last = None  # lost for too long: search afresh
        if last is None:
            reliable = points[group["reliable"].to_numpy()]
            if len(reliable) == 1:  # only (re)start when the choice is unambiguous
                last, last_frame = reliable[0], frame
                rows.append((frame, *last))
            continue
        reach = 1.0 + MAX_BALL_SPEED_MPS * (frame - last_frame) / fps
        distances = np.linalg.norm(points - last, axis=1)
        cost = np.where(distances <= reach, distances + group["penalty_m"].to_numpy(), np.inf)
        if np.isfinite(cost).any():
            last, last_frame = points[cost.argmin()], frame
            rows.append((frame, *last))
    return pd.DataFrame(rows, columns=["frame", "x_m", "y_m"])


def follow_ball_both_ways(candidates: pd.DataFrame, fps: float, max_lost_frames: int = 45) -> pd.DataFrame:
    """Follow the ball forwards and backwards in time and combine (offline, so the future is known).

    A forward pass misses the frames before each restart; a backward pass fills
    them. Where both passes give a position but disagree by more than 1 m, the
    frame is left empty rather than guessed.
    """
    forward = follow_ball(candidates, fps, max_lost_frames)
    backward = follow_ball(candidates.assign(frame=-candidates["frame"]), fps, max_lost_frames)
    backward["frame"] = -backward["frame"]
    both = forward.merge(backward, on="frame", how="outer", suffixes=("_f", "_b"))
    agree = np.hypot(both["x_m_f"] - both["x_m_b"], both["y_m_f"] - both["y_m_b"]) <= 1.0
    only_f, only_b = both["x_m_b"].isna(), both["x_m_f"].isna()
    keep = agree | only_f | only_b
    both = both[keep]
    x = both["x_m_f"].fillna(both["x_m_b"])
    y = both["y_m_f"].fillna(both["y_m_b"])
    return pd.DataFrame({"frame": both["frame"], "x_m": x, "y_m": y}).sort_values("frame").reset_index(drop=True)


def median_background(frames: list[np.ndarray], rows_per_chunk: int = 120) -> np.ndarray:
    """Per-pixel median of full-resolution frames, computed in horizontal strips.

    A plain np.median over 60 4K frames would build a ~12 GB float copy; strips keep it small.
    """
    stack_height = frames[0].shape[0]
    out = np.empty_like(frames[0])
    for top in range(0, stack_height, rows_per_chunk):
        strip = np.stack([f[top:top + rows_per_chunk] for f in frames])
        out[top:top + rows_per_chunk] = np.median(strip, axis=0).astype(np.uint8)
    return out


class BallDetector:
    """Ball candidates at full resolution: small, round, white blobs that differ from the empty pitch.

    The player detector works at half resolution and closes gaps so a player is one blob; that also
    glues a ball at someone's feet onto the player. Here we keep full resolution and do not close,
    so a ball a few pixels from a boot stays separate.
    """

    def __init__(self, background: np.ndarray, mask: np.ndarray, threshold: int = 35,
                 min_area_px: int = 25, max_area_px: int = 220, min_roundness: float = 0.55):
        self.background, self.mask = background, mask
        self.threshold, self.min_area, self.max_area, self.min_roundness = threshold, min_area_px, max_area_px, min_roundness
        hsv = cv2.cvtColor(background, cv2.COLOR_BGR2HSV)
        lines = cv2.inRange(hsv, (0, 0, 170), (180, 70, 255))
        self.lines = cv2.dilate(lines, np.ones((7, 7), np.uint8))  # painted lines (+ a margin), never the ball

    def candidates(self, frame: np.ndarray) -> pd.DataFrame:
        """Centres (x, y) in full-resolution pixels of ball-like blobs, with their mean colour."""
        diff = cv2.absdiff(frame, self.background).max(axis=2)
        _, moving = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, (0, 0, 160), (180, 80, 255))
        ball_like = cv2.bitwise_and(cv2.bitwise_and(moving, white), self.mask)
        ball_like = cv2.bitwise_and(ball_like, cv2.bitwise_not(self.lines))
        ball_like = cv2.morphologyEx(ball_like, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(ball_like, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rows = []
        for contour in contours:
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if not self.min_area <= area <= self.max_area or perimeter == 0:
                continue
            roundness = 4 * np.pi * area / perimeter**2  # 1.0 for a perfect circle
            if roundness < self.min_roundness:
                continue
            m = cv2.moments(contour)
            rows.append((m["m10"] / m["m00"], m["m01"] / m["m00"], area, roundness))
        return pd.DataFrame(rows, columns=["x", "y", "area_px", "roundness"])


def distance_to_players(candidates: pd.DataFrame, players: pd.DataFrame, x: str = "x_m", y: str = "y_m") -> np.ndarray:
    """For each candidate, the distance to the nearest player-blob centre in the same frame (inf if none)."""
    out = np.full(len(candidates), np.inf)
    by_frame = {f: g[[x, y]].to_numpy() for f, g in players.groupby("frame")}
    for i, (frame, cx, cy) in enumerate(candidates[["frame", x, y]].itertuples(index=False)):
        centres = by_frame.get(frame)
        if centres is not None and len(centres):
            out[i] = np.hypot(centres[:, 0] - cx, centres[:, 1] - cy).min()
    return out


def mark_candidates(candidates: pd.DataFrame, players: pd.DataFrame, near_player_m: float = 0.4,
                    min_roundness: float = 0.75, penalty_m: float = 1.0, x: str = "x_m", y: str = "y_m") -> pd.DataFrame:
    """Add `reliable` and `penalty_m` for `follow_ball`.

    Measured on 10:00-10:30: false candidates (mostly white-shirt fragments) sit a median 0.29 m
    from a player-blob centre with roundness 0.65; real ball candidates sit a median 2.2 m away
    (10th percentile 0.53 m) with roundness 0.88. Dropping near-player candidates outright lost the
    ball when it was at a player's feet, so they are only demoted.
    """
    near = distance_to_players(candidates, players, x, y) <= near_player_m
    round_enough = candidates["roundness"].to_numpy() >= min_roundness if "roundness" in candidates else True
    return candidates.assign(reliable=~near & round_enough, penalty_m=np.where(near, penalty_m, 0.0))
