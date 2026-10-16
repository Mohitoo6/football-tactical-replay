"""People and ball in a broadcast frame.

Pretrained RF-DETR models (Apache-2.0, COCO classes). Measured on Mohit's hand-labelled
frames (DECISIONS.md, D29):
- people: RF-DETR Base on the whole frame found 87%; tiles or the Large model did not do
  better (89% at 8x the cost), because the rest are hidden behind other players. Tracking
  over time fills those gaps instead.
- ball: on the whole frame the ~10 px ball shrinks to ~3 px and was found in 32% of frames;
  the Large model on a 704 px window at full resolution around the ball found it in 63%.

A player's feet (bottom centre of the box) are on the ground, so the camera's homography
places them on the pitch.
"""

import cv2
import numpy as np
import pandas as pd

from tactics.broadcast.ball import WINDOW_PX
from tactics.broadcast.calibrate import to_pitch

PERSON, BALL = 1, 37  # COCO category ids in rfdetr's pretrained weights
PERSON_CONFIDENCE = 0.35
BALL_CONFIDENCE = 0.1  # low on purpose: the ball tracker decides which candidates are real
ON_PITCH_MARGIN_M = 3.0
PLAYER_COLUMNS = ["frame", "x_m", "y_m", "b", "g", "r", "px", "py", "height_px"]


def shirt_colour(frame: np.ndarray, box: np.ndarray) -> tuple[float, float, float] | None:
    """Median BGR colour of the upper body (15-50% of the box height), ignoring grass pixels."""
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    height = y2 - y1
    crop = frame[max(y1 + int(0.15 * height), 0):max(y1 + int(0.5 * height), 0), max(x1, 0):max(x2, 0)]
    if crop.size == 0:
        return None
    pixels = crop.reshape(-1, 3)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    grass = (hsv[:, 0] >= 30) & (hsv[:, 0] <= 90) & (hsv[:, 1] >= 40)
    shirt = pixels[~grass]
    if len(shirt) < 5:
        return None
    b, g, r = np.median(shirt, axis=0)
    return float(b), float(g), float(r)


def _rgb(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _balls(found, offset=(0, 0)) -> np.ndarray:
    """Ball detections as rows (x, y, confidence) in full-frame pixels."""
    keep = found.class_id == BALL
    boxes = found.xyxy[keep]
    centres = (boxes[:, :2] + boxes[:, 2:]) / 2 + np.asarray(offset, dtype=float)
    return np.column_stack([centres, found.confidence[keep]]) if len(boxes) else np.empty((0, 3))


class PeopleDetector:
    """RF-DETR Base on the whole frame: people (and ball candidates, for free)."""

    def __init__(self):
        from rfdetr import RFDETRBase  # heavy import (PyTorch); only when broadcast clips are processed

        self.model = RFDETRBase()

    def detect(self, frame: np.ndarray, homography: np.ndarray, frame_index: int) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        """(people on the pitch, all person boxes (x1, y1, x2, y2), ball candidates (x, y, confidence)).

        People columns: frame, x_m, y_m (pitch metres), b, g, r (shirt), px, py (feet pixels), height_px.
        Only people whose feet land on the pitch (+3 m) are kept: no crowd, photographers or substitutes.
        """
        found = self.model.predict(_rgb(frame), threshold=BALL_CONFIDENCE)
        people = (found.class_id == PERSON) & (found.confidence >= PERSON_CONFIDENCE)
        boxes = found.xyxy[people]
        rows = []
        for box in boxes:
            feet = np.array([[(box[0] + box[2]) / 2, box[3]]])
            x, y = to_pitch(feet, homography)[0]
            colour = shirt_colour(frame, box)
            if colour is not None and on_pitch(x, y):
                rows.append((frame_index, x, y, *colour, *feet[0], box[3] - box[1]))
        return pd.DataFrame(rows, columns=PLAYER_COLUMNS), boxes, _balls(found)


class BallDetector:
    """RF-DETR Large at full resolution, in a window around the expected ball or in tiles over the whole frame."""

    def __init__(self):
        import supervision as sv
        from rfdetr import RFDETRLarge

        self.model = RFDETRLarge()
        self.slicer = sv.InferenceSlicer(callback=lambda tile: self.model.predict(_rgb(tile), threshold=BALL_CONFIDENCE),
                                         slice_wh=(WINDOW_PX, WINDOW_PX), overlap_wh=(100, 100), iou_threshold=0.5)

    def in_window(self, frame: np.ndarray, x0: int, y0: int) -> np.ndarray:
        window = frame[y0:y0 + WINDOW_PX, x0:x0 + WINDOW_PX]
        return _balls(self.model.predict(_rgb(window), threshold=BALL_CONFIDENCE), offset=(x0, y0))

    def everywhere(self, frame: np.ndarray) -> np.ndarray:
        return _balls(self.slicer(frame))


def on_pitch(x: float, y: float) -> bool:
    return bool(np.isfinite(x) and np.isfinite(y) and abs(x) <= 52.5 + ON_PITCH_MARGIN_M and abs(y) <= 34 + ON_PITCH_MARGIN_M)
