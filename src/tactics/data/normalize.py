"""Make attacking direction consistent (see DECISIONS.md, D3).

Coordinates are metres with the pitch centre at (0, 0), x along the length
(-52.5..52.5) and y along the width (-34..34).
"""

import pandas as pd


def rotate_180(df: pd.DataFrame, x_col: str = "x", y_col: str = "y") -> pd.DataFrame:
    """Return a copy with every point rotated 180 degrees around the centre spot.

    Rotating (not just mirroring x) keeps each team's left wing on its left,
    so "the left side" still means the same thing after the flip.
    """
    out = df.copy()
    out[x_col] = -out[x_col]
    out[y_col] = -out[y_col]
    return out


def home_attacks_left_to_right(home_goalkeeper_x: float) -> bool:
    """Decide the home team's attacking direction from its goalkeeper's average x.

    A goalkeeper stands in front of his own goal, so a keeper on the left
    (negative x) means his team attacks towards the right.
    """
    return home_goalkeeper_x < 0


def orient_for_team(players: pd.DataFrame, ball: pd.DataFrame, team: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Orient a clip so that `team` ("home" or "away") attacks left to right.

    Expects data where the home team already attacks left to right
    (which is what `load.get_frames` returns).
    """
    if team == "home":
        return players, ball
    if team == "away":
        return rotate_180(players), rotate_180(ball)
    raise ValueError(f"team must be 'home' or 'away', got {team!r}")
