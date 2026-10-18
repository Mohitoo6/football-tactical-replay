"""Write a clip as a tracking file in our upload template (one row per object per moment).

    uv run python scripts/export_template.py musiala-winner templates/example_musiala_winner.csv

Used to make the example file in templates/ and to test that an uploaded file reproduces the clip.
"""

import sys
from pathlib import Path

import pandas as pd

from tactics.data.clips import load_clip

ROOT = Path(__file__).resolve().parents[1]


def clip_to_template(clip) -> pd.DataFrame:
    start = clip.ball["time_s"].iloc[0]
    players = clip.players.assign(time_s=(clip.players["time_s"] - start).round(3))
    people = pd.DataFrame({"time_s": players["time_s"], "team": players["team"], "player": players["player_name"],
                           "jersey": players["jersey"], "position": players["position"].map({"Goalkeeper": "GK"}),
                           "x": players["x"].round(2), "y": players["y"].round(2)})
    ball = clip.ball[clip.ball["alive"]]
    balls = pd.DataFrame({"time_s": (ball["time_s"] - start).round(3), "team": "ball", "player": "", "jersey": None,
                          "position": None, "x": ball["x"].round(2), "y": ball["y"].round(2)})
    return pd.concat([people, balls]).sort_values(["time_s", "team"], kind="stable").reset_index(drop=True)


if __name__ == "__main__":
    clip_id, out = sys.argv[1], Path(sys.argv[2])
    clip_to_template(load_clip(ROOT / "clips" / clip_id)).to_csv(out, index=False)
    print(f"wrote {out}")
