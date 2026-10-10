"""Load a DFL (Sportec) match into clean, standard tables.

The raw tracking file is large (~400 MB XML), so this is only used offline by
`scripts/build_clips.py`. The app and the tests read small clip files instead
(see DECISIONS.md, D2).
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from kloppy import sportec

from tactics.data.normalize import home_attacks_left_to_right

PLAYER_COLUMNS = ["frame", "period", "time_s", "team", "player_id", "player_name", "jersey", "position", "x", "y"]
BALL_COLUMNS = ["frame", "period", "time_s", "x", "y", "z", "alive", "owning_team"]


@dataclass
class Team:
    team_id: str
    name: str
    side: str  # "home" or "away"
    formation: str | None  # official starting formation, e.g. "4-2-3-1"


@dataclass
class Match:
    match_id: str
    frame_rate: float
    home: Team
    away: Team
    roster: pd.DataFrame  # one row per player: player_id, team, player_name, jersey, position, starting
    tracking: pd.DataFrame  # kloppy's wide table, metres, home attacking left to right in both periods

    def side_of(self, team_id: str) -> str | None:
        """Map a provider team id to "home" / "away"."""
        return {self.home.team_id: "home", self.away.team_id: "away"}.get(team_id)


def load_dfl_match(data_dir: Path, match_id: str) -> Match:
    """Load one DFL match (e.g. "J03WMX") from the raw files in `data_dir`."""
    meta_path = _find_file(data_dir, "matchinformation", match_id)
    raw_path = _find_file(data_dir, "positions_raw", match_id)

    # "secondspectrum" coordinates: metres, origin at the pitch centre.
    dataset = sportec.load_tracking(meta_data=meta_path, raw_data=raw_path, coordinates="secondspectrum")
    formations = read_dfl_formations(meta_path)

    teams: dict[str, Team] = {}
    roster_rows = []
    for team in dataset.metadata.teams:
        side = str(team.ground)
        teams[side] = Team(team.team_id, team.name, side, formations.get(team.team_id))
        for player in team.players:
            roster_rows.append({
                "player_id": player.player_id,
                "team": side,
                "player_name": player.name,
                "jersey": player.jersey_no,
                "position": str(player.starting_position) if player.starting_position else None,
                "starting": bool(player.starting),
            })
    roster = pd.DataFrame(roster_rows)

    tracking = dataset.to_df()
    orient_home_left_to_right(tracking, roster)

    return Match(match_id, dataset.metadata.frame_rate, teams["home"], teams["away"], roster, tracking)


def read_dfl_formations(meta_path: Path) -> dict[str, str]:
    """Read each team's official starting formation ("LineUp") from the match-information XML.

    kloppy does not expose this field, so we read it ourselves.
    """
    root = ET.parse(meta_path).getroot()
    return {team.get("TeamId"): team.get("LineUp") for team in root.iter("Team")}


def get_frames(match: Match, start_frame: int, end_frame: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return clean player and ball tables for frames `start_frame`..`end_frame` (inclusive).

    players: one row per player per frame (columns PLAYER_COLUMNS). Players who
             are not on the pitch in a frame (e.g. substitutes) have no row.
    ball:    one row per frame (columns BALL_COLUMNS).
    """
    wide = match.tracking[(match.tracking["frame_id"] >= start_frame) & (match.tracking["frame_id"] <= end_frame)]
    base = pd.DataFrame({
        "frame": wide["frame_id"].astype(int),
        "period": wide["period_id"].astype(int),
        "time_s": wide["timestamp"].dt.total_seconds(),
    })

    parts = []
    for p in match.roster.itertuples():
        if f"{p.player_id}_x" not in wide.columns:
            continue
        parts.append(base.assign(
            team=p.team,
            player_id=p.player_id,
            player_name=p.player_name,
            jersey=p.jersey,
            position=p.position,
            x=wide[f"{p.player_id}_x"],
            y=wide[f"{p.player_id}_y"],
        ))
    players = pd.concat(parts, ignore_index=True).dropna(subset=["x", "y"])
    players = players.sort_values(["frame", "team", "jersey"]).reset_index(drop=True)[PLAYER_COLUMNS]

    ball = base.assign(
        x=wide["ball_x"],
        y=wide["ball_y"],
        z=wide["ball_z"],
        alive=wide["ball_state"].astype(str) == "alive",
        owning_team=wide["ball_owning_team_id"].map(match.side_of),
    ).reset_index(drop=True)[BALL_COLUMNS]

    return players, ball


def frame_at(match: Match, period: int, time_s: float) -> int:
    """Return the frame closest to `time_s` seconds after the start of `period`."""
    rows = match.tracking[match.tracking["period_id"] == period]
    seconds = rows["timestamp"].dt.total_seconds()
    return int(rows["frame_id"].iloc[(seconds - time_s).abs().argmin()])


def orient_home_left_to_right(tracking: pd.DataFrame, roster: pd.DataFrame) -> None:
    """Rotate periods in place so the home team attacks left to right in every period.

    Teams switch ends at half-time, so we check each period separately using
    where the home goalkeeper stands.
    """
    keepers = roster[(roster["team"] == "home") & (roster["position"] == "Goalkeeper") & roster["starting"]]
    keeper_x = f"{keepers['player_id'].iloc[0]}_x"
    x_cols = [c for c in tracking.columns if c.endswith("_x")]
    y_cols = [c for c in tracking.columns if c.endswith("_y")]

    for _, rows in tracking.groupby("period_id").groups.items():
        if not home_attacks_left_to_right(tracking.loc[rows, keeper_x].mean()):
            tracking.loc[rows, x_cols] *= -1
            tracking.loc[rows, y_cols] *= -1


def _find_file(data_dir: Path, kind: str, match_id: str) -> Path:
    matches = sorted(Path(data_dir).glob(f"*{kind}*{match_id}*.xml"))
    if not matches:
        raise FileNotFoundError(f"No '{kind}' file for match {match_id} in {data_dir}")
    return matches[0]
