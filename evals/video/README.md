# Drone video → tracking: evaluation across the match

Generated from `segments.csv`, which `scripts/video_to_tracks.py all` writes. The script runs **the same `process_video` pipeline that builds clips** (`src/tactics/video/pipeline.py`) on 13 SoccerTrack top-view segments of 30 s each, spread over the 30 minutes of one university match.

- **Positions** come only from the video: frame rate and length are read from the file, and the pitch is calibrated from its lines (D20, D23, D24, D26).
- **The dataset's ground truth** is used only afterwards, for scoring (`src/tactics/video/scoring.py`). A detection counts as matched within 1.5 m.
- Every segment passed the pipeline's own quality report. Processing took ~2 min per 30 s of 4K video on an Apple M2.
- This table was made with the D26 code. For edited copies (rotated, cropped, darker, 1080p, 25 fps) and the calibration fixes they led to (D27), see [robustness.md](robustness.md).

| Segment | Quality | Players found | Position error (auto calibration) | Identity purity | Team correct | Ball correct |
|---|---|---|---|---|---|---|
| 0:30 | ok | 98.4% | 0.51 m | 95.1% | 99.0% | 69.9% |
| 2:30 | ok | 91.0% | 0.81 m | 99.2% | 99.6% | 59.9% |
| 5:00 | ok | 99.6% | 0.42 m | 99.7% | 99.7% | 40.8% |
| 7:30 | ok | 98.0% | 0.58 m | 98.7% | 94.3% | 57.7% |
| 10:00 | ok | 98.2% | 0.49 m | 96.4% | 98.2% | 61.1% |
| 12:30 | ok | 99.7% | 0.40 m | 99.9% | 99.9% | 67.4% |
| 15:00 | ok | 97.7% | 0.35 m | 90.2% | 97.4% | 61.7% |
| 17:30 | ok | 98.8% | 0.64 m | 99.0% | 99.6% | 73.4% |
| 20:00 | ok | 100.0% | 0.56 m | 100.0% | 100.0% | 14.4% |
| 22:30 | ok | 99.5% | 0.59 m | 96.5% | 97.2% | 70.2% |
| 25:00 | ok | 98.1% | 0.43 m | 95.6% | 98.5% | 59.0% |
| 27:30 | ok | 98.1% | 0.38 m | 96.3% | 97.0% | 67.1% |
| 29:30 | ok | 98.6% | 0.47 m | 97.4% | 97.5% | 71.9% |
| **median** | | **98.4%** | **0.49 m** | **97.4%** | **98.5%** | **61.7%** |
| worst | | 91.0% | 0.81 m | 90.2% | 94.3% | 14.4% |

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
