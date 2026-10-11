"""Tests for the data layer: loading helpers, orientation, validation and clips.

Most tests use a tiny hand-made match, so they run without the 400 MB raw data.
The last group checks the committed clips in clips/ (real DFL data).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tactics.data.clips import ClipSpec, build_clip, load_clip, load_clip_specs, match_clock, save_clip
from tactics.data.load import BALL_COLUMNS, PLAYER_COLUMNS, Match, Team, frame_at, get_frames, orient_home_left_to_right
from tactics.data.normalize import home_attacks_left_to_right, orient_for_team, rotate_180
from tactics.data.validate import find_problems, find_warnings, players_per_team

CLIPS_DIR = Path(__file__).resolve().parents[1] / "clips"


def make_match() -> Match:
    """Four frames, one home goalkeeper and one away striker who is missing in frame 10002."""
    roster = pd.DataFrame([
        {"player_id": "H1", "team": "home", "player_name": "Home Keeper", "jersey": 1, "position": "Goalkeeper", "starting": True},
        {"player_id": "A9", "team": "away", "player_name": "Away Striker", "jersey": 9, "position": "Striker", "starting": True},
    ])
    tracking = pd.DataFrame({
        "period_id": [1, 1, 1, 1],
        "timestamp": pd.to_timedelta([0.0, 0.04, 0.08, 0.12], unit="s"),
        "frame_id": [10000, 10001, 10002, 10003],
        "ball_state": ["alive", "alive", "dead", "alive"],
        "ball_owning_team_id": ["T_H", "T_A", "T_A", None],
        "ball_x": [0.0, 1.0, 2.0, 3.0],
        "ball_y": [0.0, 0.5, 1.0, 1.5],
        "ball_z": [0.0, 0.0, 0.0, 0.0],
        "H1_x": [-50.0, -50.0, -50.0, -50.0],
        "H1_y": [0.0, 0.0, 0.0, 0.0],
        "A9_x": [10.0, 10.2, np.nan, 10.6],  # jogging at 5 m/s
        "A9_y": [5.0, 5.0, np.nan, 5.0],
    })
    home = Team("T_H", "Home FC", "home", "4-4-2")
    away = Team("T_A", "Away FC", "away", "4-3-3")
    return Match("TEST", 25.0, home, away, roster, tracking)


# --- normalize.py -----------------------------------------------------------

def test_rotate_180_flips_both_axes_and_twice_is_identity():
    df = pd.DataFrame({"x": [10.0, -3.0], "y": [5.0, 0.0], "z": [1.0, 2.0]})
    rotated = rotate_180(df)
    assert rotated["x"].tolist() == [-10.0, 3.0]
    assert rotated["y"].tolist() == [-5.0, 0.0]
    assert rotated["z"].tolist() == [1.0, 2.0]  # height is unchanged
    pd.testing.assert_frame_equal(rotate_180(rotated), df)
    assert df["x"].tolist() == [10.0, -3.0]  # input not modified


def test_home_attacks_left_to_right_uses_goalkeeper_side():
    assert home_attacks_left_to_right(-48.0) is True
    assert home_attacks_left_to_right(48.0) is False


def test_orient_for_team():
    players = pd.DataFrame({"x": [10.0], "y": [5.0]})
    ball = pd.DataFrame({"x": [1.0], "y": [2.0]})
    assert orient_for_team(players, ball, "home")[0]["x"].tolist() == [10.0]
    away_players, away_ball = orient_for_team(players, ball, "away")
    assert away_players["x"].tolist() == [-10.0] and away_ball["y"].tolist() == [-2.0]
    with pytest.raises(ValueError):
        orient_for_team(players, ball, "ball")


# --- load.py ----------------------------------------------------------------

def test_get_frames_returns_clean_long_tables():
    players, ball = get_frames(make_match(), 10001, 10002)

    assert list(players.columns) == PLAYER_COLUMNS
    assert list(ball.columns) == BALL_COLUMNS
    # Keeper in both frames, striker only in 10001 (his frame-10002 position is missing).
    assert players[["frame", "player_id"]].values.tolist() == [[10001, "A9"], [10001, "H1"], [10002, "H1"]]
    assert players["player_name"].tolist() == ["Away Striker", "Home Keeper", "Home Keeper"]
    assert ball["frame"].tolist() == [10001, 10002]
    assert ball["time_s"].tolist() == pytest.approx([0.04, 0.08])
    assert ball["alive"].tolist() == [True, False]
    assert ball["owning_team"].tolist() == ["away", "away"]


def test_get_frames_maps_unknown_ball_owner_to_missing():
    _, ball = get_frames(make_match(), 10003, 10003)
    assert ball["owning_team"].isna().all()


def test_frame_at_picks_nearest_frame():
    assert frame_at(make_match(), period=1, time_s=0.05) == 10001
    assert frame_at(make_match(), period=1, time_s=99.0) == 10003


def test_orient_home_left_to_right_flips_only_the_wrong_period():
    match = make_match()
    tracking = pd.concat([match.tracking, match.tracking.assign(
        period_id=2, frame_id=match.tracking["frame_id"] + 90000, H1_x=50.0, ball_x=7.0)], ignore_index=True)

    orient_home_left_to_right(tracking, match.roster)

    period1, period2 = tracking[tracking["period_id"] == 1], tracking[tracking["period_id"] == 2]
    assert (period1["H1_x"] == -50.0).all()  # already correct, unchanged
    assert (period2["H1_x"] == -50.0).all()  # keeper was on the right, now rotated
    assert (period2["ball_x"] == -7.0).all()
    assert period2["A9_y"].dropna().eq(-5.0).all()


# --- validate.py ------------------------------------------------------------

def test_find_problems_accepts_clean_data():
    players, ball = get_frames(make_match(), 10000, 10003)
    assert find_problems(players, ball) == []
    assert find_warnings(players) == []


def test_find_problems_flags_bad_data():
    players, ball = get_frames(make_match(), 10000, 10003)

    twelve = pd.concat([players[players["player_id"] == "H1"].assign(player_id=f"X{i}") for i in range(12)])
    assert any("more than 11 players" in p for p in find_problems(twelve, ball))

    far_away = players.assign(x=players["x"].where(players["player_id"] != "A9", 70.0))
    assert any("outside the pitch" in p for p in find_problems(far_away, ball))

    jump = players.assign(x=players["x"].where(~((players["player_id"] == "A9") & (players["frame"] == 10003)), 30.0))
    assert find_problems(jump, ball) == []  # a tracking jump alone does not make data unusable...
    assert any("faster than" in w for w in find_warnings(jump))  # ...but it is reported: 19.8 m in 0.08 s

    gap = ball[ball["frame"] != 10001]
    assert any("not consecutive" in p for p in find_problems(players[players["frame"] != 10001], gap))

    # A new period restarts the frame numbers: that is not a gap.
    second_half = ball.assign(period=2, frame=ball["frame"] + 90000)
    assert find_problems(players, pd.concat([ball, second_half], ignore_index=True)) == []

    assert find_problems(players.drop(columns="x"), ball) == ["missing columns: ['x']"]


# --- clips.py ---------------------------------------------------------------

def test_match_clock():
    assert match_clock(1, 469.8) == "7:49"
    assert match_clock(2, 2595.3) == "88:15"


def test_clip_build_save_load_roundtrip(tmp_path):
    spec = ClipSpec("test-clip", "TEST", "A test clip", period=1, start_s=0.0, end_s=0.12, focus_team="away")
    goals = pd.DataFrame({"period": [1, 1, 2], "time_s": [0.1, 5.0, 0.1], "team": ["away"] * 3, "player": ["In", "Late", "Other half"]})
    clip = build_clip(make_match(), spec, goals)
    assert clip.meta["goals"] == [{"time_s": 0.1, "clock": "0:00", "team": "away", "player": "In"}]

    # Away is the focus team, so the clip is rotated: the home keeper ends up on the right.
    assert (clip.players.loc[clip.players["player_id"] == "H1", "x"] == 50.0).all()
    assert clip.meta["teams"]["away"] == {"name": "Away FC", "formation": "4-3-3"}

    loaded = load_clip(save_clip(clip, tmp_path))
    assert loaded.meta == clip.meta
    pd.testing.assert_frame_equal(loaded.players, clip.players)
    pd.testing.assert_frame_equal(loaded.ball, clip.ball)


def test_clip_specs_file_is_valid():
    specs = load_clip_specs(CLIPS_DIR / "clips.toml")
    assert len(specs) >= 1
    for spec in specs:
        assert spec.focus_team in ("home", "away")
        assert spec.start_s < spec.end_s


# --- committed clips (real DFL data) ----------------------------------------

COMMITTED_CLIPS = sorted(p.parent for p in CLIPS_DIR.glob("*/meta.json"))


@pytest.mark.parametrize("folder", COMMITTED_CLIPS, ids=lambda p: p.name)
def test_committed_clip_is_clean(folder):
    clip = load_clip(folder)
    assert find_problems(clip.players, clip.ball) == []
    counts = players_per_team(clip.players)
    assert counts["max"].le(11).all() and counts["min"].ge(7).all()  # 7 is the legal minimum
    assert "CC-BY 4.0" in clip.meta["source"]


@pytest.mark.parametrize("folder", COMMITTED_CLIPS, ids=lambda p: p.name)
def test_committed_clip_focus_team_attacks_left_to_right(folder):
    clip = load_clip(folder)
    focus = clip.meta["focus_team"]
    keepers = clip.players[clip.players["position"] == "Goalkeeper"]
    own_keeper_x = keepers.loc[keepers["team"] == focus, "x"].mean()
    other_keeper_x = keepers.loc[keepers["team"] != focus, "x"].mean()
    assert own_keeper_x < other_keeper_x
    assert other_keeper_x > 35  # the defending keeper stands near the right-hand goal
