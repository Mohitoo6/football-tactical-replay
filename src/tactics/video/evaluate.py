"""Compare detected positions with ground truth: how many found, how many false, how far off."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


@dataclass
class MatchResult:
    true_positives: int
    false_positives: int
    false_negatives: int
    errors: np.ndarray  # distance of each matched pair (same units as the inputs)

    @property
    def recall(self) -> float:
        """Share of real players that were found."""
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total else 0.0

    @property
    def precision(self) -> float:
        """Share of detections that are real players."""
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total else 0.0


def match(detected: np.ndarray, truth: np.ndarray, max_distance: float) -> MatchResult:
    """Pair detections with true positions one-to-one (closest overall, Hungarian), within `max_distance`."""
    detected, truth = np.asarray(detected, dtype=float).reshape(-1, 2), np.asarray(truth, dtype=float).reshape(-1, 2)
    if len(detected) == 0 or len(truth) == 0:
        return MatchResult(0, len(detected), len(truth), np.empty(0))
    distances = np.linalg.norm(detected[:, None] - truth[None], axis=2)
    rows, cols = linear_sum_assignment(distances)
    close = distances[rows, cols] <= max_distance
    tp = int(close.sum())
    return MatchResult(tp, len(detected) - tp, len(truth) - tp, distances[rows, cols][close])


def combine(results: list[MatchResult]) -> MatchResult:
    """Add up per-frame results."""
    return MatchResult(
        sum(r.true_positives for r in results),
        sum(r.false_positives for r in results),
        sum(r.false_negatives for r in results),
        np.concatenate([r.errors for r in results]) if results else np.empty(0),
    )


def identity_metrics(tracks: pd.DataFrame, truth: pd.DataFrame, max_distance: float, fps: float) -> dict:
    """How well track ids follow real players.

    tracks: frame, track_id, x, y.  truth: frame, truth_id, x, y (same units).
    Each frame, tracks are matched one-to-one to real players (Hungarian, within max_distance).
    - coverage: share of real player-frames that have a matched track
    - id_switches: times a real player's matched track id changes
    - purity: share of a player's matched frames that carry its most common track id (1.0 = one id all along)
    """
    pairs = []
    for frame, real in truth.groupby("frame"):
        found = tracks[tracks["frame"] == frame]
        if found.empty:
            continue
        distances = np.linalg.norm(found[["x", "y"]].to_numpy()[:, None] - real[["x", "y"]].to_numpy()[None], axis=2)
        rows, cols = linear_sum_assignment(distances)
        for r, c in zip(rows, cols):
            if distances[r, c] <= max_distance:
                pairs.append((frame, real["truth_id"].iloc[c], found["track_id"].iloc[r]))
    matched = pd.DataFrame(pairs, columns=["frame", "truth_id", "track_id"]).sort_values(["truth_id", "frame"])
    switches = int((matched.groupby("truth_id")["track_id"].diff().fillna(0) != 0).sum())
    purity = matched.groupby("truth_id")["track_id"].agg(lambda ids: ids.value_counts().iloc[0] / len(ids))
    minutes = truth["frame"].nunique() / fps / 60
    return {
        "coverage": len(matched) / len(truth),
        "id_switches": switches,
        "switches_per_player_minute": switches / truth["truth_id"].nunique() / minutes,
        "mean_purity": float(purity.mean()),
        "tracks_created": int(tracks["track_id"].nunique()),
    }
