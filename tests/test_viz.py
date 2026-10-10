"""Tests for drawing and animation: every marker must sit exactly at its data position."""

import gc
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

from tactics.data.clips import Clip, load_clip
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
