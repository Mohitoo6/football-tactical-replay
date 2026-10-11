"""Detect a team's formation by matching its average shape to standard templates (DECISIONS.md, D8).

How it works:
1. Average each outfield player's position over a time window, oriented so
   the team attacks towards +x (so small x = defence, large x = attack).
2. Rescale that shape to a 0..1 box, so only the arrangement matters, not
   how high or wide the team stands.
3. For every template (e.g. "4-2-3-1" as ten dots), pair each player with
   one dot so the total squared distance is as small as possible (the
   Hungarian algorithm, scipy's `linear_sum_assignment`).
4. The template with the smallest average distance wins. The pairing also
   tells us which line (defence / midfield / attack) each player is in.
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from tactics.geometry.shape import outfield

FORMATIONS = [
    "4-4-2", "4-3-3", "4-2-3-1", "4-1-4-1", "4-4-1-1", "4-3-2-1",
    "4-1-2-1-2", "3-5-2", "3-4-3", "5-3-2", "5-4-1",
]
# A player must be on the pitch for at least this share of the window to count
# (so a substitute who came on in the last minute does not distort the shape).
MIN_SHARE_OF_FRAMES = 0.5


def base_formation(label: str | None) -> str | None:
    """Strip extra words from an official label: "4-3-3 Double-6" -> "4-3-3"."""
    found = re.search(r"\d(?:-\d)+", label or "")
    return found.group(0) if found else None


def line_sizes(formation: str) -> list[int]:
    """Players per line from back to front, e.g. "4-2-3-1" -> [4, 2, 3, 1]."""
    return [int(n) for n in formation.split("-")]


def formation_template(formation: str) -> np.ndarray:
    """Ten (x, y) dots in a 0..1 box: lines evenly spaced from back (x=0) to front (x=1).

    Within a line, players are spread evenly across the width; lines with more
    players spread wider (a lone striker sits in the middle).
    """
    sizes = line_sizes(formation)
    dots = []
    for line_x, n in zip(np.linspace(0, 1, len(sizes)), sizes):
        spread = min(0.9, 0.3 * (n - 1))
        for y in np.linspace(0.5 - spread / 2, 0.5 + spread / 2, n):
            dots.append((line_x, y))
    return np.array(dots)


def template_lines(formation: str) -> np.ndarray:
    """Line index (0 = defence) for each dot of `formation_template`."""
    return np.repeat(np.arange(len(line_sizes(formation))), line_sizes(formation))


def line_name(line: int, n_lines: int) -> str:
    """Readable name for a line index: defence, midfield or attack."""
    if line == 0:
        return "defence"
    if line == n_lines - 1:
        return "attack"
    return "midfield"


def normalize_shape(points: np.ndarray) -> np.ndarray:
    """Rescale x and y separately so the points fill a 0..1 box."""
    points = np.asarray(points, dtype=float)
    low, high = points.min(axis=0), points.max(axis=0)
    span = np.where(high - low > 0, high - low, 1.0)
    return (points - low) / span


@dataclass
class FormationResult:
    formation: str
    cost: float  # mean squared distance between players and their template dots (0..1 box units)
    lines: np.ndarray  # line index for each input player, 0 = defence
    ranking: list[tuple[str, float]]  # every candidate with its cost, best first


def match_formation(points: np.ndarray, candidates: list[str] = FORMATIONS) -> FormationResult:
    """Find the template closest to `points` (outfield average positions, team attacking towards +x)."""
    shape = normalize_shape(points)
    results = []
    for name in candidates:
        # Rescale the template the same way, so both fill the same 0..1 box.
        template = normalize_shape(formation_template(name))
        cost_matrix = ((shape[:, None, :] - template[None, :, :]) ** 2).sum(axis=2)
        players, dots = linear_sum_assignment(cost_matrix)
        lines = np.empty(len(shape), dtype=int)
        lines[players] = template_lines(name)[dots]
        results.append((float(cost_matrix[players, dots].mean()), name, lines))

    results.sort(key=lambda r: r[0])
    best_cost, best_name, best_lines = results[0]
    return FormationResult(best_name, best_cost, best_lines, [(name, cost) for cost, name, _ in results])


def average_positions(players: pd.DataFrame, team: str, attacking_right: bool) -> pd.DataFrame:
    """Average position of each regular outfield player of `team`, oriented to attack towards +x.

    Returns columns player_id, x, y, frames (how many frames the player appears in).
    """
    team_rows = outfield(players[players["team"] == team])
    n_frames = team_rows["frame"].nunique()
    avg = (team_rows.groupby("player_id")
           .agg(x=("x", "mean"), y=("y", "mean"), frames=("frame", "size"))
           .reset_index())
    avg = avg[avg["frames"] >= MIN_SHARE_OF_FRAMES * n_frames]
    avg = avg.nlargest(10, "frames").sort_values("player_id").reset_index(drop=True)
    if not attacking_right:
        # Rotate 180 degrees so this team also attacks towards +x (keeps left wing on the left).
        avg[["x", "y"]] = -avg[["x", "y"]]
    return avg


def formation_label(result: FormationResult, positions: pd.DataFrame) -> str:
    """Label to show for a detection; templates have 10 outfield players, so fewer (red card) gets "n/a"."""
    if len(positions) == 10:
        return result.formation
    return f"n/a, {len(positions)} outfield players"


def detect_formation(players: pd.DataFrame, team: str, attacking_right: bool) -> tuple[FormationResult, pd.DataFrame]:
    """Detect `team`'s formation over all frames in `players`.

    Returns the result and the average-position table with an added `line` column.
    """
    avg = average_positions(players, team, attacking_right)
    result = match_formation(avg[["x", "y"]].to_numpy())
    return result, avg.assign(line=result.lines)
