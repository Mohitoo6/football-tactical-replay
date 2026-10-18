"""Per-segment ground-truth calibration for SoccerTrack (evaluation only).

    uv run --group video python scripts/truth_calibration.py            # every downloaded segment

SoccerTrack gives ONE set of pitch keypoints (drone_keypoints.json) for the whole match, but the
hovering drone slowly moves and turns over 30 minutes. Drawn on segment 18:30, the dataset's pitch
lines landed on the painted lines only 38% of the time (D30), so its "true" positions there are off
by 1-2 m. To score fairly we move the dataset's keypoints to each segment:

1. An empty-pitch image (median of 60 frames) per segment, cached in data/processed/soccertrack/backgrounds.
2. The reference segment is the one where the dataset's lines sit best on the painted lines.
3. Each segment is registered to the reference with ORB features and a RANSAC homography over the
   whole image (pitch lines, fences, goals, buildings). This does not use our pitch-line calibration.
4. The dataset's image keypoints are moved through that homography and saved per segment in
   data/processed/soccertrack/truth_calibration/<segment>.json, which the scoring then uses.

Every calibration is checked by drawing its pitch lines on the segment's empty pitch and measuring the
share that lands on white paint ("on paint"). Results go to evals/video/truth_calibration.csv.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.video.calibration import PITCH_LENGTH_M, PITCH_WIDTH_M, PitchCalibration
from tactics.video.detect import BackgroundDetector, Stabilizer, read_frames
from tactics.video.pipeline import BACKGROUND_SAMPLES, video_info
from tactics.video.pitch_lines import auto_calibrate, line_pixels, pitch_line_points

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "soccertrack"
PREFIX = "D_20220220_1_"
OUT = ROOT / "data" / "processed" / "soccertrack"
SCALE = 0.5  # backgrounds are stored at half resolution


def background(segment: str) -> np.ndarray:
    """Empty-pitch image of a segment at half resolution (cached)."""
    path = OUT / "backgrounds" / f"{segment}.png"
    if path.exists():
        return cv2.imread(str(path))
    video = DATA / "top_view" / "videos" / f"{PREFIX}{segment}.mp4"
    fps, count, (h, w) = video_info(video)
    indices = np.linspace(0, count - 1, BACKGROUND_SAMPLES).astype(int).tolist()
    sample = read_frames(video, indices)
    stabilizer = Stabilizer(sample[indices[0]])
    aligned = [Stabilizer.align(f, stabilizer.warp(f)) for f in sample.values()]
    image = BackgroundDetector(aligned, np.full((h, w), 255, np.uint8), scale=SCALE).background
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return image


def on_paint(calibration: PitchCalibration, image: np.ndarray, tolerance_px: float = 4.0) -> float:
    """Share of the calibration's pitch lines (drawn on the half-resolution image) within tolerance of white paint."""
    distance = cv2.distanceTransform(255 - line_pixels(image), cv2.DIST_L2, 3)
    height, width = image.shape[:2]
    hits = total = 0
    for points in pitch_line_points(0.5):
        px = calibration.from_pitch(points) * SCALE
        inside = (px[:, 0] >= 0) & (px[:, 0] < width) & (px[:, 1] >= 0) & (px[:, 1] < height)
        xy = px[inside].astype(int)
        total += len(xy)
        hits += int((distance[xy[:, 1], xy[:, 0]] <= tolerance_px).sum())
    return hits / max(total, 1)


def register(reference: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Homography mapping reference-image pixels to target-image pixels (full resolution), from ORB features."""
    orb = cv2.ORB_create(nfeatures=8000)
    grey = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) for img in (reference, target)]
    (kp1, d1), (kp2, d2) = (orb.detectAndCompute(g, None) for g in grey)
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    src = np.float32([kp1[m.queryIdx].pt for m in matches]) / SCALE
    dst = np.float32([kp2[m.trainIdx].pt for m in matches]) / SCALE
    homography, _ = cv2.findHomography(src, dst, cv2.RANSAC, 3.0 / SCALE)
    return homography


def main() -> int:
    segments = sorted(p.stem.removeprefix(PREFIX) for p in (DATA / "top_view" / "videos").glob(f"{PREFIX}*.mp4"))
    dataset = PitchCalibration.from_file(DATA / "drone_keypoints.json")
    pitch_corner_origin = dataset.pitch_m + [PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2]
    images = {}
    for segment in segments:
        print(f"empty pitch for {segment}", flush=True)
        images[segment] = background(segment)
    as_given = {s: on_paint(dataset, images[s]) for s in segments}
    reference = max(as_given, key=as_given.get)
    print(f"reference segment: {reference} (dataset lines on paint {as_given[reference]:.0%})")

    rows = []
    for segment in segments:
        moved = cv2.perspectiveTransform(dataset.other.reshape(-1, 1, 2), register(images[reference], images[segment])).reshape(-1, 2)
        corrected = PitchCalibration(pitch_corner_origin, moved)
        ours = auto_calibrate(images[segment], image_scale=SCALE)
        out = OUT / "truth_calibration" / f"{segment}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({str(tuple(map(float, p))): list(map(float, q)) for p, q in zip(pitch_corner_origin, moved)}))
        rows.append({"segment": segment, "dataset_on_paint": as_given[segment], "corrected_on_paint": on_paint(corrected, images[segment]),
                     "ours_on_paint": on_paint(ours, images[segment])})
        print(f"{segment}: on paint - dataset {rows[-1]['dataset_on_paint']:.0%}, corrected {rows[-1]['corrected_on_paint']:.0%}, "
              f"ours {rows[-1]['ours_on_paint']:.0%}", flush=True)
    pd.DataFrame(rows).round(3).to_csv(ROOT / "evals" / "video" / "truth_calibration.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
