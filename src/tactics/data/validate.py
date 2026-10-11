"""Sanity checks for clean player and ball tables."""

import pandas as pd

from tactics.data.load import BALL_COLUMNS, PLAYER_COLUMNS

HALF_LENGTH_M = 52.5
HALF_WIDTH_M = 34.0
# Players and the ball really do leave the pitch (throw-ins, run-offs, celebrations).
# The Phase 0 spike saw up to ~4 m outside the lines over a full match.
OUTSIDE_MARGIN_M = 5.0
MAX_PLAYERS_PER_TEAM = 11
# Top sprinters in football reach ~10 m/s (36 km/h); anything faster is a tracking jump.
MAX_PLAYER_SPEED_MS = 12.0


def find_problems(players: pd.DataFrame, ball: pd.DataFrame) -> list[str]:
    """Return a list of human-readable problems that make the data unusable. Empty means clean."""
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
    # Frame numbers restart at each period (e.g. 10000.. then 100000..), so check within periods.
    if ball.groupby("period")["frame"].diff().dropna().ne(1).any():
        problems.append("ball frames are not consecutive within a period")
    return problems


def find_warnings(players: pd.DataFrame, frame_rate: float = 25.0) -> list[str]:
    """Return small, tolerable issues worth knowing about (the data is still usable).

    The full Köln v Bayern match has 16 single-frame tracking jumps among 3.2 million
    player moves, mostly near the touchlines, so one jump should not reject a clip.
    """
    warnings = []
    too_fast = player_speeds(players, frame_rate) > MAX_PLAYER_SPEED_MS
    if too_fast.any():
        warnings.append(f"{int(too_fast.sum())} player moves faster than {MAX_PLAYER_SPEED_MS} m/s (tracking jumps)")
    return warnings


def players_per_team(players: pd.DataFrame) -> pd.DataFrame:
    """Min and max number of players on the pitch per team across all frames."""
    return players.groupby(["frame", "team"]).size().groupby("team").agg(["min", "max"])


def player_speeds(players: pd.DataFrame, frame_rate: float) -> pd.Series:
    """Each player's speed in m/s between consecutive appearances (NaN for the first)."""
    ordered = players.sort_values(["player_id", "frame"])
    grouped = ordered.groupby("player_id")
    metres = (grouped["x"].diff() ** 2 + grouped["y"].diff() ** 2) ** 0.5
    seconds = grouped["frame"].diff() / frame_rate
    return (metres / seconds).reindex(players.index)


def _outside_pitch(df: pd.DataFrame) -> pd.Series:
    return (df["x"].abs() > HALF_LENGTH_M + OUTSIDE_MARGIN_M) | (df["y"].abs() > HALF_WIDTH_M + OUTSIDE_MARGIN_M)
