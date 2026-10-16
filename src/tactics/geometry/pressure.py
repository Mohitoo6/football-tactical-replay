"""Measures around the ball: how hard the ball carrier is pressed and how many players each team has nearby.

Broadcast cameras follow the ball, so the area around it is the part of the game we see best.
These are the measures used for partial-view clips (DECISIONS.md, D29). All positions are pitch
metres with the origin at the centre spot.
"""

import numpy as np

NEAR_BALL_M = 15.0  # "around the ball": a radius that covers the players who can join the play quickly


def nearest_opponent_m(carrier: np.ndarray, opponents: np.ndarray) -> float:
    """Distance from the ball carrier to the closest opponent (the pressure on the ball); inf with no opponent."""
    opponents = np.asarray(opponents, dtype=float).reshape(-1, 2)
    if len(opponents) == 0:
        return float("inf")
    return float(np.linalg.norm(opponents - np.asarray(carrier, dtype=float), axis=1).min())


def players_within(points: np.ndarray, ball: np.ndarray, radius: float = NEAR_BALL_M) -> int:
    """How many of these players are within `radius` metres of the ball."""
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    return int((np.linalg.norm(points - np.asarray(ball, dtype=float), axis=1) <= radius).sum())


def progress_m(start_x: float, end_x: float, attacking_right: bool) -> float:
    """Metres the ball moved towards the goal a team attacks (negative: backwards)."""
    return float((end_x - start_x) if attacking_right else (start_x - end_x))
