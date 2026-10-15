"""Calibrate a top-view video automatically from its pitch lines (no hand-marked points).

Steps, on an image of the empty pitch (the median background):
1. Field mask: the largest green region, with holes filled (so lines inside it count).
2. Line pixels: white (low saturation, high brightness) inside the field.
3. Long straight segments (Hough). Text painted on the grass is made of short
   strokes, so a minimum length keeps it out.
4. Group segments into the two main directions and take the outermost line in
   each direction on each side: the touchlines and goal lines.
5. Their four intersections are the pitch corners -> homography to a pitch of
   known size (105 x 68 m by default).

Limits: assumes a near top-down view where the whole pitch outline is visible,
and a known pitch size. Lines alone cannot tell which goal is which, so the
result is correct up to the pitch's mirror symmetries.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from tactics.video.calibration import PITCH_LENGTH_M, PITCH_WIDTH_M, PitchCalibration

WHITE_OVER_GRASS = 1.17  # paint is this much brighter than the median grass (the old fixed 170 on grass of V ~145)
SAME_LINE_PX = 6  # segments whose ends are this close to a line belong to it (lines are ~2-5 px wide)


@dataclass
class LineFit:
    point: np.ndarray  # a point on the line (x, y)
    direction: np.ndarray  # unit direction (dx, dy)


def field_mask(image: np.ndarray) -> np.ndarray:
    """255 on the largest green area (holes filled), 0 elsewhere."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (30, 40, 40), (90, 255, 255))
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(green)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    region = np.where(labels == largest, 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(region)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled


def line_pixels(image: np.ndarray) -> np.ndarray:
    """255 where the image is white paint (bright, unsaturated) on or at the edge of the field.

    The field mask is grown slightly: when the strip of grass beyond a touchline
    is not green enough (e.g. in shadow), the green region ends inside the line
    and the touchline itself would be cut away (seen on segment 22:30).
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    value = hsv[..., 2]
    field = field_mask(image)
    # Brighter than this pitch's grass, not brighter than a fixed level: a fixed V >= 170 lost every
    # line on a 30% darker clip (D27). Comparing with the grass nearby instead added shadow edges.
    grass = float(np.median(value[field > 0]))
    white = np.where((value >= grass * WHITE_OVER_GRASS) & (hsv[..., 1] <= 70), 255, 0).astype(np.uint8)
    grow = int(0.008 * max(image.shape[:2])) | 1  # ~15 px at 1920 px wide, always odd
    field = cv2.dilate(field, np.ones((grow, grow), np.uint8))
    return cv2.bitwise_and(white, field)


def _intersect(a: LineFit, b: LineFit) -> np.ndarray:
    # Solve a.point + s * a.direction = b.point + t * b.direction.
    matrix = np.column_stack([a.direction, -b.direction])
    s, _ = np.linalg.solve(matrix, b.point - a.point)
    return a.point + s * a.direction


def _fit_line(points: np.ndarray) -> LineFit:
    vx, vy, x0, y0 = cv2.fitLine(points.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    return LineFit(np.array([x0, y0]), np.array([vx, vy]))


def candidate_lines(lines_mask: np.ndarray, min_length_px: int) -> dict[str, list[tuple[float, LineFit]]]:
    """Long straight lines in the two main directions ("a" and "b"), each with its position across that direction.

    A line counts if it runs at least 60% as far as the longest line in its direction: touchlines,
    goal lines and the halfway line do; painted text does not. Rows of white objects beyond the
    pitch (e.g. practice goals) can also qualify, so the final choice is left to `pitch_corners`.
    """
    segments = cv2.HoughLinesP(lines_mask, 1, np.pi / 720, threshold=80, minLineLength=min_length_px, maxLineGap=25)
    if segments is None or len(segments) < 4:
        raise ValueError("not enough long straight lines found to locate the pitch outline")
    segments = segments.reshape(-1, 4).astype(float)  # OpenCV 4 returns (n, 1, 4), OpenCV 5 (n, 4)
    angles = np.degrees(np.arctan2(segments[:, 3] - segments[:, 1], segments[:, 2] - segments[:, 0])) % 180
    lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    main = angles[np.argmax(lengths)] % 90  # the longest segment sets the grid orientation
    ys, xs = np.nonzero(lines_mask)
    pixels = np.column_stack([xs, ys])

    result = {}
    for name, angle in (("a", main), ("b", main + 90)):
        offset = np.abs((angles - angle + 90) % 180 - 90)
        group = segments[offset < 5]  # within 5 degrees of this direction
        if len(group) < 2:
            raise ValueError("pitch outline needs lines in two directions")
        normal = np.array([-np.sin(np.radians(angle)), np.cos(np.radians(angle))])
        direction = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])

        levels = []
        for on_line in _same_line_groups(group):
            rough = _fit_line(np.vstack([on_line[:, :2], on_line[:, 2:]]))
            span = np.concatenate([on_line[:, :2] @ direction, on_line[:, 2:] @ direction])
            levels.append((float(rough.point @ normal), span.max() - span.min(), span.min(), span.max(), rough))
        longest = max(length for _, length, _, _, _ in levels)
        fitted = []
        for position, length, low, high, rough in levels:
            if length < 0.6 * longest:
                continue
            # Refit precisely on all line pixels within a few px of this line, along its span.
            across = np.abs((pixels - rough.point) @ np.array([-rough.direction[1], rough.direction[0]]))
            along = pixels @ direction
            near = pixels[(across < SAME_LINE_PX) & (along >= low - 5) & (along <= high + 5)]
            fitted.append((position, _fit_line(near)))
        result[name] = sorted(fitted, key=lambda item: item[0])
    return result


def _same_line_groups(segments: np.ndarray) -> list[np.ndarray]:
    """Group Hough segments that lie on one straight line (both ends within a few px of it), longest first.

    Grouping by distance across one shared direction failed when the two touchlines are not quite
    parallel in the image (0.8 degrees apart on a 1080p clip): a 700 px line drifts ~10 px across that
    direction, so its pieces fell into different groups, each too short to count (DECISIONS.md, D27).
    """
    lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    groups: list[list[int]] = []
    lines: list[LineFit] = []
    for i in np.argsort(-lengths):
        ends = segments[i].reshape(2, 2)
        for members, line in zip(groups, lines):
            across = np.abs((ends - line.point) @ np.array([-line.direction[1], line.direction[0]]))
            if across.max() < SAME_LINE_PX:
                members.append(i)
                break
        else:
            groups.append([i])
            lines.append(_fit_line(ends))
    return [segments[members] for members in groups]


def pitch_corners(image: np.ndarray, min_length_frac: float = 0.15,
                  aspect: float = PITCH_LENGTH_M / PITCH_WIDTH_M) -> np.ndarray:
    """Pixel positions of the four pitch corners, ordered around the outline.

    Among all pairs of long lines in each direction, pick the rectangle whose length/width ratio is
    closest to a real pitch (105/68 by default); among equally good ones, the larger. Taking simply
    the outermost lines picked up a row of practice goals beyond the touchline (DECISIONS.md, D24).
    """
    lines = candidate_lines(line_pixels(image), int(min_length_frac * max(image.shape[:2])))
    best, best_key = None, None
    for i, (pos_a_low, a_low) in enumerate(lines["a"]):
        for pos_a_high, a_high in lines["a"][i + 1:]:
            for j, (pos_b_low, b_low) in enumerate(lines["b"]):
                for pos_b_high, b_high in lines["b"][j + 1:]:
                    corners = np.array([_intersect(a_low, b_low), _intersect(a_low, b_high),
                                        _intersect(a_high, b_high), _intersect(a_high, b_low)])
                    side_1 = np.linalg.norm(corners[1] - corners[0])
                    side_2 = np.linalg.norm(corners[2] - corners[1])
                    ratio = max(side_1, side_2) / max(min(side_1, side_2), 1e-6)
                    # Within 5% of the true ratio counts as a match; then prefer the biggest outline.
                    key = (round(abs(np.log(ratio / aspect)) / 0.05), -side_1 * side_2)
                    if best_key is None or key < best_key:
                        best, best_key = corners, key
    if best is None:
        raise ValueError("no pair of lines in each direction forms a pitch outline")
    return best


def auto_calibrate(image: np.ndarray, length_m: float = PITCH_LENGTH_M, width_m: float = PITCH_WIDTH_M,
                   image_scale: float = 1.0) -> PitchCalibration:
    """Calibration from the pitch outline: the longer pair of sides is the touchlines.

    `image_scale` is the size of `image` relative to the video frames (0.5 for a half-resolution background).
    """
    corners = pitch_corners(image, aspect=length_m / width_m) / image_scale
    side_01 = np.linalg.norm(corners[1] - corners[0])
    side_12 = np.linalg.norm(corners[2] - corners[1])
    if side_01 >= side_12:  # corners 0 -> 1 run along a touchline
        pitch = [[0, 0], [length_m, 0], [length_m, width_m], [0, width_m]]
    else:
        pitch = [[0, 0], [0, width_m], [length_m, width_m], [length_m, 0]]
    return PitchCalibration(np.array(pitch, dtype=float), corners)


def outline_ratio_error(corners: np.ndarray, length_m: float = PITCH_LENGTH_M, width_m: float = PITCH_WIDTH_M) -> float:
    """How far the found outline's length/width ratio is from the real pitch's, as a fraction (0.03 = 3%)."""
    sides = np.linalg.norm(corners - np.roll(corners, -1, axis=0), axis=1)
    side_1, side_2 = (sides[0] + sides[2]) / 2, (sides[1] + sides[3]) / 2  # mean of opposite sides
    ratio = max(side_1, side_2) / max(min(side_1, side_2), 1e-6)
    return float(abs(ratio / (length_m / width_m) - 1))
