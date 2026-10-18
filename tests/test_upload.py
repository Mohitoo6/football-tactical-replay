"""Tests for coordinate data a user uploads (our template, Excel, kloppy providers) -> clip."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tactics.ai.summary import build_summary
from tactics.data.clips import load_clip
from tactics.data.report import QualityReport
from tactics.data.upload import check_input, from_kloppy, from_template, read_table, to_clip
from tactics.data.validate import find_problems

ROOT = Path(__file__).resolve().parents[1]


def synthetic(seconds: float = 5.0, fps: float = 25.0, keeper_x: float = -48.0, with_position: bool = True) -> pd.DataFrame:
    """11 v 11 standing in two blocks, the home keeper at `keeper_x`, plus a ball, in our template."""
    rng = np.random.default_rng(0)
    rows = []
    home = rng.uniform([-40, -30], [-5, 30], (10, 2))
    away = rng.uniform([5, -30], [40, 30], (10, 2))
    for k in range(int(seconds * fps)):
        t = round(k / fps, 3)
        rows.append((t, "home", "Keeper", 1, "GK" if with_position else "", keeper_x, 0.0))
        rows.append((t, "away", "Keeper", 1, "GK" if with_position else "", -keeper_x, 0.0))
        for i, (x, y) in enumerate(home, 2):
            rows.append((t, "home", f"H{i}", i, "", x + 0.01 * k, y))
        for i, (x, y) in enumerate(away, 2):
            rows.append((t, "away", f"A{i}", i, "", x - 0.01 * k, y))
        rows.append((t, "ball", "", None, "", 0.1 * k, 0.0))
    return pd.DataFrame(rows, columns=["time_s", "team", "player", "jersey", "position", "x", "y"])


def read(table: pd.DataFrame, **kwargs):
    report = QualityReport()
    data = from_template(table, report, **kwargs)
    if data is not None:
        check_input(data, report)
    return data, report


def test_example_file_reproduces_the_bundled_clip():
    original = load_clip(ROOT / "clips" / "musiala-winner")
    data, report = read(read_table(ROOT / "templates" / "example_musiala_winner.csv"))
    assert report.status in ("ok", "warning"), report.summary()
    clip = to_clip(data, "uploaded-musiala", "Uploaded copy", focus_team=original.meta["focus_team"])
    assert not find_problems(clip.players, clip.ball)
    assert len(clip.ball) == len(original.ball)
    first = original.players[original.players["frame"] == original.players["frame"].min()].sort_values("player_name")
    mine = clip.players[clip.players["frame"] == 0].sort_values("player_name")
    np.testing.assert_allclose(mine[["x", "y"]].to_numpy(), first[["x", "y"]].to_numpy(), atol=0.01)
    assert build_summary(clip)["timeline"]  # the coach's facts can be built from it


def test_excel_files_are_read_like_csv(tmp_path):
    path = tmp_path / "match.xlsx"
    synthetic(seconds=4).to_excel(path, index=False)
    data, report = read(read_table(path))
    assert report.status == "ok", report.summary()
    assert data.frame_rate == 25.0 and data.players.groupby(["frame", "team"]).size().max() == 11


def test_missing_columns_are_refused_with_a_clear_reason():
    data, report = read(synthetic().drop(columns=["y"]))
    assert data is None and report.status == "rejected"
    assert "missing: y" in report.summary()


def test_wrong_units_are_caught():
    corner_origin = synthetic().assign(x=lambda t: t["x"] + 52.5, y=lambda t: t["y"] + 34)
    data, report = read(corner_origin)  # read as centre-origin metres: half the pitch lands outside
    failed = [c.name for c in report.checks if not c.passed]
    assert report.status == "rejected" and "positions on the pitch" in failed
    data, report = read(corner_origin, units="metres_corner")
    assert report.status == "ok", report.summary()


def test_normalised_units_become_metres():
    table = synthetic().assign(x=lambda t: t["x"] / 105 + 0.5, y=lambda t: t["y"] / 68 + 0.5)
    data, report = read(table, units="normalised")
    keeper = data.players[(data.players["team"] == "home") & (data.players["player_name"] == "Keeper")]
    assert keeper["x"].iloc[0] == pytest.approx(-48.0)


def test_short_clips_are_refused():
    data, report = read(synthetic(seconds=2))
    assert report.status == "rejected" and "clip length" in [c.name for c in report.checks if not c.passed]


def test_keeper_is_inferred_and_the_focus_team_attacks_left_to_right():
    data, report = read(synthetic(keeper_x=48.0, with_position=False))  # home keeper on the right, no GK labels
    assert not [c for c in report.checks if not c.passed and c.blocking]
    clip = to_clip(data, "x", "x", focus_team="home")
    keepers = clip.players[clip.players["position"] == "Goalkeeper"]
    assert set(keepers["team"]) == {"home", "away"}
    assert keepers.loc[keepers["team"] == "home", "x"].mean() < 0  # turned so home attacks left to right
    assert clip.meta["rotated"] and clip.meta["direction_known"]


def test_kloppy_datasets_are_cut_to_a_window():
    times = pd.to_timedelta(np.arange(0, 10, 0.04), unit="s")
    wide = pd.DataFrame({"period_id": 1, "timestamp": times, "ball_x": 1.0, "ball_y": 2.0, "ball_z": 0.0,
                         "ball_state": "alive", "p1_x": -40.0, "p1_y": 0.0, "p2_x": 40.0, "p2_y": 0.0})
    player = lambda pid, jersey: SimpleNamespace(player_id=pid, name=None, jersey_no=jersey, starting_position="GK")
    dataset = SimpleNamespace(to_df=lambda: wide, metadata=SimpleNamespace(frame_rate=25, teams=[
        SimpleNamespace(ground="home", name="Reds", players=[player("p1", 1)]),
        SimpleNamespace(ground="away", name="Blues", players=[player("p2", 1)])]))
    data = from_kloppy(dataset, period=1, start_s=2.0, end_s=6.0, source="test")
    assert len(data.ball) == 101 and data.team_names == {"home": "Reds", "away": "Blues"}
    assert set(data.players["position"]) == {"Goalkeeper"}
