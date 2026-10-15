"""Tests of the broadcast-camera path (Phase 8) on synthetic images with known cameras: no model, no download.

Skipped unless OpenCV is installed (`uv sync --group video`, or headless OpenCV in CI).
"""

import numpy as np
import pandas as pd
import pytest

cv2 = pytest.importorskip("cv2")

from tactics.broadcast.calibrate import (camera_track, homography_at, line_agreement, pitch_line_points,  # noqa: E402
                                         project, to_pitch)
from tactics.broadcast.detect import shirt_colour  # noqa: E402
from tactics.broadcast.pipeline import upsample  # noqa: E402
from tactics.data.clips import Clip  # noqa: E402
from tactics.viz.overlay import TEAM_COLOURS, draw_overlay  # noqa: E402

GRASS = (60, 140, 60)  # BGR


def side_camera(shift_x_m: float = 0.0) -> np.ndarray:
    """A side-on view of the left half of the pitch: the far touchline is shorter (perspective)."""
    pitch = np.float32([[-52.5, -34], [0, -34], [0, 34], [-52.5, 34]]) + np.float32([shift_x_m, 0])
    image = np.float32([[260, 220], [1500, 220], [1880, 1000], [40, 1000]])
    return cv2.getPerspectiveTransform(pitch, image).astype(float)


def drawn_view(homography: np.ndarray) -> np.ndarray:
    frame = np.full((1080, 1920, 3), GRASS, np.uint8)
    for points in pitch_line_points():
        cv2.polylines(frame, [project(points, homography).astype(np.int32)], False, (255, 255, 255), 3)
    return frame


def test_projection_round_trip():
    h = side_camera()
    points = np.array([[-40.0, 10.0], [-11.0, 0.0], [0.0, -34.0]])
    np.testing.assert_allclose(to_pitch(project(points, h), h), points, atol=1e-6)


def test_line_agreement_separates_a_right_from_a_wrong_calibration():
    frame = drawn_view(side_camera())
    assert line_agreement(frame, side_camera()) > 0.9
    assert line_agreement(frame, side_camera(shift_x_m=3.0)) < 0.4  # 3 m off: lines miss the paint


def test_camera_track_interpolates_and_stops_at_cuts_and_gaps():
    a, b = side_camera(), side_camera(shift_x_m=1.0)
    far = side_camera(shift_x_m=40.0)  # the view jumps 40 m in 0.2 s: a cut
    homographies = [a, b, None, None, None, far, far]
    agreements = [0.9, 0.9, 0, 0, 0, 0.9, 0.9]
    camera = camera_track(homographies, agreements, key_fps=5, video_fps=25, frames=31)
    middle = homography_at(camera, 2)  # 2/25 s = 0.4 of the way from keyframe 0 to 1
    expected = 0.6 * a / a[2, 2] + 0.4 * b / b[2, 2]
    np.testing.assert_allclose(middle, expected, rtol=1e-9)
    assert homography_at(camera, 10) is None  # keyframes 1 -> 5: gap of 3 missing keyframes
    assert homography_at(camera, 25) is not None  # keyframe 5 itself
    two_shots = camera_track([a, far], [0.9, 0.9], key_fps=5, video_fps=25, frames=6)
    assert homography_at(two_shots, 2) is None  # never blend across a cut


def test_camera_track_drops_keyframes_with_low_line_agreement():
    camera = camera_track([side_camera()], [0.2], key_fps=5, video_fps=25, frames=1)
    assert homography_at(camera, 0) is None


def test_upsample_interpolates_only_between_keyframes_where_seen():
    players = pd.DataFrame({
        "frame": [0, 1, 3], "period": 1, "time_s": [0.0, 0.2, 0.6], "team": "home", "player_id": "A1",
        "player_name": "Player A1", "jersey": 1, "position": None, "x": [0.0, 1.0, 10.0], "y": [0.0, 0.0, 0.0]})
    ball = pd.DataFrame({"frame": [0, 1, 2, 3], "period": 1, "time_s": [0.0, 0.2, 0.4, 0.6], "x": [0.0, 2.0, 2.0, 4.0],
                         "y": 0.0, "z": 0.0, "alive": [True, True, False, True], "owning_team": None})
    clip = upsample(Clip({"frame_rate": 5.0, "start_s": 0.0}, players, ball), 5)
    assert clip.meta["frame_rate"] == 25.0
    x = clip.players.set_index("frame")["x"]
    assert list(x.index) == [0, 1, 2, 3, 4, 5, 15]  # seen at keyframes 0 and 1: filled between; keyframe 3 alone
    assert x.loc[2] == pytest.approx(0.4)
    alive = clip.ball.set_index("frame")["alive"]
    assert alive.loc[0:5].all() and not alive.loc[6:14].any() and alive.loc[15]


def test_shirt_colour_ignores_the_grass_around_the_player():
    frame = np.full((200, 200, 3), GRASS, np.uint8)
    cv2.rectangle(frame, (95, 60), (105, 140), (30, 30, 200), -1)  # a thin red player on grass
    b, g, r = shirt_colour(frame, np.array([80, 50, 120, 150]))
    assert r > 150 and g < 80


def test_overlay_draws_each_team_where_its_players_stand():
    h = side_camera()
    frame = np.full((1080, 1920, 3), GRASS, np.uint8)
    players = pd.DataFrame({"team": ["home"] * 3 + ["away"] * 3, "position": None,
                            "x": [-40, -35, -38, -15, -10, -12], "y": [-10, 0, 10, -20, -15, -25]})
    out = draw_overlay(frame, h, players, None, rotated=False, team_labels={"home": "Red", "away": "Blue"})
    for side, (x, y) in (("home", (-35, 0)), ("away", (-10, -15))):
        px, py = project(np.array([[x + 0.9, y]]), h)[0].astype(int)  # on the player's marker ring
        patch = out[py - 3:py + 4, px - 3:px + 4].reshape(-1, 3).astype(int)
        colour = np.array(TEAM_COLOURS[side])
        assert np.abs(patch - colour).sum(axis=1).min() < 60
