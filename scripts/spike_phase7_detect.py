"""Phase 7 spike: which detector finds players best in top-view drone video?

    uv run --group video python scripts/spike_phase7_detect.py                       # both approaches, first segment
    uv run --group video python scripts/spike_phase7_detect.py background 0300_0330  # approach B on another segment

Uses one 30 s SoccerTrack top-view segment in data/raw/soccertrack/ and its
annotation boxes as ground truth (the box centre is the player's position).
Reports recall, precision, position error in metres and speed, and saves a
picture of detections vs ground truth for one frame to outputs/.
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np

from tactics.video.calibration import PitchCalibration
from tactics.video.detect import BackgroundDetector, RFDetrDetector, Stabilizer, pitch_mask, read_frames
from tactics.video.evaluate import combine, match
from tactics.video.pitch_lines import auto_calibrate
from tactics.video.soccertrack import load_boxes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "soccertrack"
DEFAULT_SEGMENT = "0030_0060"
EVAL_FRAMES = list(range(0, 900, 90))  # 10 frames, 3 s apart (0-based video indices)
BACKGROUND_FRAMES = list(range(0, 900, 15))  # 60 frames spread over the clip
MATCH_RADIUS_M = 1.5


def main(approaches: list[str], segment: str) -> None:
    segment = f"D_20220220_1_{segment}"
    calibration = PitchCalibration.from_file(DATA / "drone_keypoints.json")
    video = DATA / "top_view" / "videos" / f"{segment}.mp4"
    truth = load_boxes(DATA / "top_view" / "annotations" / f"{segment}.csv")
    truth = truth[truth["team"] != "BALL"]

    frames = read_frames(video, EVAL_FRAMES)
    # The calibration matches frame 0 (checked visually), so frame 0 is the reference for stabilisation.
    stabilizer = Stabilizer(frames[0])
    warps = {index: stabilizer.warp(frame) for index, frame in frames.items()}
    shape = frames[0].shape[:2]
    detectors = {}
    if "background" in approaches:
        start = time.perf_counter()
        background = [Stabilizer.align(f, stabilizer.warp(f)) for f in read_frames(video, BACKGROUND_FRAMES).values()]
        detectors["background"] = BackgroundDetector(background, np.full(shape, 255, dtype=np.uint8))
        print(f"background model from {len(BACKGROUND_FRAMES)} aligned frames in {time.perf_counter() - start:.1f} s")
        auto = auto_calibrate(detectors["background"].background, image_scale=detectors["background"].scale)
        # The pitch area for detection comes from our automatic calibration, not the dataset's keypoints.
        detectors["background"].mask = detectors["background"]._resize(pitch_mask(shape, auto))
    mask = pitch_mask(shape, auto) if "background" in approaches else pitch_mask(shape, calibration)
    if "rfdetr" in approaches:
        detectors["rfdetr"] = RFDetrDetector()

    for name, detector in detectors.items():
        results, seconds = [], []
        for index, frame in frames.items():
            start = time.perf_counter()
            if name == "background":
                found = detector.detect(Stabilizer.align(frame, warps[index]))  # reference coordinates
            else:
                found = Stabilizer.to_reference(detector.detect(frame), warps[index])
            seconds.append(time.perf_counter() - start)
            found = found[mask[found[:, 1].astype(int).clip(0, mask.shape[0] - 1),
                               found[:, 0].astype(int).clip(0, mask.shape[1] - 1)] > 0] if len(found) else found
            # Annotation frames start at 1 and are in raw frame pixels: move them to reference pixels too.
            real = Stabilizer.to_reference(truth[truth["frame"] == index + 1][["cx", "cy"]].to_numpy(), warps[index])
            results.append(match(calibration.to_pitch(found) if len(found) else found,
                                 calibration.to_pitch(real), MATCH_RADIUS_M))
            if index == EVAL_FRAMES[6]:  # frame 540: the largest drift
                save_picture(Stabilizer.align(frame, warps[index]), found, real, ROOT / "outputs" / f"phase7_{name}_{segment[-9:]}.png")
        if name == "background":
            report_auto_calibration(auto, calibration, detector, frames, warps, truth, mask)
        total = combine(results)
        print(f"{segment[-9:]} {name:10} recall {total.recall:6.1%}  precision {total.precision:6.1%}  "
              f"position error mean {total.errors.mean():.2f} m (p90 {np.percentile(total.errors, 90):.2f} m)  "
              f"{np.mean(seconds):.2f} s/frame  [{total.true_positives} found, {total.false_negatives} missed, "
              f"{total.false_positives} false, {len(frames)} frames]")


def report_auto_calibration(auto, reference, detector, frames, warps, truth, mask) -> None:
    """Raw-footage test: positions from the automatic calibration vs ground truth from the dataset's calibration.

    The outline cannot tell the goals apart, so the auto result is compared under the best mirror.
    """
    found_m, truth_m = [], []
    for index, frame in frames.items():
        found = detector.detect(Stabilizer.align(frame, warps[index]))
        found = found[mask[found[:, 1].astype(int).clip(0, mask.shape[0] - 1), found[:, 0].astype(int).clip(0, mask.shape[1] - 1)] > 0]
        real = Stabilizer.to_reference(truth[truth["frame"] == index + 1][["cx", "cy"]].to_numpy(), warps[index])
        found_m.append(auto.to_pitch(found))
        truth_m.append(reference.to_pitch(real))
    best = None
    for mirror in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        total = combine([match(f * mirror, t, MATCH_RADIUS_M) for f, t in zip(found_m, truth_m)])
        if best is None or total.true_positives > best[1].true_positives:
            best = (mirror, total)
    mirror, total = best
    print(f"           AUTO calibration (no dataset points; mirror {mirror}): recall {total.recall:6.1%}  "
          f"precision {total.precision:6.1%}  position error mean {total.errors.mean():.2f} m "
          f"(p90 {np.percentile(total.errors, 90):.2f} m)")


def save_picture(frame: np.ndarray, found: np.ndarray, real: np.ndarray, path: Path) -> None:
    """Green circles: ground truth; red crosses: detections."""
    image = frame.copy()
    for x, y in real:
        cv2.circle(image, (int(x), int(y)), 30, (0, 255, 0), 4)
    for x, y in found:
        cv2.drawMarker(image, (int(x), int(y)), (0, 0, 255), cv2.MARKER_CROSS, 40, 4)
    path.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(path), cv2.resize(image, None, fx=0.5, fy=0.5))


if __name__ == "__main__":
    args = sys.argv[1:]
    segments = [a for a in args if a[:1].isdigit()] or [DEFAULT_SEGMENT]
    names = [a for a in args if not a[:1].isdigit()] or ["background", "rfdetr"]
    for seg in segments:
        main(names, seg)
