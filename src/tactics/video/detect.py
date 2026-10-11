"""Find players in top-view video frames. Two approaches, compared in scripts/spike_phase7_detect.py.

A. `RFDetrDetector`: a pretrained object detector (RF-DETR, COCO classes, Apache 2.0),
   run on overlapping tiles because players are only ~20-40 px in a 4K frame.
B. `BackgroundDetector`: the drone hovers in place, so the per-pixel median of
   many frames is an empty pitch (players move, so they vanish from the median).
   Anything that differs from that background is a player. Pitch lines are part
   of the background, so white shirts are not confused with white lines.

The drone drifts (up to ~50 px and 1.5 degrees in 30 s, about 2 m on the pitch),
so `Stabilizer` aligns every frame to a reference frame first; the pitch
calibration belongs to that reference frame.

Detections are an (n, 2) array of pixel centres (x, y) in the full frame.
"""

import cv2
import numpy as np

from tactics.video.calibration import PitchCalibration


def read_frames(video_path: str, indices: list[int]) -> dict[int, np.ndarray]:
    """Read the given 0-based frame indices (BGR images)."""
    capture = cv2.VideoCapture(str(video_path))
    frames = {}
    for index in sorted(indices):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if ok:
            frames[index] = frame
    capture.release()
    return frames


class Stabilizer:
    """Aligns frames to a reference frame with ECC (rotation + shift), estimated at low resolution."""

    def __init__(self, reference: np.ndarray, scale: float = 0.25):
        self.scale = scale
        self.reference = self._gray(reference)
        self.last_matrix = np.eye(2, 3, dtype=np.float32)
        self.failures = 0  # frames where alignment did not converge and the previous warp was reused

    def _gray(self, frame: np.ndarray) -> np.ndarray:
        small = cv2.resize(frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

    def warp(self, frame: np.ndarray) -> np.ndarray:
        """2x3 matrix mapping reference pixels to this frame's pixels (full resolution)."""
        start = self.last_matrix.copy()
        start[:, 2] *= self.scale  # start from the previous frame's warp (the drone drifts slowly)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
        try:
            _, matrix = cv2.findTransformECC(self.reference, self._gray(frame), start, cv2.MOTION_EUCLIDEAN, criteria, None, 11)
        except cv2.error:
            self.failures += 1  # e.g. a blurred frame: reuse the last good alignment instead of crashing
            return self.last_matrix.copy()
        matrix[:, 2] /= self.scale  # rotation is scale-free; the shift scales with resolution
        self.last_matrix = matrix
        return matrix

    @staticmethod
    def align(frame: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Resample the frame into reference coordinates."""
        height, width = frame.shape[:2]
        return cv2.warpAffine(frame, matrix, (width, height), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)

    @staticmethod
    def to_reference(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Frame pixel coordinates -> reference pixel coordinates."""
        inverse = cv2.invertAffineTransform(matrix)
        points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        return points @ inverse[:, :2].T + inverse[:, 2]


def pitch_mask(shape: tuple[int, int], calibration: PitchCalibration, margin_m: float = 2.0) -> np.ndarray:
    """255 inside the pitch (plus a margin), 0 outside: ignores benches, staff and spectators."""
    half_length, half_width = 52.5 + margin_m, 34.0 + margin_m
    corners = np.array([[-half_length, -half_width], [half_length, -half_width],
                        [half_length, half_width], [-half_length, half_width]])
    polygon = calibration.from_pitch(corners).astype(np.int32)
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)
    return mask


class BackgroundDetector:
    """Approach B: difference from a median background, then connected blobs of player size.

    Works on frames already aligned to the reference (see `Stabilizer`); returns reference coordinates.
    """

    def __init__(self, background_frames: list[np.ndarray], mask: np.ndarray, scale: float = 0.5,
                 threshold: int = 30, min_area_px: int = 20, max_area_px: int = 900):
        self.scale = scale  # work at half resolution: 4x fewer pixels, players still ~10-20 px
        small = [self._resize(f) for f in background_frames]
        self.background = np.median(np.stack(small), axis=0).astype(np.uint8)
        self.mask = self._resize(mask)
        self.threshold, self.min_area, self.max_area = threshold, min_area_px, max_area_px

    def _resize(self, image: np.ndarray) -> np.ndarray:
        return cv2.resize(image, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)

    def foreground(self, frame: np.ndarray) -> np.ndarray:
        """Binary image of pixels that differ from the empty pitch."""
        diff = cv2.absdiff(self._resize(frame), self.background).max(axis=2)  # strongest colour channel
        _, binary = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)
        binary = cv2.bitwise_and(binary, self.mask)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)  # remove single-pixel noise
        return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)  # join a player's parts

    def detect(self, frame: np.ndarray) -> np.ndarray:
        count, _, stats, centroids = cv2.connectedComponentsWithStats(self.foreground(frame))
        areas = stats[1:, cv2.CC_STAT_AREA]  # row 0 is the background
        keep = (areas >= self.min_area) & (areas <= self.max_area)
        return centroids[1:][keep] / self.scale


class RFDetrDetector:
    """Approach A: pretrained RF-DETR on overlapping tiles, keeping 'person' detections."""

    PERSON = 1  # COCO category id used by rfdetr's pretrained weights

    def __init__(self, tile_px: int = 640, overlap: float = 0.15, confidence: float = 0.3):
        import supervision as sv
        from rfdetr import RFDETRBase  # heavy import (PyTorch); only when this approach is used

        self.model = RFDETRBase()
        self.confidence = confidence
        self.slicer = sv.InferenceSlicer(
            callback=self._predict_tile, slice_wh=(tile_px, tile_px), overlap_wh=(int(tile_px * overlap),) * 2,
            iou_threshold=0.3,
        )

    def _predict_tile(self, tile: np.ndarray):
        rgb = cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)
        return self.model.predict(rgb, threshold=self.confidence)

    def detect(self, frame: np.ndarray) -> np.ndarray:
        detections = self.slicer(frame)
        people = detections[detections.class_id == self.PERSON]
        boxes = people.xyxy
        return np.column_stack([(boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2]) if len(boxes) else np.empty((0, 2))
