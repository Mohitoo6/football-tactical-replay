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


# --- tracking, teams and ball (synthetic, no video needed) --------------------

import pandas as pd  # noqa: E402

from tactics.video.ball import follow_ball, follow_ball_both_ways  # noqa: E402
from tactics.video.track import PointTracker, assign_teams, stitch_tracks, track_points  # noqa: E402

WHITE_SHIRT, BLUE_SHIRT = (230, 230, 230), (200, 120, 60)  # BGR


def crossing_players(frames: int = 40) -> pd.DataFrame:
    """Two players of different teams run past each other, 0.4 m apart at the closest point."""
    rows = []
    for f in range(frames):
        t = f / (frames - 1)
        rows.append({"frame": f, "x_m": -4 + 8 * t, "y_m": 0.2, "who": "white", **dict(zip("bgr", WHITE_SHIRT))})
        rows.append({"frame": f, "x_m": 4 - 8 * t, "y_m": -0.2, "who": "blue", **dict(zip("bgr", BLUE_SHIRT))})
    return pd.DataFrame(rows)


def test_colour_keeps_identities_when_opponents_cross():
    tracks = track_points(crossing_players(), PointTracker(max_distance_m=1.5, colour_weight=2.0))
    assert tracks.groupby("who")["track_id"].nunique().tolist() == [1, 1]  # one id each, all the way
    assert tracks["track_id"].nunique() == 2


def test_stitching_joins_a_broken_track():
    one_player = pd.DataFrame({"frame": range(30), "x_m": np.linspace(0, 3, 30), "y_m": 0.0,
                               "b": 230, "g": 230, "r": 230})
    broken = one_player.assign(track_id=np.where(one_player["frame"] < 15, 7, 8))
    assert stitch_tracks(broken)["track_id"].nunique() == 1


def test_assign_teams_splits_by_shirt_colour():
    rows = []
    for track_id, shirt in enumerate([WHITE_SHIRT] * 5 + [BLUE_SHIRT] * 5 + [(20, 220, 240)]):  # 5 + 5 + a yellow referee
        for f in range(60):
            rows.append({"frame": f, "track_id": track_id, **dict(zip("bgr", shirt))})
    teams = assign_teams(pd.DataFrame(rows))
    assert teams.iloc[:5].nunique() == 1 and teams.iloc[5:10].nunique() == 1
    assert teams.iloc[0] != teams.iloc[5] and set(teams.iloc[:10]) == {"A", "B"}
    assert teams.iloc[10] == "other"


def test_ball_follower_ignores_far_noise_and_does_not_invent_hidden_frames():
    rows = [{"frame": f, "x_m": 0.3 * f, "y_m": 0.0} for f in range(20) if not 8 <= f < 12]  # hidden for 4 frames
    rows += [{"frame": f, "x_m": 30.0, "y_m": 20.0} for f in range(5, 20)]  # a far-away white spot
    ball = follow_ball(pd.DataFrame(rows), fps=30.0)
    assert set(ball["frame"]) == set(range(20)) - set(range(8, 12))  # no positions made up while hidden
    assert ball["x_m"].max() < 6


def test_ball_both_ways_fills_frames_before_a_restart():
    # Two candidates (ambiguous) in the first 5 frames, then only the ball: forward misses the start.
    rows = [{"frame": f, "x_m": 0.3 * f, "y_m": 0.0} for f in range(20)]
    rows += [{"frame": f, "x_m": 10.0 + 0.1 * f, "y_m": 5.0} for f in range(5)]
    candidates = pd.DataFrame(rows)
    assert follow_ball(candidates, 30.0)["frame"].min() == 5
    both = follow_ball_both_ways(candidates, 30.0)
    assert both["frame"].min() == 0 and both.loc[both["frame"] == 0, "x_m"].iloc[0] == 0.0


def test_export_uses_only_video_derived_columns():
    """The clip must be buildable from our own video columns alone (x_m, y_m, colour),
    with no dataset-calibrated x/y present: guards against ground truth leaking in."""
    from tactics.video.export import tracks_to_clip

    rows = []
    for f in range(40):
        for k in range(3):
            rows.append({"frame": f, "track_id": k, "x_m": -45.0 + 10 * k if k == 0 else 5.0 * k, "y_m": 2.0 * k,
                         **dict(zip("bgr", WHITE_SHIRT))})
            rows.append({"frame": f, "track_id": 10 + k, "x_m": 45.0 - 10 * k if k == 0 else -5.0 * k, "y_m": -2.0 * k,
                         **dict(zip("bgr", BLUE_SHIRT))})
    tracks = pd.DataFrame(rows)
    assert not {"x", "y"} & set(tracks.columns)
    teams = pd.Series({0: "A", 1: "A", 2: "A", 10: "B", 11: "B", 12: "B"})
    teams.attrs["keepers"] = {-1: 0, 1: 10}
    ball = pd.DataFrame({"frame": range(0, 40, 2), "x_m": 0.0, "y_m": 0.0})

    clip = tracks_to_clip(tracks, teams, ball, fps=30.0, clip_id="t", title="t", start_s=0)

    assert clip.meta["teams"]["home"]["name"].endswith("(lighter shirts)")  # white team is home
    keepers = clip.players[clip.players["position"] == "Goalkeeper"]
    assert keepers.loc[keepers["team"] == "home", "x"].mean() < 0  # home attacks left to right
    assert clip.ball["alive"].mean() == 0.5  # ball known in every other frame only
