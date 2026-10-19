"""Check (and fix) how a drone clip's positions sit on its video: never mirrored, and turned like the video.

    uv run --group video python scripts/fix_drone_orientation.py drone-1110-1140 data/raw/.../D_20220220_1_1110_1140.mp4

Before the calibration fix (DECISIONS D33), a clip could come out as the mirror image of the real pitch, because
the pitch outline alone does not say which corner is which. This script finds out empirically: it places the clip's
positions on a few video frames in each of the four symmetries of the pitch (as is, mirrored in x, mirrored in y,
turned 180 degrees) and keeps the one that lands on the moving players. A mirrored clip is reflected (y -> -y),
its facts are rebuilt, and meta.video_rotation records how to turn the drawn pitch to look like the video.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from tactics.ai.summary import build_summary
from tactics.data.clips import load_clip, save_clip
from tactics.service import clip_folder
from tactics.video.pitch_lines import auto_calibrate, view_rotation

SCALE = 0.5
SYMMETRIES = {"as is": (1, 1), "mirror x": (-1, 1), "mirror y": (1, -1), "turned 180": (-1, -1)}


def frames_at(video: Path, seconds: list[float]) -> tuple[list[np.ndarray], float]:
    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS)
    out = []
    for s in seconds:
        capture.set(cv2.CAP_PROP_POS_FRAMES, round(s * fps))
        ok, frame = capture.read()
        if ok:
            out.append(cv2.resize(frame, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA))
    capture.release()
    return out, fps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip_id")
    parser.add_argument("video", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = parser.parse_args()

    folder = clip_folder(args.clip_id)
    clip = load_clip(folder)
    duration = float(clip.ball["time_s"].max() - clip.meta["start_s"])
    background_frames, fps = frames_at(args.video, list(np.linspace(0, duration, 31)))
    background = np.median(np.stack(background_frames), axis=0).astype(np.uint8)
    calibration = auto_calibrate(background, image_scale=SCALE)   # the fixed, never-mirrored calibration

    test_times = [duration * f for f in (0.2, 0.45, 0.7, 0.9)]
    frames, _ = frames_at(args.video, test_times)
    scores = {name: [] for name in SYMMETRIES}
    for t, frame in zip(test_times, frames):
        moving = (np.abs(frame.astype(int) - background.astype(int)).sum(axis=2) > 45).astype(np.uint8)
        moving = cv2.dilate(moving, np.ones((7, 7), np.uint8))
        time_s = clip.meta["start_s"] + t
        nearest = clip.players.loc[(clip.players["time_s"] - time_s).abs().idxmin(), "time_s"]
        here = clip.players[clip.players["time_s"] == nearest][["x", "y"]].to_numpy(float)
        for name, (sx, sy) in SYMMETRIES.items():
            px = calibration.from_pitch(here * [sx, sy]) * SCALE
            inside = [moving[int(v), int(u)] for u, v in px if 0 <= int(v) < moving.shape[0] and 0 <= int(u) < moving.shape[1]]
            scores[name].append(float(np.mean(inside)) if inside else 0.0)
    mean = {name: round(float(np.mean(v)), 3) for name, v in scores.items()}
    best = max(mean, key=mean.get)
    mirrored = best in ("mirror x", "mirror y")
    # after reflecting y, "mirror y" becomes "as is" and "mirror x" becomes "turned 180"
    turned = best in ("turned 180", "mirror x")
    rotation = (view_rotation(calibration) + (180 if turned else 0)) % 360
    print(json.dumps({"clip": args.clip_id, "share_on_players": mean, "best": best, "mirrored": mirrored,
                      "video_rotation": rotation}))
    if args.dry_run:
        return
    if mirrored:
        clip.players["y"] = -clip.players["y"]
        clip.ball["y"] = -clip.ball["y"]
    clip.meta["video_rotation"] = rotation
    save_clip(clip, folder.parent)
    if mirrored or (folder / "summary.json").exists():
        (folder / "summary.json").write_text(json.dumps(build_summary(clip), indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
