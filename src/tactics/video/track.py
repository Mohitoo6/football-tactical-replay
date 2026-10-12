"""Give each detected player one identity across frames (a simple, explainable tracker).

Detections are points in pitch metres. For every frame:
1. Predict where each live track should be now (last position + last velocity).
2. Pair predictions with detections one-to-one at the lowest total cost
   (Hungarian). Cost = distance in metres + `colour_weight` x shirt-colour
   difference, so two players of different teams passing close to each other
   are less likely to swap identities. Pairs further apart than
   `max_distance_m` are never matched.
3. Matched tracks move to their detection; unmatched detections start new
   tracks; tracks unmatched for longer than `max_missing_frames` end.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


COLOUR_SCALE = 40.0  # Lab units; the two teams' shirts differ by roughly this much
COLOUR_MEMORY = 0.1  # how fast a track's remembered colour follows new detections


@dataclass
class _Track:
    track_id: int
    position: np.ndarray
    colour: np.ndarray | None = None
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    missing: int = 0


class PointTracker:
    def __init__(self, max_distance_m: float = 1.5, max_missing_frames: int = 15, colour_weight: float = 0.0):
        self.max_distance = max_distance_m
        self.colour_weight = colour_weight
        self.max_missing = max_missing_frames  # 15 frames = 0.5 s at 30 fps
        self.tracks: list[_Track] = []
        self.next_id = 0

    def update(self, points: np.ndarray, colours: np.ndarray | None = None) -> np.ndarray:
        """Track ids for this frame's detections (same order as `points`); `colours` are Lab shirt colours."""
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        ids = np.full(len(points), -1)
        predicted = np.array([t.position + t.velocity * (t.missing + 1) for t in self.tracks]).reshape(-1, 2)
        if len(self.tracks) and len(points):
            distances = np.linalg.norm(predicted[:, None] - points[None], axis=2)
            cost = distances.copy()
            if colours is not None and self.colour_weight:
                remembered = np.array([t.colour for t in self.tracks])
                cost += self.colour_weight * np.linalg.norm(remembered[:, None] - colours[None], axis=2) / COLOUR_SCALE
            rows, cols = linear_sum_assignment(cost)
            for row, col in zip(rows, cols):
                if distances[row, col] <= self.max_distance:
                    track = self.tracks[row]
                    track.velocity = (points[col] - track.position) / (track.missing + 1)
                    track.position, track.missing = points[col], 0
                    if colours is not None:
                        track.colour = (1 - COLOUR_MEMORY) * track.colour + COLOUR_MEMORY * colours[col]
                    ids[col] = track.track_id
        for track in self.tracks:
            if track.track_id not in ids:
                track.missing += 1
        self.tracks = [t for t in self.tracks if t.missing <= self.max_missing]
        for col in np.flatnonzero(ids == -1):
            self.tracks.append(_Track(self.next_id, points[col], None if colours is None else colours[col].copy()))
            ids[col] = self.next_id
            self.next_id += 1
        return ids


def lab_colours(detections: pd.DataFrame) -> np.ndarray:
    """Mean blob colours (columns b, g, r) in Lab, where distances match how different colours look."""
    import cv2

    bgr = detections[["b", "g", "r"]].to_numpy().round().clip(0, 255).astype(np.uint8).reshape(-1, 1, 3)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)


def track_points(detections: pd.DataFrame, tracker: PointTracker | None = None) -> pd.DataFrame:
    """Add a `track_id` column to detections (columns frame, x_m, y_m; optional b, g, r), in frame order."""
    tracker = tracker or PointTracker()
    detections = detections.sort_values("frame")
    colours = lab_colours(detections) if {"b", "g", "r"} <= set(detections.columns) else None
    out = []
    for frame, index in detections.groupby("frame", sort=True).indices.items():
        group = detections.iloc[index]
        ids = tracker.update(group[["x_m", "y_m"]].to_numpy(), None if colours is None else colours[index])
        out.append(group.assign(track_id=ids))
    return pd.concat(out, ignore_index=True)


def stitch_tracks(tracks: pd.DataFrame, max_gap_frames: int = 60, max_speed_mps: float = 8.0, fps: float = 29.97,
                  colour_weight: float = 2.0) -> pd.DataFrame:
    """Join a track that ends to one that starts soon after, close by and in a similar shirt colour.

    Works offline on the whole clip (we know the future), so broken tracks after a
    collision can be repaired. The gap a player can cover grows with the time gap.
    """
    tracks = tracks.copy()
    colours = pd.DataFrame(lab_colours(tracks), index=tracks.index, columns=["L", "A", "B"])
    tracks = tracks.join(colours)
    while True:
        summary = tracks.sort_values("frame").groupby("track_id").agg(
            start=("frame", "first"), end=("frame", "last"),
            x0=("x_m", "first"), y0=("y_m", "first"), x1=("x_m", "last"), y1=("y_m", "last"),
            L=("L", "mean"), A=("A", "mean"), B=("B", "mean"))
        ends, starts = summary, summary
        gap = starts["start"].to_numpy()[None] - ends["end"].to_numpy()[:, None]
        distance = np.hypot(starts["x0"].to_numpy()[None] - ends["x1"].to_numpy()[:, None],
                            starts["y0"].to_numpy()[None] - ends["y1"].to_numpy()[:, None])
        colour = np.linalg.norm(ends[["L", "A", "B"]].to_numpy()[:, None] - starts[["L", "A", "B"]].to_numpy()[None], axis=2)
        reachable = (gap > 0) & (gap <= max_gap_frames) & (distance <= 1.0 + max_speed_mps * gap / fps)
        cost = np.where(reachable, distance + colour_weight * colour / COLOUR_SCALE, np.inf)
        if not np.isfinite(cost).any():
            break
        rows, cols = linear_sum_assignment(np.where(np.isfinite(cost), cost, 1e9))
        links = [(summary.index[c], summary.index[r]) for r, c in zip(rows, cols) if np.isfinite(cost[r, c])]
        if not links:
            break
        mapping = dict(links)
        # Follow chains so each later track takes its earliest ancestor's id.
        def root(track_id):
            while track_id in mapping:
                track_id = mapping[track_id]
            return track_id
        tracks["track_id"] = tracks["track_id"].map(lambda t: root(t))
    return tracks.drop(columns=["L", "A", "B"])


def assign_teams(tracks: pd.DataFrame, min_frames: int = 30) -> pd.Series:
    """Team label per track_id ("A", "B" or "other") from shirt colour.

    Tracks are grouped into three colour clusters (k-means, weighted by length);
    the two clusters with the most player-frames are the teams, the third is
    everyone else (referee, staff, noise). Short tracks are "other".
    """
    import cv2

    colours = pd.DataFrame(lab_colours(tracks), index=tracks.index, columns=["L", "A", "B"])
    per_track = tracks.join(colours).groupby("track_id").agg(L=("L", "mean"), A=("A", "mean"), B=("B", "mean"),
                                                              frames=("frame", "size"))
    long = per_track[per_track["frames"] >= min_frames]
    data = np.repeat(long[["L", "A", "B"]].to_numpy(np.float32), np.ceil(long["frames"] / 30).astype(int), axis=0)
    _, _, centres = cv2.kmeans(data, 3, None, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 100, 0.1), 10,
                               cv2.KMEANS_PP_CENTERS)
    nearest = np.linalg.norm(long[["L", "A", "B"]].to_numpy()[:, None] - centres[None], axis=2).argmin(axis=1)
    weight = pd.Series(long["frames"].to_numpy()).groupby(nearest).sum().sort_values(ascending=False)
    names = {cluster: name for cluster, name in zip(weight.index, ["A", "B", "other"])}
    teams = pd.Series("other", index=per_track.index)
    teams.loc[long.index] = [names.get(c, "other") for c in nearest]
    return teams


def fix_goalkeepers(tracks: pd.DataFrame, teams: pd.Series, min_share: float = 0.5, colour_gap: float = 20.0) -> pd.Series:
    """Give each goalkeeper the right team.

    Keepers wear a different colour from their team, so the colour clusters put
    them in the wrong group. We find them, then use the offside logic of football.
    1. Candidates: long tracks whose shirt colour is far from their own team's
       average colour (keepers, and the referee).
    2. Per half, the candidate standing deepest on average is that goal's keeper
       (the referee stays nearer the middle).
    3. Towards a goal, the deepest outfield player almost always belongs to the
       team defending it (attackers cannot stand beyond the last defender), so
       the keeper joins that team.
    """
    teams = teams.copy()
    colours = pd.DataFrame(lab_colours(tracks), index=tracks.index, columns=["L", "A", "B"])
    data = tracks.join(colours).assign(team=tracks["track_id"].map(teams))
    per_track = data.groupby("track_id").agg(x=("x_m", "mean"), length=("frame", "size"),
                                             L=("L", "mean"), A=("A", "mean"), B=("B", "mean"), team=("team", "first"))
    centres = data[data["team"].isin(["A", "B"])].groupby("team")[["L", "A", "B"]].mean()
    if len(centres) < 2:
        return teams
    long = per_track[per_track["length"] >= min_share * data["frame"].nunique()]
    medians = data.groupby("track_id")[["x_m", "y_m"]].median().abs()
    # A keeper stays on the pitch and roughly within the penalty-area width, not behind the goal line.
    on_pitch = (medians["x_m"] <= 53.5) & (medians["y_m"] <= 20.16)
    long = long[on_pitch.reindex(long.index)]
    own_centre = centres.reindex(long["team"]).to_numpy()
    gap = np.linalg.norm(long[["L", "A", "B"]].to_numpy() - own_centre, axis=1)
    candidates = long[(gap > colour_gap) | ~long["team"].isin(["A", "B"])]

    outfield = data[data["team"].isin(["A", "B"]) & ~data["track_id"].isin(candidates.index)]
    teams.attrs["keepers"] = {}
    for side in (1, -1):
        here = candidates[candidates["x"] * side > 0]
        if here.empty:
            continue
        keeper = (here["x"] * side).idxmax()
        teams.attrs["keepers"][side] = keeper
        deepest = (outfield.assign(depth=outfield["x_m"] * side)
                   .groupby(["frame", "team"])["depth"].max().unstack())
        defending = (deepest["A"] > deepest["B"]).mean()  # share of frames team A has the deepest player
        teams.loc[keeper] = "A" if defending > 0.5 else "B"
    return teams


def officials(tracks: pd.DataFrame, touchline_y_m: float = 34.0, margin_m: float = 2.0) -> list:
    """Track ids that never come more than `margin_m` inside a touchline: assistant referees.

    They run along one touchline for the whole clip and wear dark kit, so they
    look like players. Remove them *after* assigning teams: removing them first
    left k-means without a natural third ("other") group, and team accuracy fell
    from 99.6% to 86.0% on one segment.
    """
    closest = tracks.groupby("track_id")["y_m"].agg(lambda y: y.abs().min())
    return closest[closest >= touchline_y_m - margin_m].index.tolist()
