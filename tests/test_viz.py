"""Tests for drawing: every marker must sit exactly at its data position."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from tactics.data.clips import load_clip
from tactics.viz.pitch import draw_frame, save_frame

CLIP_DIR = Path(__file__).resolve().parents[1] / "clips" / "musiala-winner"


@pytest.fixture(scope="module")
def clip():
    return load_clip(CLIP_DIR)


def markers(ax, label: str) -> np.ndarray:
    """Positions of the scatter markers with this legend label."""
    (collection,) = [c for c in ax.collections if c.get_label() == label]
    return np.asarray(collection.get_offsets())


def test_draw_frame_places_players_and_ball_at_data_positions(clip):
    frame = int(clip.ball["frame"].iloc[100])
    ax = draw_frame(clip, frame)

    players = clip.players[clip.players["frame"] == frame]
    for side in ("home", "away"):
        info = clip.meta["teams"][side]
        expected = players[players["team"] == side][["x", "y"]].to_numpy()
        drawn = markers(ax, f"{info['name']} ({info['formation']})")
        assert drawn.shape == (11, 2)
        np.testing.assert_allclose(drawn, expected)

    ball = clip.ball[clip.ball["frame"] == frame][["x", "y"]].to_numpy()
    np.testing.assert_allclose(markers(ax, "Ball"), ball)
    plt.close(ax.figure)


def test_draw_frame_rejects_unknown_frame(clip):
    with pytest.raises(ValueError, match="not in clip"):
        draw_frame(clip, frame=-1)
    plt.close("all")


def test_save_frame_writes_png(clip, tmp_path):
    out = tmp_path / "frame.png"
    save_frame(clip, int(clip.ball["frame"].iloc[0]), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
