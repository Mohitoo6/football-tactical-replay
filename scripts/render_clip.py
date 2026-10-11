"""Render a clip as an MP4 (full 25 fps) and a lighter GIF (12.5 fps) in outputs/.

    uv run python scripts/render_clip.py musiala-winner
    uv run python scripts/render_clip.py musiala-winner --no-gif

MP4 export needs ffmpeg (macOS: brew install ffmpeg). The GIF needs nothing extra.
"""

import argparse
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from tactics.data.clips import load_clip
from tactics.viz.animate import save_animation

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clip_id")
    parser.add_argument("--no-gif", action="store_true", help="only render the MP4")
    parser.add_argument("--plain", action="store_true", help="no shape overlays")
    args = parser.parse_args()

    clip = load_clip(ROOT / "clips" / args.clip_id)
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)

    jobs = [(out_dir / f"{args.clip_id}.mp4", 1, 100)]
    if not args.no_gif:
        jobs.append((out_dir / f"{args.clip_id}.gif", 2, 60))
    for path, step, dpi in jobs:
        start = time.perf_counter()
        save_animation(clip, path, step=step, dpi=dpi, overlays=not args.plain)
        size_mb = path.stat().st_size / 1e6
        print(f"saved {path.relative_to(ROOT)} ({size_mb:.1f} MB) in {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
