"""Read a broadcast clip as evenly timed 1920x1080 frames.

Screen recordings and phone videos often have a variable frame rate (one test
recording was labelled 60 fps but averaged 36). ffmpeg's fps filter resamples to
an exact rate, so frame k is at k / fps seconds. Other aspect ratios are padded
(never stretched) to 16:9, because the calibration model expects 16:9 frames and
stretching would bend the camera geometry.
"""

import subprocess
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT = 1920, 1080
KEY_FPS = 5.0  # frames per second that are calibrated and searched for players
VIDEO_FPS = 25.0  # frames per second of the output clip and overlay video
MIN_GREEN_SHARE = 0.3  # below this a frame is not a view of the pitch (intro screen, close-up, crowd)


def _filter(fps: float) -> str:
    return (f"fps={fps},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2")


def extract_keyframes(video: Path, folder: Path, fps: float = KEY_FPS) -> list[Path]:
    """Write frames at `fps` as folder/00000.jpg, 00001.jpg, ... (frame k is at k / fps seconds)."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", _filter(fps), "-q:v", "3",
                    "-start_number", "0", str(folder / "%05d.jpg")], check=True)
    return sorted(folder.glob("*.jpg"))


def iter_frames(video: Path, fps: float = VIDEO_FPS) -> Iterator[np.ndarray]:
    """Decode the video at exactly `fps`, as BGR frames of WIDTH x HEIGHT."""
    process = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", _filter(fps), "-f", "rawvideo",
                                "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)  # closing early (enough frames read) is not an error
    size = WIDTH * HEIGHT * 3
    try:
        while True:
            data = process.stdout.read(size)
            if len(data) < size:
                break
            yield np.frombuffer(data, np.uint8).reshape(HEIGHT, WIDTH, 3)
    finally:
        process.stdout.close()
        process.kill()
        process.wait()


def green_share(frame: np.ndarray) -> float:
    """Share of the frame that is grass-green (a wide view of the pitch is mostly green)."""
    hsv = cv2.cvtColor(cv2.resize(frame, (480, 270), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    return float((cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) > 0).mean())
