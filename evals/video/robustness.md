# Drone video → tracking: robustness to how clips differ

Generated from `robustness.csv`, which `scripts/robustness.py` writes.

**What it tests.** Real clips will not look exactly like the SoccerTrack footage the pipeline was built on. So we edit one segment (10:00–10:30) in the ways real clips differ, run the **exact production pipeline** on each copy, and score it against the ground truth moved the same way.

**How the copies are made.**
- Each copy is made with ffmpeg, using Apple's hardware encoder at the original bitrate.
- The ground truth gets the same pixel map: rotation, crop or resize, and for 25 fps the list of original frames that were kept.
- A one-frame check confirmed the maps: ground-truth points land on the same image content (colour difference 5–15 vs ~53 for wrong points), and each 25 fps frame matches the predicted original frame.

**Pass rule.** An edit passes if the pipeline either keeps working (players found ≥ 90%) or refuses the clip in its quality report. Output that is quietly wrong fails.

## Results (code after D27)

| Edit | What it simulates | Quality | Players found | Position error | Identity purity | Team correct | Ball correct | Pass |
|---|---|---|---|---|---|---|---|---|
| original | baseline | ok | 98.1% | 0.54 m | 96.4% | 98.2% | 63.4% | ✓ |
| rotate90 | drone turned a quarter (portrait pitch) | ok | 98.2% | 0.54 m | 96.6% | 97.5% | 70.1% | ✓ |
| rotate180 | drone facing the other way | ok | 98.1% | 0.54 m | 96.4% | 98.2% | 71.0% | ✓ |
| crop10 | tighter framing, pitch still fully in view | ok | 98.1% | 0.53 m | 96.7% | 98.9% | 60.0% | ✓ |
| crop_goal | 15% cut off, through one goal line | **rejected**: outline 16.7% off 105:68 | – | – | – | – | – | ✓ |
| dark30 | 30% darker (evening, cloud) | ok | 98.1% | 0.53 m | 98.4% | 99.2% | 68.9% | ✓ |
| 1080p | Full HD instead of 4K | ok | 98.1% | 0.53 m | 96.3% | 98.2% | 68.8% | ✓ |
| 720p | HD 720p (9.3 px per metre) | **rejected**: pitch resolution below 10 px/m | – | – | – | – | – | ✓ |
| 20s | a 20 s clip | ok | 97.9% | 0.55 m | 96.3% | 96.4% | 68.5% | ✓ |
| 25fps | 25 frames per second | ok | 98.1% | 0.54 m | 96.4% | 97.5% | 70.0% | ✓ |

All 10 pass. Every edit the pipeline accepts stays within 0.3 points of the baseline for players found and within 0.02 m for position error. Each run took 5–10 min in low-power mode (efficiency cores, `taskpolicy -b`, 90 s rests); the laptop never reported thermal pressure.

## What the first run found (before D27)

The first run, with the D26 code, passed only 4 of 7 edits. It found three real problems, all now fixed (DECISIONS.md, D27):

| Edit | First result | Cause | Fix |
|---|---|---|---|
| crop10, 1080p, 25fps | refused: "calibration stable over the clip" failed (one half lost the outline, or the halves differed by 52.7 m) | The two touchlines are 0.8° from parallel in the image. Pieces of one touchline were grouped by distance along the *other* line's direction, so they drifted across fixed 6 px bins. Each bin's piece then looked too short, and the line was dropped. Whether this happened depended on the exact pixel position, so it came and went with small changes | Group Hough pieces that lie on one straight line |
| dark30 | refused: "not enough long straight lines" | White paint meant brightness ≥ 170, a fixed number. On a 30% darker clip, the lines fall to ~140 | Paint = brighter than 1.17 × this pitch's median grass. That equals 170 on the original footage |
| 1080p (after the fix above) | refused: 3 player blobs per frame; 11% players found | Blob sizes are fixed in pixels, tuned on 4K at half size. At 1080p the players were 4× smaller | Process each clip at the scale that gives ~14 px per metre (measured from the calibrated outline). 4K is unchanged |
| 720p | 76% players found, only a warning | 9.3 px per metre is too coarse to separate players | The pitch-resolution check now refuses clips below 10 px/m |

Also: the first "crop10" was meant to cut through a goal line, but SoccerTrack's goal line is at 12.5% of the width, so it did not. That copy is kept as a tighter-framing test, and `crop_goal` (15%) tests the refusal.

## Honest limits

- **One segment, one ground, one match.** These edits test how clips differ in *format*. Other grounds, pitch colours, line wear, shadows across half the pitch and a tilted (not top-down) camera are untested. Those need real clips from elsewhere.
- **The 13-segment table (`segments.csv`) was made with the D26 code.** On this segment, the D27 calibration moved the position error from 0.49 m to 0.54 m (players found 98.2% → 98.1%). On saved backgrounds of all 13 segments, the pitch corners moved by at most 0.14 m, and their average distance from the dataset's corners fell from 0.74 m to 0.71 m. A full re-run of the 13 segments is still to do.
- **Edits are simulated.** A real 1080p phone or drone file has its own compression, not a downscaled 4K encode.
