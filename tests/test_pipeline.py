"""End-to-end tests of the drone-video pipeline on small synthetic videos with known answers.

Skipped unless OpenCV is installed (`uv sync --group video`, or headless OpenCV in CI).
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from tactics.video.pipeline import QualityReport, process_video  # noqa: E402

SCALE, OFFSET = 8.0, (60, 40)  # px per metre; pitch drawn 60 px / 40 px from the image edge
GRASS, LINE = (60, 140, 60), (255, 255, 255)
SHIRTS = {"A": (235, 235, 235), "B": (190, 90, 40)}  # BGR: white and blue


def px(x_m: float, y_m: float) -> tuple[int, int]:
    """Pitch metres (corner origin, 105 x 68) -> image pixels."""
    return int(round(OFFSET[0] + x_m * SCALE)), int(round(OFFSET[1] + y_m * SCALE))


def draw_pitch(height: int, width: int) -> np.ndarray:
    rng = np.random.default_rng(0)
    image = np.full((height, width, 3), GRASS, np.uint8)
    image = cv2.add(image, cv2.GaussianBlur(rng.integers(0, 40, image.shape, dtype=np.uint8), (31, 31), 0))
    cv2.rectangle(image, px(0, 0), px(105, 68), LINE, 3)
    cv2.line(image, px(52.5, 0), px(52.5, 68), LINE, 3)
    cv2.circle(image, px(52.5, 34), int(9.15 * SCALE), LINE, 3)
    cv2.rectangle(image, px(0, 13.84), px(16.5, 54.16), LINE, 3)
    cv2.rectangle(image, px(88.5, 13.84), px(105, 54.16), LINE, 3)
    return image


def write_video(path, seconds: float = 12.0, fps: float = 10.0, crop_right_m: float = 0.0) -> None:
    """22 players jogging on circles around fixed spots, plus a ball; optionally cut off part of the pitch."""
    height, width = int(68 * SCALE + 2 * OFFSET[1]), int(105 * SCALE + 2 * OFFSET[0])
    pitch = draw_pitch(height, width)
    rng = np.random.default_rng(1)
    homes = {"A": rng.uniform([8, 6], [50, 62], (11, 2)), "B": rng.uniform([55, 6], [97, 62], (11, 2))}
    homes["A"][0] = (3, 34)  # keepers near their goals
    homes["B"][0] = (102, 34)
    keep_width = width - int(crop_right_m * SCALE)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (keep_width, height))
    for i in range(int(seconds * fps)):
        t = i / fps
        frame = pitch.copy()
        for team, spots in homes.items():
            for k, (x, y) in enumerate(spots):
                angle = t * 0.8 + k
                cv2.circle(frame, px(x + 3 * np.cos(angle), y + 3 * np.sin(angle)), 7, SHIRTS[team], -1)
        cv2.circle(frame, px(52.5 + 20 * np.sin(t / 2), 34 + 10 * np.cos(t / 3)), 3, (250, 250, 250), -1)
        writer.write(frame[:, :keep_width])
    writer.release()


def test_quality_report_status():
    report = QualityReport()
    report.add("a", True, "1", ">= 1")
    assert report.status == "ok"
    report.add("b", False, "0", ">= 1", blocking=False)
    assert report.status == "warning"
    report.add("c", False, "0", ">= 1")
    assert report.status == "rejected" and "FAIL" in report.summary()


def test_pipeline_end_to_end_on_a_synthetic_clip(tmp_path):
    video = tmp_path / "clip.mp4"
    write_video(video)
    clip, report = process_video(video, "synthetic", "Synthetic clip")

    assert report.status in ("ok", "warning"), report.summary()
    assert clip is not None
    per_team = clip.players.groupby(["frame", "team"]).size().groupby("team").median()
    assert per_team.min() >= 9  # most of the 11 players per team are found and tracked
    # Players stay on the pitch (metres, centre origin) and the keepers end up in their own halves.
    assert clip.players["x"].abs().max() < 56 and clip.players["y"].abs().max() < 37
    keepers = clip.players[clip.players["position"] == "Goalkeeper"].groupby("team")["x"].mean()
    if len(keepers) == 2:
        assert keepers["home"] < 0 < keepers["away"]


def test_pipeline_rejects_a_short_clip(tmp_path):
    video = tmp_path / "short.mp4"
    write_video(video, seconds=4.0)
    clip, report = process_video(video, "short", "Too short")
    assert clip is None and report.status == "rejected"
    assert not next(c for c in report.checks if c.name == "clip length").passed


def test_pipeline_rejects_a_clip_without_the_whole_pitch(tmp_path):
    video = tmp_path / "cropped.mp4"
    write_video(video, crop_right_m=30.0)  # the right goal line and a third of the pitch are out of view
    clip, report = process_video(video, "cropped", "Cropped")
    assert clip is None and report.status == "rejected", report.summary()
