"""Teams for broadcast clips: split tracks where the shirt colour changes, then label each piece.

At 5 frames per second and with players crossing in front of each other, the
tracker sometimes hands one identity from player to player. On the first
broadcast clip, one "track" was the referee, then a white-shirted player, then a
dark-shirted one (DECISIONS.md, D28). Its average colour was white, so all three
were drawn as the white team. A player cannot change team, so a change of shirt
colour along a track means the tracker swapped people. We cut the track there
and label each piece by its own colour.
"""

import numpy as np
import pandas as pd

from tactics.video.track import assign_teams, lab_colours

SMOOTH_DETECTIONS = 5  # rolling majority over this many detections, so one odd frame does not cut a track
MIN_PIECE = 3  # shorter pieces keep their neighbour's label
MAX_TEAM_DISTANCE_LAB = 40.0  # a piece further than this from both team colours is "other" (not a player)


def split_by_colour(tracks: pd.DataFrame, min_frames: int) -> tuple[pd.DataFrame, pd.Series]:
    """(tracks with new track ids, team per new id: "A", "B" or "other")."""
    teams = assign_teams(tracks, min_frames=min_frames)
    lab = lab_colours(tracks)
    labelled = tracks.assign(team=tracks["track_id"].map(teams).to_numpy())
    in_team = labelled["team"].isin(["A", "B"]).to_numpy()
    if not in_team.any():
        return tracks, teams
    centres = {t: np.median(lab[labelled["team"].to_numpy() == t], axis=0) for t in ("A", "B")}
    distance = np.column_stack([np.linalg.norm(lab - centres[t], axis=1) for t in ("A", "B")])
    labelled["own"] = np.where(distance[:, 0] <= distance[:, 1], 0, 1)
    labelled["far"] = distance.min(axis=1) > MAX_TEAM_DISTANCE_LAB

    pieces = []
    for track_id, group in labelled.sort_values("frame").groupby("track_id", sort=False):
        own = group["own"].rolling(SMOOTH_DETECTIONS, center=True, min_periods=1).mean().round().astype(int).to_numpy().copy()
        run = np.concatenate([[0], np.cumsum(own[1:] != own[:-1])])
        sizes = np.bincount(run)
        for r in np.flatnonzero(sizes < MIN_PIECE):  # too short to be a separate person: join a neighbour
            neighbour = r - 1 if r > 0 else r + 1
            if neighbour < len(sizes):
                own[run == r] = own[run == neighbour][0]
        run = np.concatenate([[0], np.cumsum(own[1:] != own[:-1])])
        pieces.append(group.assign(track_id=track_id * 1000 + run, own=own))
    split = pd.concat(pieces)

    per_piece = split.groupby("track_id").agg(own=("own", "first"), far=("far", "mean"), frames=("frame", "size"))
    new_teams = pd.Series(np.where(per_piece["own"] == 0, "A", "B"), index=per_piece.index)
    new_teams[(per_piece["far"] > 0.5) | (per_piece["frames"] < min_frames)] = "other"
    return split.drop(columns=["team", "own", "far"]).sort_values("frame"), new_teams
