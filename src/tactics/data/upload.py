"""Coordinate data that a user brings -> a clip for the overlays and the AI coach (Phase 9, D32).

Two kinds of input:
1. Our template: a CSV or Excel file with one row per object per moment,
       time_s, team, player, x, y        (+ optional jersey, position)
   where team is "home", "away" or "ball" (see templates/tracking_template.csv).
2. A provider format read with kloppy (Metrica, SkillCorner, Sportec/DFL, TRACAB, Second Spectrum, Hawk-Eye),
   cut to a time window.

Both become the same `TrackingInput`, are checked by `check_input` (a quality report that can refuse
the data instead of guessing) and turned into a standard clip by `to_clip`. From there the system
works exactly as for the bundled clips: geometry, overlays, facts and the coach.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from tactics.data.clips import Clip, match_clock
from tactics.data.load import BALL_COLUMNS, PLAYER_COLUMNS
from tactics.data.normalize import rotate_180
from tactics.data.report import QualityReport

REQUIRED = ["time_s", "team", "player", "x", "y"]
UNITS = ("metres", "metres_corner", "normalised")  # centre origin | origin at a corner | 0..1 along each side
PITCH_M = (105.0, 68.0)
MIN_SECONDS, MAX_SECONDS = 3.0, 120.0
FPS_RANGE = (5.0, 60.0)
MIN_PLAYERS_PER_TEAM = 7  # median players of each team per moment (red cards and partial views happen)
MAX_OUTSIDE_SHARE = 0.02  # share of positions more than 5 m outside the pitch before we suspect the units
OUTSIDE_M = 5.0
MIN_BALL_SHARE = 0.5
KEEPER_MIN_DEPTH_M = 30.0  # an inferred keeper must stand, on average, this deep (the penalty area starts at 36 m)
KEEPER_MAX_WIDTH_M = 20.16  # ... and within the penalty area's width (half of 40.32 m)


@dataclass
class TrackingInput:
    players: pd.DataFrame  # frame, time_s, team, player_id, player_name, jersey, position, x, y (metres, centre origin)
    ball: pd.DataFrame  # frame, time_s, x, y, z, alive
    frame_rate: float
    team_names: dict[str, str]  # "home"/"away" -> name
    source: str  # where the data came from, for the clip's credit line


def read_table(path: Path | str) -> pd.DataFrame:
    """Read a CSV or Excel file (by extension) with lower-cased, stripped column names."""
    path = Path(path)
    table = pd.read_excel(path) if path.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(path)
    table.columns = [str(c).strip().lower() for c in table.columns]
    return table


def from_template(table: pd.DataFrame, report: QualityReport, units: str = "metres",
                  pitch_m: tuple[float, float] = PITCH_M, team_names: dict[str, str] | None = None,
                  source: str = "Uploaded by the user") -> TrackingInput | None:
    """Our long template -> TrackingInput (None, with a failed check in `report`, if it cannot be read)."""
    missing = [c for c in REQUIRED if c not in table.columns]
    report.add("required columns", not missing, "all present" if not missing else f"missing: {', '.join(missing)}",
               ", ".join(REQUIRED))
    if missing:
        return None
    table = table.copy()
    for column in ("time_s", "x", "y"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    unreadable = table[["time_s", "x", "y"]].isna().any(axis=1).mean()
    report.add("numbers readable", unreadable == 0, f"{unreadable:.1%} of rows have a non-number in time_s, x or y",
               "time_s, x and y are numbers")
    if unreadable:
        return None
    table["team"] = table["team"].astype(str).str.strip().str.lower()
    unknown = sorted(set(table["team"]) - {"home", "away", "ball"})
    report.add("team values", not unknown, "home, away, ball" if not unknown else f"unknown: {', '.join(unknown[:5])}",
               'each row\'s team is "home", "away" or "ball"')
    if unknown:
        return None
    if units not in UNITS:
        raise ValueError(f"units must be one of {UNITS}, got {units!r}")
    table["x"], table["y"] = _to_metres(table["x"].to_numpy(float), table["y"].to_numpy(float), units, pitch_m)

    times = np.sort(table["time_s"].unique())
    frame_of = {t: i for i, t in enumerate(times)}
    table["frame"] = table["time_s"].map(frame_of)
    step = float(np.median(np.diff(times))) if len(times) > 1 else 0.0
    frame_rate = round(1 / step, 3) if step > 0 else 0.0

    people = table[table["team"] != "ball"].copy()
    people["player"] = people["player"].astype(str).str.strip()
    people = people.drop_duplicates(["frame", "team", "player"])
    position = people["position"] if "position" in people else pd.Series(None, index=people.index)
    jersey = pd.to_numeric(people["jersey"], errors="coerce") if "jersey" in people else pd.Series(np.nan, index=people.index)
    players = pd.DataFrame({
        "frame": people["frame"].astype(int), "time_s": people["time_s"], "team": people["team"],
        "player_id": people["team"] + "-" + people["player"], "player_name": people["player"],
        "jersey": jersey, "position": position.map(_position), "x": people["x"], "y": people["y"]})
    balls = table[table["team"] == "ball"].drop_duplicates("frame")
    ball = pd.DataFrame({"frame": range(len(times)), "time_s": times}).merge(
        balls[["frame", "x", "y"]], on="frame", how="left")
    ball = ball.assign(z=0.0, alive=ball["x"].notna())
    names = {"home": "Home", "away": "Away", **(team_names or {})}
    return TrackingInput(players, ball, frame_rate, names, source)


def from_kloppy(dataset, period: int, start_s: float, end_s: float, source: str) -> TrackingInput:
    """A kloppy TrackingDataset in metres (coordinates="secondspectrum") -> TrackingInput for one time window."""
    wide = dataset.to_df()
    seconds = wide["timestamp"].dt.total_seconds()
    wide = wide[(wide["period_id"] == period) & (seconds >= start_s) & (seconds <= end_s)].reset_index(drop=True)
    times = wide["timestamp"].dt.total_seconds().to_numpy()
    parts, names = [], {}
    for team in dataset.metadata.teams:
        side = str(team.ground)
        names[side] = team.name or side.title()
        for player in team.players:
            if f"{player.player_id}_x" not in wide:
                continue
            parts.append(pd.DataFrame({
                "frame": np.arange(len(wide)), "time_s": times, "team": side,
                "player_id": str(player.player_id), "player_name": player.name or f"{side.title()} {player.jersey_no}",
                "jersey": player.jersey_no, "position": _position(str(player.starting_position)),
                "x": wide[f"{player.player_id}_x"], "y": wide[f"{player.player_id}_y"]}))
    players = pd.concat(parts, ignore_index=True).dropna(subset=["x", "y"])
    state = wide["ball_state"].astype(str) if "ball_state" in wide else pd.Series("alive", index=wide.index)
    ball = pd.DataFrame({"frame": np.arange(len(wide)), "time_s": times, "x": wide["ball_x"], "y": wide["ball_y"],
                         "z": (wide["ball_z"] if "ball_z" in wide else pd.Series(0.0, index=wide.index)).fillna(0.0),
                         "alive": wide["ball_x"].notna() & (state != "dead")})  # unknown height: on the ground
    return TrackingInput(players, ball, float(dataset.metadata.frame_rate), names, source)


METRICA_HEADER_ROWS = 3
# What each provider's two boxes should hold, for messages when a file cannot be read.
PROVIDER_BOXES = {
    "metrica": ("the home team's tracking CSV", "the away team's tracking CSV"),
    "skillcorner": ("the match JSON (metadata)", "the tracking JSONL"),
    "sportec": ("the match information XML", "the positions XML"),
    "tracab": ("the metadata (XML or JSON)", "the tracking data (.dat or JSON)"),
    "secondspectrum": ("the metadata XML (and the metadata JSON, if you have it)", "the tracking JSONL"),
    "hawkeye": ("the ball files (…samples.ball)", "the player files (…samples.centroids)"),
}


def unreadable_message(provider: str, error: Exception) -> str:
    """A read error in plain words: what the boxes should hold, then the technical detail."""
    first, second = PROVIDER_BOXES.get(provider, ("the first file", "the second file"))
    return (f"These files could not be read as {provider} tracking data. The first box takes {first}, the second "
            f"{second}. (Detail: {type(error).__name__}: {str(error)[:160]})")


def metrica_side(path: Path | str) -> str | None:
    """'home' or 'away' from the first header row of a Metrica tracking CSV, if it says."""
    with open(path, encoding="utf-8-sig") as f:
        first = f.readline().lower()
    sides = {side for side in ("home", "away") if side in first}
    return sides.pop() if len(sides) == 1 else None


def period_range(dataset, period: int) -> tuple[float, float] | None:
    """First and last second of `period` in a kloppy dataset (None if the period has no frames)."""
    times = [f.timestamp.total_seconds() for f in dataset.records if f.period.id == period]
    return (min(times), max(times)) if times else None


def trim_metrica_csv(source: Path | str, target: Path, period: int, start_s: float, end_s: float,
                     margin_s: float = 1.0) -> Path:
    """Copy of a Metrica tracking CSV with only the rows kloppy needs for one window (D39).

    A Metrica file holds a whole match (~140,000 rows), and kloppy takes minutes to read it all. We keep the three
    header rows, the first and last row of every period (kloppy counts time from the first, so timestamps stay the
    same, and the half's length stays known) and the rows of the window. Time [s] counts from the match start, so
    the window is measured from its period's first row.
    """
    period_start: dict[str, float] = {}
    last, last_written = None, True  # the previous tracking row, and whether it was kept
    with open(source, encoding="utf-8-sig") as rows, open(target, "w", encoding="utf-8") as out:
        for i, line in enumerate(rows):
            if i < METRICA_HEADER_ROWS:
                out.write(line)
                continue
            cells = line.split(",", 3)
            if len(cells) < 3:
                continue
            try:
                time_s = float(cells[2])
            except ValueError:  # not a tracking row: let kloppy report the file
                out.write(line)
                continue
            new_period = cells[0] not in period_start
            if new_period and last is not None and not last_written:
                out.write(last)  # the last row of the period before
            keep = new_period or (cells[0] == str(period) and
                                  start_s - margin_s <= time_s - period_start[cells[0]] <= end_s + margin_s)
            if new_period:
                period_start[cells[0]] = time_s
            if keep:
                out.write(line)
            last, last_written = line, keep
        if last is not None and not last_written:
            out.write(last)
    return target


def _secondspectrum_meta(meta: Path | str | list[Path], raw: Path | str) -> tuple:
    """Second Spectrum sends the metadata as XML and as JSON (team and player names): (XML, tracking, JSON or None)."""
    paths = meta if isinstance(meta, list) else [meta]
    xml = [p for p in paths if str(p).lower().endswith(".xml")]
    other = [p for p in paths if p not in xml]
    if xml:
        return xml[0], raw, (other[0] if other else None)
    return paths[0], raw, None  # a single JSON: kloppy says what is missing


def load_provider(provider: str, files: dict[str, Path | str | list[Path]],
                  window: tuple[int, float, float] | None = None):
    """Read a provider's files with kloppy, in metres with the origin at the centre spot.

    metrica: home_data, away_data (CSV) · skillcorner: meta_data, raw_data (JSON, JSONL)
    sportec (DFL): meta_data, raw_data (XML) · tracab: meta_data (XML/JSON), raw_data (.dat/JSON)
    secondspectrum: meta_data (XML/JSON), raw_data (JSONL)
    hawkeye: ball_feeds, player_centroid_feeds (lists: Hawk-Eye writes one file per minute)
    window: (period, start_s, end_s); Metrica files are first cut to it, so a whole match reads in a second.
    """
    from kloppy import hawkeye, metrica, secondspectrum, skillcorner, sportec, tracab

    readers = {"metrica": lambda f: metrica.load_tracking_csv(f["home_data"], f["away_data"], coordinates="secondspectrum"),
               "skillcorner": lambda f: skillcorner.load(f["meta_data"], f["raw_data"], coordinates="secondspectrum"),
               "sportec": lambda f: sportec.load_tracking(f["meta_data"], f["raw_data"], coordinates="secondspectrum"),
               "tracab": lambda f: tracab.load(f["meta_data"], f["raw_data"], coordinates="secondspectrum"),
               "secondspectrum": lambda f: secondspectrum.load(*_secondspectrum_meta(f["meta_data"], f["raw_data"]),
                                                                coordinates="secondspectrum"),
               "hawkeye": lambda f: hawkeye.load(f["ball_feeds"], f["player_centroid_feeds"],
                                                 coordinates="secondspectrum")}  # names must keep "samples.ball" / "samples.centroids"
    if provider not in readers:
        raise ValueError(f"provider must be one of {sorted(readers)}, got {provider!r}")
    if provider == "metrica" and window:
        with tempfile.TemporaryDirectory(prefix="metrica-") as folder:
            trimmed = {key: trim_metrica_csv(path, Path(folder) / f"{key}.csv", *window) for key, path in files.items()}
            return readers[provider](trimmed)
    return readers[provider](files)


def _same_teams_share(players: pd.DataFrame) -> float:
    """Share of moments where both teams have exactly the same positions: the same file given twice."""
    if players.empty:
        return 0.0
    rounded = players.assign(x=players["x"].round(2), y=players["y"].round(2))
    spots = rounded.groupby(["frame", "team"])[["x", "y"]].apply(lambda g: tuple(sorted(map(tuple, g.to_numpy()))))
    spots = spots.unstack()
    if "home" not in spots or "away" not in spots:
        return 0.0
    return float((spots["home"] == spots["away"]).mean())


def check_input(data: TrackingInput, report: QualityReport) -> None:
    """Add the checks that decide whether this data can be analysed."""
    seconds = len(data.ball) / data.frame_rate if data.frame_rate else 0.0
    report.add("frame rate", FPS_RANGE[0] <= data.frame_rate <= FPS_RANGE[1], f"{data.frame_rate:g} per second",
               f"{FPS_RANGE[0]:g}-{FPS_RANGE[1]:g} (from the time step between rows)")
    report.add("clip length", MIN_SECONDS <= seconds <= MAX_SECONDS, f"{seconds:.1f} s",
               f"{MIN_SECONDS:g}-{MAX_SECONDS:g} s")
    counts = data.players.groupby(["frame", "team"]).size().unstack(fill_value=0)
    medians = {team: float(counts[team].median()) if team in counts else 0.0 for team in ("home", "away")}
    report.add("players per team", min(medians.values()) >= MIN_PLAYERS_PER_TEAM,
               f"median home {medians['home']:.0f}, away {medians['away']:.0f} per moment", f">= {MIN_PLAYERS_PER_TEAM} each")
    outside = ((data.players["x"].abs() > 52.5 + OUTSIDE_M) | (data.players["y"].abs() > 34 + OUTSIDE_M)).mean()
    report.add("positions on the pitch", outside <= MAX_OUTSIDE_SHARE, f"{outside:.1%} more than {OUTSIDE_M:g} m outside",
               f"<= {MAX_OUTSIDE_SHARE:.0%} (otherwise the units are probably wrong)")
    same = _same_teams_share(data.players)
    report.add("two different teams", same < 0.5, f"{same:.0%} of moments with identical home and away positions",
               "the home and away files are different (not the same file twice)")
    ball_share = float(data.ball["alive"].mean()) if len(data.ball) else 0.0
    report.add("ball present", ball_share >= MIN_BALL_SHARE, f"{ball_share:.0%} of moments", f">= {MIN_BALL_SHARE:.0%}",
               blocking=False)
    keepers = int(data.players.loc[data.players["position"] == "Goalkeeper", "team"].nunique())
    report.add("goalkeepers given", keepers == 2, f"{keepers} of 2 teams",
               "2 (otherwise inferred: the deepest player of each team)", blocking=False)


def to_clip(data: TrackingInput, clip_id: str, title: str, focus_team: str = "home", start_s: float = 0.0,
            period: int = 1) -> Clip:
    """A checked TrackingInput -> a standard clip in which `focus_team` attacks left to right."""
    players = _infer_keepers(data.players.copy())
    players = players.assign(period=period, time_s=start_s + players["frame"] / data.frame_rate)
    ball = data.ball.assign(period=period, time_s=start_s + data.ball["frame"] / data.frame_rate, owning_team=None)
    ball[["x", "y"]] = ball[["x", "y"]].ffill().bfill().fillna(0.0)
    ball["z"] = ball["z"].fillna(0.0)

    keeper_x = players.loc[(players["team"] == focus_team) & (players["position"] == "Goalkeeper"), "x"].mean()
    rotated = bool(keeper_x > 0)  # the focus team's keeper on the right: it attacks right to left, so turn the clip
    if rotated:
        players, ball = rotate_180(players), rotate_180(ball)
    end_s = start_s + (len(ball) - 1) / data.frame_rate
    meta = {
        "clip_id": clip_id, "match_id": None, "title": title, "period": period,
        "start_s": start_s, "end_s": end_s, "focus_team": focus_team,
        "start_clock": match_clock(period, start_s), "end_clock": match_clock(period, end_s),
        "frame_rate": data.frame_rate, "rotated": rotated, "direction_known": bool(np.isfinite(keeper_x)),
        "teams": {side: {"name": data.team_names.get(side, side.title()), "formation": None} for side in ("home", "away")},
        "goals": [], "data_kind": "uploaded",
        "coordinates": "metres, origin at pitch centre; focus_team attacks left to right",
        "source": data.source, "credit": f"Data: {data.source} · analysis by this project",
    }
    players = players.sort_values(["frame", "team", "jersey"]).reset_index(drop=True)[PLAYER_COLUMNS]
    return Clip(meta, players, ball[BALL_COLUMNS].reset_index(drop=True))


def _to_metres(x: np.ndarray, y: np.ndarray, units: str, pitch_m: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    length, width = pitch_m
    if units == "metres_corner":
        return x - length / 2, y - width / 2
    if units == "normalised":
        return (x - 0.5) * length, (y - 0.5) * width
    return x, y


def _position(value) -> str | None:
    """Map the many ways of writing 'goalkeeper' to our label; other positions are not used by the analysis."""
    text = str(value).strip().lower() if value is not None else ""
    return "Goalkeeper" if text in {"gk", "goalkeeper", "goalie", "keeper", "g"} else None


def _infer_keepers(players: pd.DataFrame) -> pd.DataFrame:
    """Where a team has no goalkeeper marked, mark as keeper its deepest regular player in front of goal (if deep enough)."""
    for team in ("home", "away"):
        rows = players[players["team"] == team]
        if rows.empty or (rows["position"] == "Goalkeeper").any():
            continue
        frames = rows["frame"].nunique()
        regular = rows.groupby("player_id").filter(lambda g: len(g) >= 0.5 * frames)
        if regular.empty:
            continue
        means = regular.groupby("player_id")[["x", "y"]].mean()
        # In front of goal: within the penalty area's width. A player taking a corner is deep but wide.
        central = means[means["y"].abs() <= KEEPER_MAX_WIDTH_M]
        if central.empty:
            continue
        deepest = central["x"].abs().idxmax()
        if abs(central.at[deepest, "x"]) >= KEEPER_MIN_DEPTH_M:
            players.loc[players["player_id"] == deepest, "position"] = "Goalkeeper"
    return players
