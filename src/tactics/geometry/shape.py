"""Team shape metrics: hull, width, depth, compactness, defensive line height.

All functions take an (n, 2) array of (x, y) positions in metres, origin at
the pitch centre. By convention we pass outfield players only: a goalkeeper
standing 30 m behind the defence would distort every shape metric.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull, QhullError

HALF_LENGTH_M = 52.5


def hull_vertices(points: np.ndarray) -> np.ndarray:
    """Corners of the convex hull (the tightest shape around all points), in drawing order.

    Returns an empty (0, 2) array if the points do not form an area (fewer than
    3 points, or all on one line).
    """
    points = np.asarray(points, dtype=float)
    try:
        return points[ConvexHull(points).vertices]
    except (QhullError, ValueError):
        return np.empty((0, 2))


def hull_area(points: np.ndarray) -> float:
    """Area of the convex hull in square metres (0 if the points do not form an area)."""
    try:
        # For 2-D hulls scipy calls the area "volume" (and "area" is the perimeter).
        return float(ConvexHull(np.asarray(points, dtype=float)).volume)
    except (QhullError, ValueError):
        return 0.0


def width(points: np.ndarray) -> float:
    """Distance between the widest players across the pitch (y), in metres."""
    y = np.asarray(points, dtype=float)[:, 1]
    return float(y.max() - y.min())


def depth(points: np.ndarray) -> float:
    """Distance between the deepest and the most advanced player along the pitch (x), in metres."""
    x = np.asarray(points, dtype=float)[:, 0]
    return float(x.max() - x.min())


def centroid(points: np.ndarray) -> np.ndarray:
    """Average position of the points."""
    return np.asarray(points, dtype=float).mean(axis=0)


def stretch_index(points: np.ndarray) -> float:
    """Average distance of the players from their centroid, in metres (smaller = more compact)."""
    points = np.asarray(points, dtype=float)
    return float(np.linalg.norm(points - centroid(points), axis=1).mean())


def defensive_line_height(points: np.ndarray, attacking_right: bool) -> float:
    """Distance from the team's own goal line to its deepest outfield player, in metres.

    A team attacking to the right defends the goal at x = -52.5.
    """
    x = np.asarray(points, dtype=float)[:, 0]
    if attacking_right:
        return float(x.min() + HALF_LENGTH_M)
    return float(HALF_LENGTH_M - x.max())


@dataclass
class ShapeMetrics:
    width_m: float
    depth_m: float
    hull_area_m2: float
    stretch_m: float
    line_height_m: float
    centroid_x: float
    centroid_y: float


def team_shape(points: np.ndarray, attacking_right: bool) -> ShapeMetrics:
    """All shape metrics for one team in one frame."""
    cx, cy = centroid(points)
    return ShapeMetrics(
        width_m=width(points),
        depth_m=depth(points),
        hull_area_m2=hull_area(points),
        stretch_m=stretch_index(points),
        line_height_m=defensive_line_height(points, attacking_right),
        centroid_x=float(cx),
        centroid_y=float(cy),
    )


def outfield(players: pd.DataFrame) -> pd.DataFrame:
    """Drop goalkeepers from a players table."""
    return players[players["position"] != "Goalkeeper"]


def shape_over_time(players: pd.DataFrame, team: str, attacking_right: bool) -> pd.DataFrame:
    """Shape metrics for `team` in every frame: one row per frame, one column per metric."""
    rows = []
    for frame, group in outfield(players[players["team"] == team]).groupby("frame"):
        metrics = team_shape(group[["x", "y"]].to_numpy(), attacking_right)
        rows.append({"frame": frame, **asdict(metrics)})
    return pd.DataFrame(rows)
