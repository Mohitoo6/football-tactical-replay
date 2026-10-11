"""Health report for any DFL match: does our pipeline hold up on the whole match?

    uv run python scripts/check_match.py J03WN1

Runs the same checks we use for clips, but on every frame of the match, and
lists the goals with ready-to-paste clips.toml entries.
"""

import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

from tactics.data.load import find_goals, get_frames, load_dfl_match
from tactics.data.validate import (
    MAX_PLAYER_SPEED_MS, OUTSIDE_MARGIN_M, find_problems, find_warnings, player_speeds,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "dfl"


def main(match_id: str) -> None:
    start = time.perf_counter()
    match = load_dfl_match(RAW_DIR, match_id)
    tracking = match.tracking
    players, ball = get_frames(match, int(tracking["frame_id"].min()), int(tracking["frame_id"].max()))
    print(f"== {match_id}: {match.home.name} ({match.home.formation}) v {match.away.name} ({match.away.formation})")
    print(f"loaded {len(ball):,} frames in {time.perf_counter() - start:.0f} s")

    counts = players.groupby(["frame", "team"]).size().unstack(fill_value=0)
    for side in ("home", "away"):
        share_11 = (counts[side] == 11).mean()
        print(f"{side}: 11 players in {share_11:.1%} of frames (min {counts[side].min()}, max {counts[side].max()})")

    keepers = players[players["position"] == "Goalkeeper"]
    for period, rows in keepers.groupby("period"):
        home_x = rows.loc[rows["team"] == "home", "x"].mean()
        away_x = rows.loc[rows["team"] == "away", "x"].mean()
        ok = home_x < 0 < away_x
        print(f"period {period}: home keeper mean x {home_x:+.1f}, away keeper {away_x:+.1f} -> "
              f"{'home attacks left to right: OK' if ok else 'ORIENTATION PROBLEM'}")

    speeds = player_speeds(players, match.frame_rate)
    print(f"player speed: p99 {np.nanpercentile(speeds, 99):.1f} m/s, max {np.nanmax(speeds):.1f} m/s, "
          f"{int((speeds > MAX_PLAYER_SPEED_MS).sum())} moves above {MAX_PLAYER_SPEED_MS} m/s "
          f"out of {int(speeds.notna().sum()):,}")

    outside = (players["x"].abs() > 52.5 + OUTSIDE_MARGIN_M) | (players["y"].abs() > 34 + OUTSIDE_MARGIN_M)
    print(f"player positions > {OUTSIDE_MARGIN_M} m outside the pitch: {int(outside.sum())} of {len(players):,}")
    print(f"ball dead in {(~ball['alive']).mean():.0%} of frames; missing in {ball['x'].isna().mean():.1%}")

    print("validation on the whole match:")
    for problem in find_problems(players, ball) or ["no problems"]:
        print(f"  - {problem}")
    for warning in find_warnings(players, match.frame_rate):
        print(f"  - warning: {warning}")

    goals = find_goals(RAW_DIR, match)
    print(f"goals ({len(goals)}): paste into clips/clips.toml to build a clip")
    for g in goals.itertuples():
        surname = (g.player or "goal").split()[-1].lower()
        name = unicodedata.normalize("NFKD", surname).encode("ascii", "ignore").decode()  # förster -> forster
        print(f'\n[[clip]]\nid = "{name}-{match_id.lower()}-{int(g.time_s)}"\nmatch_id = "{match_id}"\n'
              f'title = "{g.player} goal for {getattr(match, g.team).name}"\nperiod = {g.period}\n'
              f'start_s = {g.time_s - 15:.1f}\nend_s = {g.time_s + 5:.1f}\nfocus_team = "{g.team}"')


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "J03WMX")
