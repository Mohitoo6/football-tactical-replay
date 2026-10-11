"""Tests for drawing and animation: every marker must sit exactly at its data position."""

import gc
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

from tactics.data.clips import Clip, load_clip
from tactics.geometry.links import line_links
from tactics.geometry.shape import hull_vertices, outfield, team_shape
from tactics.viz.animate import animate_clip, save_animation
from tactics.viz.pitch import BALL_OUT_TEXT, FramePainter, draw_frame, save_frame, team_label

CLIP_DIR = Path(__file__).resolve().parents[1] / "clips" / "musiala-winner"


@pytest.fixture(scope="module")
def clip():
    return load_clip(CLIP_DIR)


def markers(ax, label: str) -> np.ndarray:
    """Positions of the scatter markers with this legend label."""
    (collection,) = [c for c in ax.collections if c.get_label() == label]
    return np.asarray(collection.get_offsets())


def assert_markers_match_data(ax, clip, frame):
    players = clip.players[clip.players["frame"] == frame]
    for side in ("home", "away"):
        expected = players[players["team"] == side][["x", "y"]].to_numpy()
        drawn = markers(ax, team_label(clip, side))
        assert drawn.shape == (11, 2)
        np.testing.assert_allclose(drawn, expected)


def first_frames(clip: Clip, n: int) -> Clip:
    """A short copy of the clip, to keep rendering tests fast."""
    frames = clip.ball["frame"].iloc[:n]
    return Clip(clip.meta, clip.players[clip.players["frame"].isin(frames)], clip.ball.iloc[:n])


def test_draw_frame_places_players_and_ball_at_data_positions(clip):
    frame = int(clip.ball.loc[clip.ball["alive"], "frame"].iloc[100])
    ax = draw_frame(clip, frame)

    assert_markers_match_data(ax, clip, frame)
    ball = clip.ball[clip.ball["frame"] == frame][["x", "y"]].to_numpy()
    np.testing.assert_allclose(markers(ax, "Ball"), ball)
    plt.close(ax.figure)


def test_dead_ball_is_hidden_and_labelled(clip):
    frame = int(clip.ball.loc[~clip.ball["alive"], "frame"].iloc[0])
    ax = draw_frame(clip, frame)

    assert np.isnan(markers(ax, "Ball")).all()
    (label,) = [t for t in ax.texts if t.get_text() == BALL_OUT_TEXT]
    assert label.get_visible()
    plt.close(ax.figure)


def test_overlays_match_geometry_functions(clip):
    frame = int(clip.ball["frame"].iloc[275])
    painter = FramePainter(clip)
    painter.show(frame)
    players = clip.players[clip.players["frame"] == frame]

    for side in ("home", "away"):
        team = outfield(players[players["team"] == side])
        expected_hull = hull_vertices(team[["x", "y"]].to_numpy())
        drawn_hull = painter._hulls[side].get_xy()[:-1]  # matplotlib repeats the first corner to close it
        np.testing.assert_allclose(drawn_hull, expected_hull)

        expected_links = line_links(team, painter._formation_lines[side])
        drawn_links = [tuple(map(tuple, s)) for s in painter._links[side].get_segments()]
        np.testing.assert_allclose(drawn_links, expected_links)

        metrics = team_shape(team[["x", "y"]].to_numpy(), painter.attacking_right(side))
        assert f"width {metrics.width_m:.0f} m" in painter._metrics.get_text()
    plt.close(painter.fig)


def test_focus_team_attacks_right(clip):
    painter = FramePainter(clip, overlays=False)
    assert painter.attacking_right(clip.meta["focus_team"])
    assert not painter.attacking_right("home" if clip.meta["focus_team"] == "away" else "away")
    plt.close(painter.fig)


def test_plain_mode_draws_no_overlays(clip):
    plain, full = FramePainter(clip, overlays=False), FramePainter(clip)
    for painter in (plain, full):
        painter.show(int(clip.ball["frame"].iloc[0]))

    assert len(full.ax.patches) == len(plain.ax.patches) + 2  # one hull per team
    assert len(full.ax.collections) == len(plain.ax.collections) + 2  # one set of links per team
    assert not any("width" in t.get_text() for t in plain.ax.texts)
    plt.close("all")


def test_draw_frame_rejects_unknown_frame(clip):
    with pytest.raises(ValueError, match="not in clip"):
        draw_frame(clip, frame=-1)
    plt.close("all")


def test_painter_moves_markers_between_frames(clip):
    painter = FramePainter(clip)
    first, later = (int(f) for f in clip.ball["frame"].iloc[[0, 200]])
    painter.show(first)
    assert_markers_match_data(painter.ax, clip, first)
    painter.show(later)
    assert_markers_match_data(painter.ax, clip, later)
    plt.close(painter.fig)


@pytest.mark.filterwarnings("ignore:Animation was deleted without rendering")
def test_animation_runs_in_real_time(clip):
    animation = animate_clip(clip, step=2)
    assert animation._interval == pytest.approx(80.0)  # 2 frames at 25 fps = 80 ms
    assert len(list(animation.new_frame_seq())) == len(clip.ball[::2])
    plt.close("all")
    del animation
    gc.collect()  # trigger matplotlib's "never rendered" warning here, where it is ignored


def test_save_frame_writes_png(clip, tmp_path):
    out = tmp_path / "frame.png"
    save_frame(clip, int(clip.ball["frame"].iloc[0]), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_animation_writes_gif_with_every_frame(clip, tmp_path):
    out = save_animation(first_frames(clip, 5), tmp_path / "clip.gif", dpi=30)
    with Image.open(out) as gif:
        assert gif.n_frames == 5
        assert gif.info["duration"] == 40  # 25 fps


def test_save_animation_rejects_unknown_format(clip, tmp_path):
    with pytest.raises(ValueError, match="unsupported format"):
        save_animation(first_frames(clip, 2), tmp_path / "clip.avi")
