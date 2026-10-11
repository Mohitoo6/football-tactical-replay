"""Tests for the video-to-tracking module, on synthetic images with known answers.

Skipped unless the optional video dependencies are installed (`uv sync --group video`).
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from tactics.video.calibration import PitchCalibration, corner_to_centre  # noqa: E402
from tactics.video.detect import BackgroundDetector, Stabilizer  # noqa: E402
from tactics.video.evaluate import combine, match  # noqa: E402
from tactics.video.soccertrack import load_boxes  # noqa: E402

GRASS = (60, 140, 60)  # BGR


def test_corner_to_centre():
    np.testing.assert_allclose(corner_to_centre([[0, 0], [105, 68], [52.5, 34]]), [[-52.5, -34], [52.5, 34], [0, 0]])


def test_calibration_recovers_a_known_mapping():
    # Image = 20 px per metre, pitch rotated 180 degrees (as in the SoccerTrack drone view), offset.
    pitch = np.array([[0, 0], [105, 0], [105, 68], [0, 68], [52.5, 34], [16.5, 13.84]], dtype=float)
    image = np.column_stack([3000 - 20 * pitch[:, 0], 2000 - 20 * pitch[:, 1]])
    calibration = PitchCalibration(pitch, image)

    assert calibration.reprojection_error_m().max() < 1e-6
    np.testing.assert_allclose(calibration.to_pitch([[3000 - 20 * 52.5, 2000 - 20 * 34]]), [[0, 0]], atol=1e-6)
    point = np.array([[10.0, -5.0]])
    np.testing.assert_allclose(calibration.to_pitch(calibration.from_pitch(point)), point, atol=1e-6)


def test_match_counts_and_errors():
    truth = np.array([[0, 0], [10, 0], [20, 0]], dtype=float)
    detected = np.array([[0.3, 0.4], [10, 5], [30, 30], [20, 0]], dtype=float)  # one far off, one extra
    result = match(detected, truth, max_distance=1.5)
    assert (result.true_positives, result.false_positives, result.false_negatives) == (2, 2, 1)
    assert sorted(result.errors.round(6)) == [0.0, 0.5]
    assert result.recall == pytest.approx(2 / 3) and result.precision == pytest.approx(0.5)
    assert match(np.empty((0, 2)), truth, 1.5).false_negatives == 3
    assert combine([result, result]).true_positives == 4


def test_stabilizer_point_mapping_inverts_a_shift():
    matrix = np.array([[1, 0, 12], [0, 1, -7]], dtype=np.float32)  # reference -> frame: +12 px x, -7 px y
    np.testing.assert_allclose(Stabilizer.to_reference([[112, 93]], matrix), [[100, 100]], atol=1e-5)


def textured_pitch(shift=(0, 0)) -> np.ndarray:
    """A grass image with lines and texture (so alignment has something to lock on), shifted by `shift` px."""
    rng = np.random.default_rng(1)
    image = np.full((400, 600, 3), GRASS, dtype=np.uint8)
    patches = cv2.GaussianBlur(rng.integers(0, 60, image.shape, dtype=np.uint8), (31, 31), 0)  # grass-like blotches
    image = cv2.add(image, patches)
    for x in range(50, 600, 120):
        cv2.line(image, (x, 0), (x, 399), (255, 255, 255), 3)
    cv2.circle(image, (300, 200), 80, (255, 255, 255), 3)
    return cv2.warpAffine(image, np.float32([[1, 0, shift[0]], [0, 1, shift[1]]]), (600, 400), borderMode=cv2.BORDER_REFLECT)


def test_stabilizer_recovers_a_drone_drift():
    reference = textured_pitch()
    drifted = textured_pitch(shift=(6, -4))
    matrix = Stabilizer(reference, scale=1.0).warp(drifted)
    np.testing.assert_allclose(matrix[:, 2], [6, -4], atol=0.5)


def test_stabilizer_reuses_last_warp_when_alignment_fails():
    stabilizer = Stabilizer(textured_pitch(), scale=1.0)
    blank = np.zeros((400, 600, 3), dtype=np.uint8)  # nothing to align to
    np.testing.assert_allclose(stabilizer.warp(blank), np.eye(2, 3))
    assert stabilizer.failures == 1


def test_background_detector_finds_moving_players_but_not_lines():
    rng = np.random.default_rng(2)
    frames, positions = [], []
    for _ in range(15):  # players at random places in each frame; lines never move
        frame = textured_pitch()
        spots = rng.integers([30, 30], [570, 370], size=(3, 2))
        for x, y in spots:
            cv2.circle(frame, (int(x), int(y)), 6, (230, 230, 230), -1)  # white shirt, like the lines
        frames.append(frame)
        positions.append(spots)

    mask = np.full((400, 600), 255, dtype=np.uint8)
    detector = BackgroundDetector(frames, mask, scale=1.0)
    found = detector.detect(frames[0])

    result = match(found, positions[0].astype(float), max_distance=2.0)
    assert result.true_positives == 3 and result.false_positives == 0
    assert result.errors.max() < 1.0


def test_load_boxes_reads_the_three_row_header(tmp_path):
    csv = tmp_path / "boxes.csv"
    csv.write_text(
        "TeamID,0,0,0,0,BALL,BALL,BALL,BALL\n"
        "PlayerID,7,7,7,7,BALL,BALL,BALL,BALL\n"
        "Attributes,bb_height,bb_left,bb_top,bb_width,bb_height,bb_left,bb_top,bb_width\n"
        "frame,,,,,,,,\n"
        "1,39,100,200,39,10,500,600,10\n"
    )
    boxes = load_boxes(csv)
    player = boxes[boxes["team"] == "0"].iloc[0]
    assert (player["player_id"], player["cx"], player["cy"]) == ("7", 119.5, 219.5)
    assert set(boxes["team"]) == {"0", "BALL"}


def drawn_pitch(scale: float = 4.0, offset=(60, 40)) -> tuple[np.ndarray, np.ndarray]:
    """A synthetic top-view pitch (105 x 68 m at `scale` px/m) with outline, halfway line, boxes and some text."""
    width, height = int(105 * scale + 2 * offset[0]), int(68 * scale + 2 * offset[1])
    image = np.full((height, width, 3), GRASS, dtype=np.uint8)
    def px(x, y):
        return (int(round(offset[0] + x * scale)), int(round(offset[1] + y * scale)))
    white = (255, 255, 255)
    cv2.rectangle(image, px(0, 0), px(105, 68), white, 2)
    cv2.line(image, px(52.5, 0), px(52.5, 68), white, 2)
    cv2.rectangle(image, px(0, 13.84), px(16.5, 54.16), white, 2)
    cv2.rectangle(image, px(88.5, 13.84), px(105, 54.16), white, 2)
    cv2.putText(image, "IMAGINE THE FUTURE", px(35, 72.5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, white, 2)  # text below the touchline
    corners = np.array([px(0, 0), px(105, 0), px(105, 68), px(0, 68)], dtype=float)
    return image, corners


def test_auto_calibration_finds_the_outline_not_the_text():
    from tactics.video.pitch_lines import auto_calibrate, pitch_corners

    image, true_corners = drawn_pitch()
    found = pitch_corners(image)
    # Same four corners (order may differ); each within 2 px.
    distances = np.linalg.norm(found[:, None] - true_corners[None], axis=2)
    assert distances.min(axis=1).max() < 2.0

    calibration = auto_calibrate(image)
    centre = calibration.to_pitch(np.array([[60 + 52.5 * 4, 40 + 34 * 4]]))
    np.testing.assert_allclose(np.abs(centre), [[0, 0]], atol=0.5)  # the centre spot maps to (0, 0)
