"""Build clip files from the raw DFL data.

    uv run python scripts/build_clips.py

Reads clip definitions from clips/clips.toml, loads each needed match from
data/raw/dfl/ (slow: ~30-70 s per match), and writes clips/<clip_id>/.
Exits with an error if any clip fails the sanity checks.
"""

import sys
import time
from itertools import groupby
from pathlib import Path

from tactics.data.clips import build_clip, load_clip_specs, save_clip
from tactics.data.load import load_dfl_match
from tactics.data.validate import find_problems, players_per_team

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "dfl"
CLIPS_DIR = ROOT / "clips"


def main() -> int:
    specs = load_clip_specs(CLIPS_DIR / "clips.toml")
    failed = 0
    for match_id, match_specs in groupby(sorted(specs, key=lambda s: s.match_id), key=lambda s: s.match_id):
        start = time.perf_counter()
        match = load_dfl_match(RAW_DIR, match_id)
        print(f"loaded {match_id}: {match.home.name} ({match.home.formation}) v "
              f"{match.away.name} ({match.away.formation}) in {time.perf_counter() - start:.0f} s")

        for spec in match_specs:
            clip = build_clip(match, spec)
            folder = save_clip(clip, CLIPS_DIR)
            counts = players_per_team(clip.players)
            problems = find_problems(clip.players, clip.ball, match.frame_rate)
            failed += bool(problems)
            print(f"  {spec.clip_id}: {clip.meta['start_clock']}-{clip.meta['end_clock']}, "
                  f"{len(clip.ball)} frames, players per team "
                  f"{counts.to_dict('index')} -> {folder.relative_to(ROOT)}")
            for problem in problems:
                print(f"    PROBLEM: {problem}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
