"""Compare detected positions with ground truth: how many found, how many false, how far off."""

from dataclasses import dataclass

import numpy as np
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
