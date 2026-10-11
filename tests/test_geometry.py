"""Geometry tests: known inputs, exact expected outputs."""

import numpy as np
import pandas as pd
import pytest

from tactics.geometry.formation import (
    FORMATIONS, average_positions, detect_formation, formation_template, line_name, line_sizes,
    match_formation, normalize_shape, template_lines,
)
from tactics.geometry.links import line_links
from tactics.geometry.shape import (
    centroid, defensive_line_height, depth, hull_area, hull_vertices, shape_over_time, stretch_index,
    team_shape, width,
)

SQUARE = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])


# --- shape.py ---------------------------------------------------------------

def test_hull_area_of_known_shapes():
    assert hull_area(SQUARE) == pytest.approx(100.0)
    assert hull_area([[0, 0], [4, 0], [0, 3]]) == pytest.approx(6.0)  # right triangle 4 x 3
    # A point inside the square does not change the hull.
    assert hull_area(np.vstack([SQUARE, [[5.0, 5.0]]])) == pytest.approx(100.0)


def test_hull_area_is_zero_without_an_area():
    assert hull_area([[0, 0], [1, 1]]) == 0.0  # two points
    assert hull_area([[0, 0], [1, 1], [2, 2]]) == 0.0  # all on one line


def test_hull_vertices():
    vertices = hull_vertices(np.vstack([SQUARE, [[5.0, 5.0]]]))
    assert sorted(map(tuple, vertices)) == sorted(map(tuple, SQUARE))
    assert hull_vertices([[0, 0], [1, 1]]).shape == (0, 2)


def test_width_depth_centroid_stretch():
    points = np.array([[-20.0, -10.0], [0.0, 15.0], [10.0, 0.0]])
    assert width(points) == 25.0
    assert depth(points) == 30.0
    np.testing.assert_allclose(centroid(SQUARE), [5.0, 5.0])
    assert stretch_index(SQUARE) == pytest.approx(5 * np.sqrt(2))  # centre to each corner


def test_defensive_line_height_depends_on_direction():
    assert defensive_line_height([[-30.0, 0.0], [-10.0, 5.0]], attacking_right=True) == 22.5
    assert defensive_line_height([[30.0, 0.0], [10.0, 5.0]], attacking_right=False) == 22.5


def test_team_shape_combines_metrics():
    m = team_shape(SQUARE, attacking_right=True)
    assert (m.width_m, m.depth_m, m.hull_area_m2) == (10.0, 10.0, pytest.approx(100.0))
    assert m.line_height_m == 52.5  # deepest player at x = 0
    assert (m.centroid_x, m.centroid_y) == (5.0, 5.0)


def test_shape_over_time_ignores_goalkeepers():
    rows = [{"frame": f, "team": "home", "player_id": f"P{i}", "position": "Midfield", "x": x + f, "y": y}
            for f in (1, 2) for i, (x, y) in enumerate(SQUARE)]
    rows += [{"frame": f, "team": "home", "player_id": "GK", "position": "Goalkeeper", "x": -50.0, "y": 0.0}
             for f in (1, 2)]
    rows += [{"frame": 1, "team": "away", "player_id": "A1", "position": "Striker", "x": 40.0, "y": 30.0}]

    result = shape_over_time(pd.DataFrame(rows), "home", attacking_right=True)

    assert result["frame"].tolist() == [1, 2]
    assert result["depth_m"].tolist() == [10.0, 10.0]  # keeper at -50 would make it 60+
    assert result["line_height_m"].tolist() == [53.5, 54.5]  # the square moves 1 m forward per frame


# --- formation.py -----------------------------------------------------------

def test_templates_have_ten_players_and_matching_lines():
    for name in FORMATIONS:
        template = formation_template(name)
        assert template.shape == (10, 2), name
        assert sum(line_sizes(name)) == 10
        assert list(np.bincount(template_lines(name))) == line_sizes(name)
        assert template[:, 0].min() == 0.0 and template[:, 0].max() == 1.0


def test_every_template_is_recognised_from_its_own_shape():
    rng = np.random.default_rng(0)
    for name in FORMATIONS:
        # Stretch the template to pitch size, shuffle the players and add 0.5 m of noise.
        shape = formation_template(name) * [40.0, 50.0] + [-30.0, -25.0]
        shape = rng.permutation(shape) + rng.normal(0, 0.5, shape.shape)
        assert match_formation(shape).formation == name


def test_match_formation_assigns_lines():
    shape = formation_template("4-2-3-1") * [40.0, 50.0]
    result = match_formation(shape)
    assert result.formation == "4-2-3-1"
    assert result.cost == pytest.approx(0.0, abs=1e-12)
    assert list(result.lines) == [0, 0, 0, 0, 1, 1, 2, 2, 2, 3]
    assert result.ranking[0] == ("4-2-3-1", result.cost)
    assert len(result.ranking) == len(FORMATIONS)


def test_normalize_shape_fills_unit_box():
    normalized = normalize_shape([[10.0, -5.0], [30.0, 5.0], [20.0, 0.0]])
    np.testing.assert_allclose(normalized, [[0, 0], [1, 1], [0.5, 0.5]])


def test_line_names():
    assert [line_name(i, 4) for i in range(4)] == ["defence", "midfield", "midfield", "attack"]


def formation_frames(name: str, attacking_right: bool, frames: int = 3) -> pd.DataFrame:
    """A team standing in `name` (plus a goalkeeper) for a few frames."""
    shape = formation_template(name) * [40.0, 50.0] + [-30.0, -25.0]
    if not attacking_right:
        shape = -shape  # same formation, mirrored to attack the other way
    rows = [{"frame": f, "team": "away", "player_id": f"P{i:02d}", "position": "Midfield", "x": x, "y": y}
            for f in range(frames) for i, (x, y) in enumerate(shape)]
    rows += [{"frame": f, "team": "away", "player_id": "GK", "position": "Goalkeeper",
              "x": -50.0 if attacking_right else 50.0, "y": 0.0} for f in range(frames)]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("attacking_right", [True, False])
def test_detect_formation_handles_both_directions(attacking_right):
    result, positions = detect_formation(formation_frames("3-5-2", attacking_right), "away", attacking_right)
    assert result.formation == "3-5-2"
    assert len(positions) == 10 and "GK" not in set(positions["player_id"])
    assert positions["line"].value_counts().sort_index().tolist() == [3, 5, 2]


def test_average_positions_drops_brief_substitutes():
    players = formation_frames("4-4-2", attacking_right=True, frames=10)
    late_sub = {"frame": 9, "team": "away", "player_id": "SUB", "position": "Striker", "x": 0.0, "y": 0.0}
    players = pd.concat([players, pd.DataFrame([late_sub])], ignore_index=True)
    assert "SUB" not in set(average_positions(players, "away", attacking_right=True)["player_id"])


# --- links.py ---------------------------------------------------------------

def test_line_links_join_neighbours_across_the_pitch():
    positions = pd.DataFrame({
        "player_id": ["LB", "RB", "CB1", "CB2", "ST", "GK"],
        "x": [-20.0, -20.0, -25.0, -25.0, 10.0, -50.0],
        "y": [30.0, -30.0, -10.0, 10.0, 0.0, 0.0],
    })
    lines = {"LB": 0, "RB": 0, "CB1": 0, "CB2": 0, "ST": 1}  # no entry for the keeper

    segments = line_links(positions, lines)

    # Back four ordered by y: RB -> CB1 -> CB2 -> LB; the lone striker has no partner.
    assert segments == [((-20.0, -30.0), (-25.0, -10.0)), ((-25.0, -10.0), (-25.0, 10.0)),
                        ((-25.0, 10.0), (-20.0, 30.0))]
