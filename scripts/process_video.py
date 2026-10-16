"""Turn a football clip into a clip for the overlays and the AI coach.

    uv run --group video python scripts/process_video.py path/to/clip.mp4
    uv run --group video python scripts/process_video.py clip.mp4 --id my-goal --title "Our winner" --render --explain
    uv run --group video python scripts/process_video.py highlight.mov --mode broadcast --render

Two kinds of video:
- drone: a hovering top-down camera with the whole pitch in view (Phase 7);
- broadcast: the usual side-on TV camera that pans and zooms (Phase 8; needs
  `sh tools/pnlcalib/setup.sh` once). Only players in view are tracked.
With --mode auto (the default) the drone checks run first; if the clip has no
fixed view of the whole pitch, the broadcast path is tried.

Prints a quality report first. If the clip is not suitable it stops there
instead of producing wrong positions. Otherwise it writes clips/<id>/ and can
render the video (--render: a 2D replay for drone clips, the analysis drawn on
the footage for broadcast clips) and the coach explanation (--explain, one LLM
call, needs keys in .env). Broadcast clips get ids starting with "local-",
which git ignores: they come from footage we may not redistribute.
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from tactics.data.clips import save_clip
from tactics.data.validate import find_problems

ROOT = Path(__file__).resolve().parents[1]
# A drone clip refused for one of these reasons may be a moving broadcast camera instead.
NOT_A_FIXED_VIEW = {"pitch outline found", "pitch outline shape", "calibration stable over the clip", "camera holds still"}


def show_progress(fraction: float, message: str) -> None:
    print(f"\r  {fraction:4.0%}  {message:<50}", end="", flush=True)


def run_drone(args, clip_id, title, length_m, width_m):
    from tactics.video.pipeline import process_video
    clip, report = process_video(args.video, clip_id, title, length_m, width_m, progress=show_progress, start_s=args.start)
    return clip, report, None


def run_broadcast(args, clip_id, title):
    from tactics.broadcast.pipeline import process_broadcast
    return process_broadcast(args.video, clip_id, title, progress=show_progress, start_s=args.start)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--mode", choices=["auto", "drone", "broadcast"], default="auto")
    parser.add_argument("--id", help="clip id (default: from the file name)")
    parser.add_argument("--title", help="clip title (default: from the file name)")
    parser.add_argument("--pitch", default="105x68", help="pitch size in metres for drone clips, e.g. 100x64 (default 105x68)")
    parser.add_argument("--start", type=float, default=0.0, help="match clock of the first frame in seconds (default 0)")
    parser.add_argument("--render", action="store_true", help="also render clips/<id>/video.mp4")
    parser.add_argument("--explain", action="store_true", help="also generate the coach explanation (one LLM call)")
    args = parser.parse_args()

    stem = re.sub(r"[^a-z0-9]+", "-", args.video.stem.lower()).strip("-")
    title = args.title or f"Clip: {args.video.stem}"
    length_m, width_m = (float(v) for v in args.pitch.lower().split("x"))

    start = time.perf_counter()
    mode, clip, broadcast = args.mode, None, None
    if mode in ("auto", "drone"):
        clip, report, _ = run_drone(args, args.id or stem, title, length_m, width_m)
        print(f"\r  drone checks done in {time.perf_counter() - start:.0f} s{' ' * 40}\n{report.summary()}")
        failed = {c.name for c in report.checks if not c.passed and c.blocking}
        if clip is None and mode == "auto" and failed & NOT_A_FIXED_VIEW:
            print("No fixed view of the whole pitch: trying the broadcast-camera path.")
            mode = "broadcast"
        else:
            mode = "drone"
    if mode == "broadcast":
        clip_id = args.id or f"local-{stem}"
        broadcast = run_broadcast(args, clip_id, title)
        clip, report = broadcast.clip, broadcast.report
        print(f"\r  done in {time.perf_counter() - start:.0f} s{' ' * 50}\n{report.summary()}")
    if clip is None:
        print("This clip is not suitable; nothing was written.")
        return 1

    folder = save_clip(clip, ROOT / "clips")
    if broadcast is not None:  # what the on-video overlay draws (and the hand-label evaluation measures)
        broadcast.camera.to_parquet(folder / "camera.parquet", index=False)
        broadcast.people.to_parquet(folder / "detections.parquet", index=False)
        broadcast.ball.to_parquet(folder / "ball_track.parquet", index=False)
    problems = find_problems(clip.players, clip.ball)
    print(f"Saved {folder.relative_to(ROOT)} ({len(clip.ball)} frames).", *[f"PROBLEM: {p}" for p in problems], sep="\n")
    if args.render and mode == "broadcast":
        from tactics.broadcast.frames import iter_frames
        from tactics.viz.overlay import render_overlay
        written = render_overlay(iter_frames(args.video), clip, broadcast.camera, broadcast.people, broadcast.ball,
                                 folder / "video.mp4")
        print(f"Rendered {folder.relative_to(ROOT)}/video.mp4 ({written} frames).")
    elif args.render:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "render_clip.py"), "--for-app", clip.meta["clip_id"]], check=True)
    if args.explain:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_explanations.py"), clip.meta["clip_id"]], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
