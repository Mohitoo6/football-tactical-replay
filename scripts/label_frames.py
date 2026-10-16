"""Hand-label a broadcast clip so the tracking can be measured (ball every second, all people on 5 frames).

    uv run --group video python scripts/label_frames.py path/to/clip.mov --id local-euro-copenhagen

Part 1, ball: one frame per second. Click the ball's centre, or press N if it is not visible.
Part 2, people: five frames. Click the feet (the point on the grass between the feet) of every person
on the pitch (players, goalkeepers, referees), then press ENTER for the next frame.
Keys (shown on screen): B = back one frame, U = undo the last click (people), Q = save and quit
(running it again continues where you stopped). Saves data/processed/labels/<id>.json
(coordinates only; git-ignored like the clip).
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from tactics.broadcast.frames import VIDEO_FPS, iter_frames

ROOT = Path(__file__).resolve().parents[1]
SHOW_WIDTH = 1440  # the window shows frames scaled to this width; clicks are mapped back to 1920 x 1080
PEOPLE_SECONDS = (4, 12, 20, 28, 36)


BACK = "back"


def ask(window: str, frame: np.ndarray, title: str, keys: str, many: bool):
    """Clicks on one frame in full-frame pixels; None if Q was pressed, BACK if B was pressed."""
    scale = SHOW_WIDTH / frame.shape[1]
    clicks: list[list[float]] = []
    shown_at = time.monotonic()

    def on_mouse(event, x, y, flags, param):
        # Ignore clicks in the first 0.3 s: a double click must not also label the next frame.
        if event == cv2.EVENT_LBUTTONDOWN and time.monotonic() - shown_at > 0.3:
            clicks.append([x / scale, y / scale])

    cv2.setMouseCallback(window, on_mouse)
    while True:
        shown = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        for x, y in clicks:
            cv2.circle(shown, (int(x * scale), int(y * scale)), 7, (0, 255, 255), 2)
        cv2.rectangle(shown, (0, 0), (shown.shape[1], 64), (0, 0, 0), -1)
        cv2.putText(shown, f"{title}   (clicks: {len(clicks)})", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(shown, keys, (10, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imshow(window, shown)
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), ord("Q")):
            return None
        if key in (ord("b"), ord("B")):
            return BACK
        if key in (ord("u"), ord("U")) and clicks:
            clicks.pop()
        if not many and clicks:
            cv2.waitKey(250)  # let the yellow circle show for a moment
            return clicks
        if not many and key in (ord("n"), ord("N")):
            return []
        if many and key in (13, 10):  # ENTER
            return clicks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    parser.add_argument("--id", required=True, help="clip id the labels belong to, e.g. local-euro-copenhagen")
    args = parser.parse_args()

    out = ROOT / "data" / "processed" / "labels" / f"{args.id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    labels = json.loads(out.read_text()) if out.exists() else {"clip_id": args.id, "fps": VIDEO_FPS, "ball": {}, "people": {}}
    step = int(VIDEO_FPS)
    frames = {j: f.copy() for j, f in enumerate(iter_frames(args.video)) if j % step == 0}
    window = "label"
    cv2.namedWindow(window)

    # Part 1: the ball, one frame per second. B goes back one frame to redo it.
    ball_frames = list(frames)
    i = next((n for n, j in enumerate(ball_frames) if str(j) not in labels["ball"]), len(ball_frames))
    quit_now = False
    while i < len(ball_frames):
        j = ball_frames[i]
        answer = ask(window, frames[j], f"BALL  {i + 1}/{len(ball_frames)}: click the ball",
                     "N = ball not visible   B = back one frame   Q = save and quit", many=False)
        if answer is None:
            quit_now = True
            break
        if answer == BACK:
            i = max(i - 1, 0)
            labels["ball"].pop(str(ball_frames[i]), None)
            continue
        labels["ball"][str(j)] = answer[0] if answer else None
        out.write_text(json.dumps(labels))
        i += 1

    # Part 2: every person's feet on a few frames. B goes back to the previous frame.
    people_frames = [s * step for s in PEOPLE_SECONDS if s * step in frames]
    i = next((n for n, j in enumerate(people_frames) if str(j) not in labels["people"]), len(people_frames))
    while not quit_now and i < len(people_frames):
        j = people_frames[i]
        answer = ask(window, frames[j], f"PEOPLE {i + 1}/{len(people_frames)}: click every person's feet",
                     "ENTER = done with this frame   U = undo click   B = back one frame   Q = save and quit", many=True)
        if answer is None:
            break
        if answer == BACK:
            i = max(i - 1, 0)
            labels["people"].pop(str(people_frames[i]), None)
            continue
        labels["people"][str(j)] = answer
        out.write_text(json.dumps(labels))
        i += 1
    cv2.destroyAllWindows()
    out.write_text(json.dumps(labels))
    print(f"Saved {out.relative_to(ROOT)}: ball in {len(labels['ball'])} frames, people in {len(labels['people'])} frames.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
