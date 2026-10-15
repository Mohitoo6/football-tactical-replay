"""Stress-test the drone pipeline: edit a SoccerTrack segment in ways real clips differ, then score it.

    uv run --group video python scripts/robustness.py 0600_0630                  # every edit
    uv run --group video python scripts/robustness.py 0600_0630 rotate90 dark30  # chosen edits
    uv run --group video python scripts/robustness.py 0600_0630 --pause 90       # cool-down between runs

Each edit makes a copy of the video with ffmpeg (Apple's hardware encoder, at the
original bitrate), runs the exact production pipeline on it, and scores it against
the ground truth moved the same way (scripts/video_to_tracks.py). An edit passes if
the pipeline either keeps working or refuses the clip; quietly wrong output fails.
Results go to evals/video/robustness.csv. Copies are deleted after scoring.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from tactics.video.pipeline import video_info
from video_to_tracks import DATA, PREFIX, evaluate

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "video" / "robustness.csv"
WORK = DATA / "edited"  # git-ignored (data/raw)
BITRATE = "8M"  # the SoccerTrack files are ~8.2 Mbit/s


def edits(width: int, height: int, fps: float, count: int) -> dict[str, tuple[str, list[str], np.ndarray | None, np.ndarray | None]]:
    """name -> (what it simulates, ffmpeg options, pixel map original->copy, frame map copy->original)."""
    crop, cut = round(0.1 * width), round(0.15 * width)  # SoccerTrack's left goal line is at ~12.5% of the width
    step = 25 / fps  # keep the first original frame of each 1/25 s slot, so we know exactly which ones were kept
    kept = [n for n in range(count) if n == 0 or np.floor(n * step) > np.floor((n - 1) * step)]
    return {
        "original": ("unchanged, the baseline for this code version", None, None, None),
        "rotate90": ("drone turned a quarter: portrait pitch", ["-vf", "transpose=1"],
                     np.array([[0, -1, height - 1], [1, 0, 0]], float), None),
        "rotate180": ("drone facing the other way", ["-vf", "hflip,vflip"],
                      np.array([[-1, 0, width - 1], [0, -1, height - 1]], float), None),
        "crop10": ("tighter framing: 10% of the width cut off, the pitch still fully in view",
                   ["-vf", f"crop={width - crop}:{height}:{crop}:0"], np.array([[1, 0, -crop], [0, 1, 0]], float), None),
        "crop_goal": ("15% of the width cut off, through one goal line (should be refused)",
                      ["-vf", f"crop={width - cut}:{height}:{cut}:0"], np.array([[1, 0, -cut], [0, 1, 0]], float), None),
        "dark30": ("30% darker (evening, cloud)", ["-vf", "lutyuv=y=val*0.7"], None, None),
        "1080p": ("Full HD instead of 4K", ["-vf", f"scale={width // 2}:{height // 2}:flags=area"],
                  np.array([[0.5, 0, -0.25], [0, 0.5, -0.25]], float), None),
        "720p": ("HD 720p: below the resolution the detector needs?", ["-vf", f"scale={width // 3}:{height // 3}:flags=area"],
                 np.array([[1 / 3, 0, -1 / 3], [0, 1 / 3, -1 / 3]], float), None),
        "20s": ("a 20 s clip", ["-frames:v", str(round(20 * fps))], None, None),
        "25fps": ("25 frames per second", ["-vf", f"select='eq(n,0)+gt(floor(n*{step:.9f}),floor((n-1)*{step:.9f}))',"
                                           "setpts=N/(25*TB)", "-r", "25"], None, np.array(kept)),
    }


def make_copy(source: Path, target: Path, options: list[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), *options, "-an",
                    "-c:v", "h264_videotoolbox", "-b:v", BITRATE, str(target)], check=True)


def save_row(row: dict) -> None:
    """Add or replace this (segment, edit) row in evals/video/robustness.csv."""
    table = pd.read_csv(RESULTS, dtype={"segment": str}) if RESULTS.exists() else pd.DataFrame()
    if len(table):
        table = table[(table["segment"] != row["segment"]) | (table["edit"] != row["edit"])]
    table = pd.concat([table, pd.DataFrame([row])], ignore_index=True).sort_values(["segment", "edit"])
    table.round(4).to_csv(RESULTS, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("segment", help="e.g. 0600_0630")
    parser.add_argument("edits", nargs="*", help="which edits (default: all)")
    parser.add_argument("--pause", type=float, default=0, help="seconds to rest between runs (lets the laptop cool)")
    args = parser.parse_args()

    source = DATA / "top_view" / "videos" / f"{PREFIX}{args.segment}.mp4"
    fps, count, (height, width) = video_info(source)
    table = edits(width, height, fps, count)
    for i, name in enumerate(args.edits or table):
        what, options, pixel_map, frame_map = table[name]
        if i and args.pause:
            print(f"resting {args.pause:.0f} s", flush=True)
            time.sleep(args.pause)
        print(f"\n=== {args.segment} / {name}: {what}", flush=True)
        if options is None:
            row = evaluate(args.segment)
        else:
            copy = WORK / f"{args.segment}_{name}.mp4"
            make_copy(source, copy, options)
            try:
                row = evaluate(args.segment, copy, pixel_map, frame_map)
            finally:
                copy.unlink(missing_ok=True)
        save_row({"edit": name, **row})
    return 0


if __name__ == "__main__":
    sys.exit(main())
