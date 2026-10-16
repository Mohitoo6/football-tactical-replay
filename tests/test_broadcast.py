"""Tests of the broadcast-camera path (Phase 8) on synthetic images with known cameras: no model, no download.

Skipped unless OpenCV is installed (`uv sync --group video`, or headless OpenCV in CI).
"""

import numpy as np
import pandas as pd
import pytest

cv2 = pytest.importorskip("cv2")

from tactics.broadcast.calibrate import (camera_track, homography_at, line_agreement, pitch_line_points,  # noqa: E402
                                         project, to_pitch)
from tactics.broadcast.ball import KalmanBall, link_ball, reject_heads, search_window  # noqa: E402
from tactics.broadcast.detect import shirt_colour  # noqa: E402
from tactics.broadcast.pipeline import upsample  # noqa: E402
from tactics.data.clips import Clip  # noqa: E402
from tactics.viz.overlay import TEAM_COLOURS, Minimap, draw_rings  # noqa: E402

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


def test_rings_are_drawn_at_each_persons_feet_in_their_team_colour():
    h = side_camera()
    frame = np.full((1080, 1920, 3), GRASS, np.uint8)
    people = pd.DataFrame({"x_m": [-35.0, -10.0, -20.0], "y_m": [0.0, -15.0, 20.0], "side": ["home", "away", "other"]})
    draw_rings(frame, h, people)
    for x, y, side in people.itertuples(index=False):
        px, py = project(np.array([[x + 0.8, y]]), h)[0].astype(int)  # a point on the ring
        patch = frame[py - 3:py + 4, px - 3:px + 4].reshape(-1, 3).astype(int)
        assert np.abs(patch - np.array(TEAM_COLOURS[side])).sum(axis=1).min() < 60


def test_upsample_bridges_a_short_gap_but_not_a_long_one():
    rows = {"frame": [0, 2, 10], "period": 1, "time_s": 0.0, "team": "home", "player_id": "A1",
            "player_name": "Player A1", "jersey": 1, "position": None, "x": [0.0, 2.0, 30.0], "y": 0.0}
    ball = pd.DataFrame({"frame": [0, 10], "period": 1, "time_s": 0.0, "x": 0.0, "y": 0.0, "z": 0.0,
                         "alive": False, "owning_team": None})
    clip = upsample(Clip({"frame_rate": 12.5, "start_s": 0.0}, pd.DataFrame(rows), ball), 2, bridge=3)
    frames = clip.players["frame"].tolist()
    assert frames == [0, 1, 2, 3, 4, 20]  # one missed frame bridged (0 -> 2); 2 -> 10 is too long
    assert clip.players.set_index("frame").loc[3, "x"] == pytest.approx(1.5)


def test_kalman_ball_predicts_a_moving_ball():
    kalman = KalmanBall(np.array([100.0, 100.0]))
    for step in range(1, 6):  # the ball moves 10 px right per frame
        kalman.predict()
        kalman.update(np.array([100.0 + 10 * step, 100.0]))
    assert kalman.predict() == pytest.approx([160.0, 100.0], abs=3.0)


def test_search_window_stays_inside_the_frame():
    assert search_window(np.array([50.0, 50.0]), (1080, 1920)) == (0, 0)
    assert search_window(np.array([1900.0, 1070.0]), (1080, 1920)) == (1920 - 704, 1080 - 704)


def test_ball_candidates_on_a_players_head_are_rejected():
    candidates = np.array([[105.0, 110.0, 0.9], [105.0, 195.0, 0.5], [400.0, 400.0, 0.4]])  # head, feet, free
    boxes = np.array([[90.0, 100.0, 120.0, 200.0]])
    kept = reject_heads(candidates, boxes)
    assert kept[:, :2].tolist() == [[105.0, 195.0], [400.0, 400.0]]


def test_link_ball_follows_the_ball_ignores_a_stray_hit_and_fills_short_gaps():
    rows = [(f, 100.0 + 8 * f, 300.0, 0.6) for f in range(10) if f not in (4, 5)]  # missed in frames 4 and 5
    rows.append((7, 900.0, 80.0, 0.2))  # a stray detection far away (a head or a shoe)
    ball = link_ball(pd.DataFrame(rows, columns=["frame", "px", "py", "confidence"]), frames=12)
    track = ball.set_index("frame")
    assert track.loc[0:9, "visible"].all() and not track.loc[10:11, "visible"].any()
    assert track.loc[4, "px"] == pytest.approx(132.0) and not track.loc[4, "detected"]  # filled by interpolation
    assert track.loc[7, "px"] == pytest.approx(156.0)  # the stray hit is not taken


def test_minimap_trails_end_when_a_player_leaves_the_view():
    minimap = Minimap(1920, 1080)
    image = np.zeros((1080, 1920, 3), np.uint8)
    player = pd.DataFrame({"team": ["home"], "jersey": [7], "x": [0.0], "y": [0.0]})
    for _ in range(5):
        minimap.draw(image, player, None, None)
    assert len(minimap.trails["home-7"]) == 5
    minimap.draw(image, player.iloc[:0], None, None)
    assert "home-7" not in minimap.trails


def test_painted_spots_and_marks_that_never_move_are_not_the_ball():
    from tactics.broadcast.ball import painted_spot, static_cells
    assert painted_spot(np.array([[0.3, -0.4], [41.0, 0.5], [-41.5, 1.0], [20.0, 5.0]])).tolist() == [True, True, True, False]
    frames = np.r_[np.arange(60), np.arange(10)]  # a mark seen in 60 frames; a ball passing through in 10
    xy = np.r_[np.tile([[17.2, 36.1]], (60, 1)), np.column_stack([np.linspace(-20, 20, 10), np.zeros(10)])]
    still = static_cells(frames, xy)
    assert still[:60].all() and not still[60:].any()
