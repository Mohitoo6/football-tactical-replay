"""Sanity checks for clean player and ball tables."""

import pandas as pd

from tactics.data.load import BALL_COLUMNS, PLAYER_COLUMNS

HALF_LENGTH_M = 52.5
HALF_WIDTH_M = 34.0
# Players and the ball really do leave the pitch (throw-ins, run-offs, celebrations).
# The Phase 0 spike saw up to ~4 m outside the lines over a full match.
OUTSIDE_MARGIN_M = 5.0
MAX_PLAYERS_PER_TEAM = 11


def find_problems(players: pd.DataFrame, ball: pd.DataFrame) -> list[str]:
    """Return a list of human-readable problems. An empty list means the data looks clean."""
    missing = set(PLAYER_COLUMNS) - set(players.columns) | set(BALL_COLUMNS) - set(ball.columns)
    if missing:
        return [f"missing columns: {sorted(missing)}"]

    problems = []
    if players[["x", "y"]].isna().any().any():
        problems.append("players table has missing x/y values")
    if ball[["x", "y"]].isna().any().any():
        problems.append(f"ball position missing in {ball['x'].isna().sum()} frames")

    counts = players.groupby(["frame", "team"]).size()
    if (counts > MAX_PLAYERS_PER_TEAM).any():
        problems.append(f"more than {MAX_PLAYERS_PER_TEAM} players in {int((counts > MAX_PLAYERS_PER_TEAM).sum())} frame/team pairs")

    outside = _outside_pitch(players)
    if outside.any():
        problems.append(f"{int(outside.sum())} player positions more than {OUTSIDE_MARGIN_M} m outside the pitch")
    outside_ball = _outside_pitch(ball) & ball["alive"]
    if outside_ball.any():
        problems.append(f"ball in play but more than {OUTSIDE_MARGIN_M} m outside the pitch in {int(outside_ball.sum())} frames")

    if not set(players["frame"]).issubset(set(ball["frame"])):
        problems.append("some player frames have no ball row")
    if ball["frame"].diff().dropna().ne(1).any():
        problems.append("ball frames are not consecutive")
    return problems


def players_per_team(players: pd.DataFrame) -> pd.DataFrame:
    """Min and max number of players on the pitch per team across all frames."""
    return players.groupby(["frame", "team"]).size().groupby("team").agg(["min", "max"])


def _outside_pitch(df: pd.DataFrame) -> pd.Series:
    return (df["x"].abs() > HALF_LENGTH_M + OUTSIDE_MARGIN_M) | (df["y"].abs() > HALF_WIDTH_M + OUTSIDE_MARGIN_M)
