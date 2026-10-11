"""Render one frame of a clip to a PNG.

    uv run python scripts/render_frame.py musiala-winner --time 2594
    uv run python scripts/render_frame.py coman-opener            # first frame

--time is seconds since the start of the period (same clock as clips.toml).
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from tactics.data.clips import load_clip
from tactics.viz.pitch import save_frame

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clip_id")
    parser.add_argument("--time", type=float, help="seconds since the start of the period")
    parser.add_argument("--plain", action="store_true", help="no shape overlays")
    args = parser.parse_args()

    clip = load_clip(ROOT / "clips" / args.clip_id)
    ball = clip.ball
    if args.time is None:
        frame = int(ball["frame"].iloc[0])
    else:
        frame = int(ball.loc[(ball["time_s"] - args.time).abs().idxmin(), "frame"])

    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{args.clip_id}_{frame}.png"
    save_frame(clip, frame, out, overlays=not args.plain)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
