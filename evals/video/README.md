# Drone video → tracking: evaluation across the match

Generated from `segments.csv`, which `scripts/video_to_tracks.py all` writes. The script runs **the same `process_video` pipeline that builds clips** (`src/tactics/video/pipeline.py`) on SoccerTrack top-view segments of 30 s each from one university match:
- **13 tuned segments:** spread over the 30 minutes and used while building the pipeline.
- **2 unseen segments (0:00 and 18:30):** never used for tuning.

- **Positions** come only from the video. Frame rate and length are read from the file, and the pitch is calibrated from its lines (D20, D23, D24, D26, D27). During processing the unseen segment's ground-truth file was moved out of the data folder.
- **The ground truth is used only afterwards**, for scoring (`src/tactics/video/scoring.py`). A detection counts as matched within 1.5 m.
- **Ground truth in metres (D30):**
  - SoccerTrack has one pitch calibration for the whole match, but the drone drifts. Drawn on each segment, its pitch lines land on the paint only 37–88% of the time.
  - Each segment therefore gets the dataset's keypoints moved to it by image registration (`scripts/truth_calibration.py`); these land on the paint 87–89% of the time in every segment ([truth_calibration.csv](truth_calibration.csv)).
  - Scores with the original single calibration are kept in `segments_dataset_truth.csv`.
- Every segment passed the pipeline's own quality report. Code: after D27. For edited copies (rotated, cropped, darker, 1080p, 25 fps), see [robustness.md](robustness.md).

| Segment | Quality | Players found | Position error (auto calibration) | Identity purity | Team correct | Ball correct |
|---|---|---|---|---|---|---|
| 0:00 (unseen) | ok | 96.3% | 0.55 m | 91.4% | 91.9% | 41.9% |
| 0:30 | ok | 98.4% | 0.52 m | 95.1% | 99.0% | 69.9% |
| 2:30 | ok | 98.9% | 0.49 m | 99.2% | 95.0% | 59.8% |
| 5:00 | ok | 99.6% | 0.45 m | 99.7% | 99.7% | 40.8% |
| 7:30 | ok | 98.1% | 0.25 m | 98.7% | 94.3% | 57.7% |
| 10:00 | ok | 98.2% | 0.28 m | 96.4% | 98.2% | 63.4% |
| 12:30 | ok | 99.7% | 0.30 m | 99.9% | 99.9% | 67.4% |
| 15:00 | ok | 97.7% | 0.32 m | 91.5% | 97.4% | 61.7% |
| 17:30 | ok | 99.0% | 0.32 m | 97.8% | 99.6% | 73.4% |
| 18:30 (unseen) | ok | 99.1% | 0.44 m | 96.7% | 92.7% | 67.7% |
| 20:00 | ok | 100.0% | 0.34 m | 100.0% | 100.0% | 33.9% |
| 22:30 | ok | 99.5% | 0.35 m | 96.5% | 97.2% | 70.2% |
| 25:00 | ok | 98.1% | 0.39 m | 95.6% | 98.5% | 59.0% |
| 27:30 | ok | 98.1% | 0.35 m | 96.3% | 97.0% | 67.1% |
| 29:30 | ok | 98.6% | 0.36 m | 97.4% | 97.5% | 71.9% |
| **median, 13 tuned segments** | | **98.6%** | **0.35 m** | **97.4%** | **98.2%** | **63.4%** |
| worst, 13 tuned segments | | 97.7% | 0.52 m | 91.5% | 94.3% | 33.9% |

**What changed with the corrected ground truth:**
- The tuned median position error falls from 0.49 m to 0.35 m.
- The unseen 18:30 segment goes from 68.5% found and 0.82 m to 99.1% and 0.44 m: most of the earlier error was the drifted ground-truth calibration, not the pipeline.
- The weakest segment is unseen 0:00: 96.3% found, 0.55 m, teams 91.9%.

## Ball: full-resolution detector (D25)

"Ball correct" = share of all frames in which our ball is within 1 m of the real one.

| Segment | Used for tuning? | Old (half-res blobs) | New (full-res, near-player demotion) |
|---|---|---|---|
| 0:30 | yes | 70.0% | 82.1% |
| 5:00 | yes | 40.7% | 63.1% |
| 10:00 | yes | 61.0% | 65.0% |
| 2:30 | **no** | 63.7% | **97.3%** |
| 7:30 | **no** | 60.1% | **77.2%** |
| 12:30 | **no** | 67.4% | **38.0%** |

The new detector finds a ball-like blob near the real ball far more often: 79–97% of frames, against 41–75% before. The follower is better on 5 of 6 segments, but on 12:30 it locks onto the wrong blobs. The new detector is therefore **not yet used** in the app's drone clip.
