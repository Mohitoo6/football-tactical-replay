"""Score the video pipeline against SoccerTrack ground truth (evaluation only, never used to build clips).

The pipeline works in its own pitch metres (automatic calibration). To compare
with the dataset, we express both our detections and the ground-truth boxes in
the dataset's metres, through the same stabilised reference pixels.
"""

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from tactics.video.calibration import PitchCalibration
from tactics.video.detect import Stabilizer
from tactics.video.evaluate import combine, identity_metrics, match

MATCH_RADIUS_M = 1.5


def truth_in_dataset_metres(boxes: pd.DataFrame, warps: np.ndarray, dataset: PitchCalibration) -> pd.DataFrame:
    """Ground-truth boxes -> frame (0-based), truth_id, x, y in dataset metres, via the same reference frame."""
    rows = []
    for frame, warp in enumerate(warps):
        real = boxes[boxes["frame"] == frame + 1]  # annotation frames start at 1
        if real.empty:
            continue
        xy = dataset.to_pitch(Stabilizer.to_reference(real[["cx", "cy"]].to_numpy(), warp))
        rows.append(pd.DataFrame({"frame": frame, "truth_id": (real["team"] + "-" + real["player_id"]).to_numpy(),
                                  "x": xy[:, 0], "y": xy[:, 1]}))
    return pd.concat(rows, ignore_index=True)


def in_dataset_metres(table: pd.DataFrame, dataset: PitchCalibration) -> pd.DataFrame:
    """Add x, y (dataset metres) from the reference pixels px, py."""
    xy = dataset.to_pitch(table[["px", "py"]].to_numpy())
    return table.assign(x=xy[:, 0], y=xy[:, 1])


def detection_scores(players: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Detections in *our* metres vs the truth, under the best of the pitch's mirror symmetries."""
    best = None
    for mirror in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        results = [match(players.loc[players["frame"] == frame, ["x_m", "y_m"]].to_numpy() * mirror,
                         real[["x", "y"]].to_numpy(), MATCH_RADIUS_M) for frame, real in truth.groupby("frame")]
        total = combine(results)
        if best is None or total.true_positives > best.true_positives:
            best = total
    return {"recall": best.recall, "precision": best.precision, "error_m": float(best.errors.mean()),
            "error_p90_m": float(np.percentile(best.errors, 90))}


def tracking_scores(tracks: pd.DataFrame, truth: pd.DataFrame, fps: float) -> dict:
    """Identity metrics for tracks with x, y in dataset metres."""
    m = identity_metrics(tracks[["frame", "track_id", "x", "y"]], truth, MATCH_RADIUS_M, fps)
    return {"coverage": m["coverage"], "purity": m["mean_purity"], "id_switches": m["id_switches"],
            "tracks_created": m["tracks_created"]}


def team_correct(tracks: pd.DataFrame, truth: pd.DataFrame) -> float:
    """Share of matched player-frames whose team label agrees with the truth (best of the two label mappings)."""
    pairs = []
    for frame, real in truth.groupby("frame"):
        found = tracks[tracks["frame"] == frame]
        if found.empty:
            continue
        d = np.linalg.norm(found[["x", "y"]].to_numpy()[:, None] - real[["x", "y"]].to_numpy()[None], axis=2)
        rows, cols = linear_sum_assignment(d)
        pairs += [(found["team"].iloc[r], real["truth_id"].iloc[c][0]) for r, c in zip(rows, cols) if d[r, c] <= MATCH_RADIUS_M]
    p = pd.DataFrame(pairs, columns=["ours", "truth"])
    straight = ((p.ours == "A") & (p.truth == "0")).sum() + ((p.ours == "B") & (p.truth == "1")).sum()
    swapped = ((p.ours == "A") & (p.truth == "1")).sum() + ((p.ours == "B") & (p.truth == "0")).sum()
    return float(max(straight, swapped) / len(p)) if len(p) else 0.0


def ball_scores(ball: pd.DataFrame, ball_truth: pd.DataFrame) -> dict:
    """ball: frame, x, y in dataset metres for frames where we give a position."""
    merged = ball_truth.merge(ball, on="frame", how="left", suffixes=("", "_ours"))
    error = np.hypot(merged["x"] - merged["x_ours"], merged["y"] - merged["y_ours"])
    given = error.notna()
    return {"ball_given": float(given.mean()), "ball_correct_when_given": float((error <= 1.0).sum() / max(given.sum(), 1)),
            "ball_correct": float((error <= 1.0).mean())}
