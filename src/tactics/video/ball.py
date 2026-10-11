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

    candidates: frame, x_m, y_m for every small white blob (static spots removed).
    We follow the candidate nearest the last known ball position, within the
    distance a ball could travel since it was last seen. After losing it for
    longer than `max_lost_frames`, we restart from a frame with a single candidate.
    """
    candidates = drop_static(candidates)
    by_frame = {f: g[["x_m", "y_m"]].to_numpy() for f, g in candidates.groupby("frame")}
    rows, last, last_frame = [], None, None
    for frame in sorted(by_frame):
        points = by_frame[frame]
        if last is not None and frame - last_frame > max_lost_frames:
            last = None  # lost for too long: search afresh
        if last is None:
            if len(points) == 1:  # only (re)start when the choice is unambiguous
                last, last_frame = points[0], frame
                rows.append((frame, *last))
            continue
        reach = 1.0 + MAX_BALL_SPEED_MPS * (frame - last_frame) / fps
        distances = np.linalg.norm(points - last, axis=1)
        if distances.min() <= reach:
            last, last_frame = points[distances.argmin()], frame
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
