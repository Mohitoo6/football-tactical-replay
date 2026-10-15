"""Players and ball in a broadcast frame, placed on the pitch.

A pretrained RF-DETR (Apache-2.0, COCO classes) finds people and balls. From the
side-on broadcast camera players are upright and 40-120 px tall, which is what
COCO "person" was trained on (from straight above it found only 43%, D19).
A player's feet (bottom centre of the box) are on the ground, so the camera's
homography places them on the pitch. A ball in the air is not on the ground:
its pitch position is wrong while it flies (stated as a limit, D28).
"""

import cv2
import numpy as np
import pandas as pd

from tactics.broadcast.calibrate import to_pitch

PERSON, BALL = 1, 37  # COCO category ids in rfdetr's pretrained weights
PERSON_CONFIDENCE = 0.35
BALL_CONFIDENCE = 0.2  # the ball is small and often blurred; the ball follower removes stray hits
ON_PITCH_MARGIN_M = 3.0


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


class BroadcastDetector:
    def __init__(self):
        from rfdetr import RFDETRBase  # heavy import (PyTorch); only when broadcast clips are processed

        self.model = RFDETRBase()

    def detect(self, frame: np.ndarray, homography: np.ndarray, frame_index: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(players: frame, x_m, y_m, b, g, r, px, py, height_px; ball candidates: frame, x_m, y_m, confidence).

        px, py are the feet in image pixels. Only detections whose feet land on the pitch (+3 m) are kept,
        which removes the crowd, photographers and substitutes.
        """
        found = self.model.predict(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), threshold=BALL_CONFIDENCE)
        players, balls = [], []
        people = (found.class_id == PERSON) & (found.confidence >= PERSON_CONFIDENCE)
        for box in found.xyxy[people]:
            feet = np.array([[(box[0] + box[2]) / 2, box[3]]])
            x, y = to_pitch(feet, homography)[0]
            colour = shirt_colour(frame, box)
            if colour is not None and _on_pitch(x, y):
                players.append((frame_index, x, y, *colour, *feet[0], box[3] - box[1]))
        for box, confidence in zip(found.xyxy[found.class_id == BALL], found.confidence[found.class_id == BALL]):
            centre = np.array([[(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]])
            x, y = to_pitch(centre, homography)[0]
            if _on_pitch(x, y):
                balls.append((frame_index, x, y, float(confidence)))
        return (pd.DataFrame(players, columns=["frame", "x_m", "y_m", "b", "g", "r", "px", "py", "height_px"]),
                pd.DataFrame(balls, columns=["frame", "x_m", "y_m", "confidence"]))


def _on_pitch(x: float, y: float) -> bool:
    return bool(np.isfinite(x) and np.isfinite(y) and abs(x) <= 52.5 + ON_PITCH_MARGIN_M and abs(y) <= 34 + ON_PITCH_MARGIN_M)
