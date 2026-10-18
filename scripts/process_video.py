"""Turn any top-view drone clip into a clip for the overlays and the AI coach.

    uv run --group video python scripts/process_video.py path/to/clip.mp4
    uv run --group video python scripts/process_video.py clip.mp4 --id my-goal --title "Our winner" --render --explain

Prints a quality report first. If the clip is not suitable (camera moving, pitch
outline not visible, too short, implausible player counts) it stops there
instead of producing wrong positions. Otherwise it writes clips/<id>/ and can
render the overlay video (--render) and the coach explanation (--explain, one
LLM call, needs keys in .env).

(An experiment with moving TV-broadcast cameras lives on the branch
`broadcast-experiment`; see DECISIONS.md, D28, D29 and D31.)
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from tactics.data.clips import save_clip
from tactics.data.validate import find_problems
from tactics.video.pipeline import process_video

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--id", help="clip id (default: from the file name)")
    parser.add_argument("--title", help="clip title (default: from the file name)")
    parser.add_argument("--pitch", default="105x68", help="pitch size in metres, e.g. 100x64 (default 105x68)")
    parser.add_argument("--start", type=float, default=0.0, help="match clock of the first frame in seconds (default 0)")
    parser.add_argument("--render", action="store_true", help="also render clips/<id>/video.mp4")
    parser.add_argument("--explain", action="store_true", help="also generate the coach explanation (one LLM call)")
    args = parser.parse_args()

    clip_id = args.id or re.sub(r"[^a-z0-9]+", "-", args.video.stem.lower()).strip("-")
    title = args.title or f"Drone clip: {args.video.stem}"
    length_m, width_m = (float(v) for v in args.pitch.lower().split("x"))

    start = time.perf_counter()
    clip, report = process_video(args.video, clip_id, title, length_m, width_m,
                                 progress=lambda f, msg: print(f"\r  {f:4.0%}  {msg:<45}", end="", flush=True),
                                 start_s=args.start)
    print(f"\r  done in {time.perf_counter() - start:.0f} s{' ' * 40}")
    print(report.summary())
    if clip is None:
        print("This clip is not suitable; nothing was written.")
        return 1

    folder = save_clip(clip, ROOT / "clips")
    problems = find_problems(clip.players, clip.ball)
    print(f"Saved {folder.relative_to(ROOT)} ({len(clip.ball)} frames).", *[f"PROBLEM: {p}" for p in problems], sep="\n")
    if args.render:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "render_clip.py"), "--for-app", clip_id], check=True)
    if args.explain:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_explanations.py"), clip_id], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
