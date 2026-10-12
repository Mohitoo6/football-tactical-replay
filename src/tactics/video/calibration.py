"""Map between video pixels and pitch metres with a homography.

A homography is a 3x3 matrix that maps points on one flat plane (the pitch in
metres) to another (the image in pixels). Four or more known pairs of points,
e.g. pitch corners and penalty-box corners, are enough to estimate it. Our
pitch coordinates: metres, origin at the centre spot (as in the DFL clips).
"""

import ast
import json
from pathlib import Path

import cv2
import numpy as np

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


def load_keypoints(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read a SoccerTrack keypoints file: {"(x_m, y_m)": [u, v], ...}.

    Returns (pitch points in metres with the origin at a corner, matching image/GNSS points).
    """
    data = json.loads(Path(path).read_text())
    pitch = np.array([ast.literal_eval(key) for key in data], dtype=float)
    other = np.array(list(data.values()), dtype=float)
    return pitch, other


def corner_to_centre(points: np.ndarray) -> np.ndarray:
    """Corner-origin pitch metres (0..105, 0..68) -> centre-origin (-52.5..52.5, -34..34)."""
    return np.asarray(points, dtype=float) - [PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2]


class PitchCalibration:
    """Converts between pitch metres (centre origin) and another plane (image pixels or GNSS lon/lat)."""

    def __init__(self, pitch_m: np.ndarray, other: np.ndarray):
        self.pitch_m = corner_to_centre(pitch_m)
        self.other = np.asarray(other, dtype=float)
        # Plain least squares over all keypoints (method 0): the keypoints are curated, not noisy matches.
        self.to_pitch_matrix, _ = cv2.findHomography(self.other, self.pitch_m, method=0)
        self.from_pitch_matrix = np.linalg.inv(self.to_pitch_matrix)

    @classmethod
    def from_file(cls, path: Path) -> "PitchCalibration":
        return cls(*load_keypoints(path))

    def to_pitch(self, points: np.ndarray) -> np.ndarray:
        """Image (or GNSS) points -> pitch metres, centre origin."""
        return _apply(self.to_pitch_matrix, points)

    def from_pitch(self, points_m: np.ndarray) -> np.ndarray:
        """Pitch metres (centre origin) -> image (or GNSS) points."""
        return _apply(self.from_pitch_matrix, points_m)

    def reprojection_error_m(self) -> np.ndarray:
        """Distance in metres between each keypoint and where the homography maps it."""
        return np.linalg.norm(self.to_pitch(self.other) - self.pitch_m, axis=1)


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(points, matrix).reshape(-1, 2)
