# Drone video → tracking: evaluation across the match

Generated from `segments.csv`, which `scripts/video_to_tracks.py all` writes. There are 13 SoccerTrack top-view segments of 30 s each, spread over the 30 minutes of one university match.

- **Positions** come only from the video. Pitch calibration and the detection pitch area come from our automatic calibration (D20, D23, D24).
- **The dataset's ground truth** (boxes and its own calibration) is used only for scoring. A detection counts as matched within 1.5 m.

| Segment | Players found | Position error (auto calibration) | Identity purity | Team correct | Ball correct |
|---|---|---|---|---|---|
| 0:30 | 98.4% | 0.55 m | 95.1% | 94.4% | 70.0% |
| 2:30 | 92.0% | 0.80 m | 99.4% | 95.2% | 63.7% |
| 5:00 | 99.5% | 0.43 m | 99.6% | 99.6% | 40.7% |
| 7:30 | 98.0% | 0.59 m | 98.8% | 94.5% | 60.1% |
| 10:00 | 98.2% | 0.51 m | 96.1% | 97.8% | 61.0% |
| 12:30 | 99.7% | 0.36 m | 99.7% | 99.7% | 67.4% |
| 15:00 | 97.7% | 0.36 m | 94.9% | 98.9% | 61.3% |
| 17:30 | 98.8% | 0.65 m | 97.6% | 99.5% | 59.9% |
| 20:00 | 100.0% | 0.57 m | 100.0% | 100.0% | 13.7% |
| 22:30 | 99.5% | 0.59 m | 99.8% | 99.8% | 68.9% |
| 25:00 | 98.1% | 0.44 m | 96.3% | 99.5% | 58.9% |
| 27:30 | 98.1% | 0.37 m | 98.5% | 99.1% | 66.8% |
| 29:30 | 98.6% | 0.47 m | 97.5% | 97.6% | 72.2% |
| **median** | **98.4%** | **0.51 m** | **98.5%** | **99.1%** | **61.3%** |
| worst | 92.0% | 0.80 m | 94.9% | 94.4% | 13.7% |

Segments 15:00, 17:30 and 20:00 were scored before the D24 calibration fix. Their automatic calibration was already correct then (98–100% found), so the fix does not change them. They were not re-run because of time and laptop heat.

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
