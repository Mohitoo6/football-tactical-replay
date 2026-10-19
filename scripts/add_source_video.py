"""Attach the original video to an existing clip, so the replay can play it under the 2D pitch.

    uv run python scripts/add_source_video.py drone-1110-1140 data/raw/soccertrack/top_view/videos/D_20220220_1_1110_1140.mp4

New drone uploads keep their video automatically; this is for clips made before that, or by scripts.
The video must start at the clip's first frame (as the drone pipeline numbers frames from the video start).
"""

import argparse
from pathlib import Path

from tactics.service import clip_folder, save_source_video


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip_id")
    parser.add_argument("video", type=Path)
    args = parser.parse_args()
    folder = clip_folder(args.clip_id)
    if not save_source_video(args.video, folder):
        raise SystemExit("could not encode the video (is ffmpeg installed?)")
    print(f"{folder / 'source.mp4'}: {(folder / 'source.mp4').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
