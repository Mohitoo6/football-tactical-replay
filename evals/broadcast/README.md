# Broadcast video → tracking: first evaluation (Phase 8)

**No ground truth yet.** These numbers come from the pipeline's own checks and from looking at the output, not from true player positions. A ground-truth evaluation on SoccerNet-GSR is still to do (DECISIONS.md, D28). The clips are local screen recordings of TV footage, so they are not in the repository.

## Which cameras work

| Clip | Camera | Calibrated keyframes | Line agreement | Result |
|---|---|---|---|---|
| Women's World Cup (tactical camera) | high, looking along the pitch | 0/8 with default settings; 7/8 with lowered thresholds, but wrong | 0.01–0.08 | refused: the model was trained on side-on views |
| World Cup 2022 (tactical camera) | high, looking along the pitch | 0/3 | – | refused |
| Euro 2020, Copenhagen, 40 s | main side-on camera, plus one cut to a high corner camera | 200/200 | median 0.84; 98% of frames ≥ 0.5 | **accepted** |

**Line agreement** is the share of the calibrated pitch lines, drawn into the frame, that fall within 4 px of white paint. On the calibration model's own example image it is 0.48 with a visibly correct fit. Wrong fits score below 0.1.

## Euro 2020 clip (40 s)

Quality report:

```
Quality: OK
  [ok  ] clip length: 40.0 s
  [ok  ] camera calibrated: 98% of pitch frames, median line agreement 0.84
  [ok  ] usable length: 39.0 s with a good calibration
  [ok  ] players in view: median 21 per frame
  [ok  ] ball visible: 39% of frames
```

| What | Result | How we know |
|---|---|---|
| Players found | median 21 per keyframe (15–25) | count; spot-checked on frames |
| Ball | detected in 82% of keyframes; 4 of 4 inspected detections were the real ball; the ball follower keeps 39% of frames | crops checked by eye |
| Teams by shirt colour | detections whose colour disagrees with their track's team: 7.7% → **3.3%** after cutting tracks where the colour changes; detections in a team: 81% → 94% | self-consistency only: this is the same colour rule the split uses |
| Referee | **drawn as the white team** (light-blue shirt, too close to white in our colour measure) | seen in the overlay |
| Coach explanation | grounding PASS; states that the camera showed only part of the pitch | `scripts/generate_explanations.py` |

**Speed on an M2:**
- Calibration: 1.4 s per keyframe on the Apple GPU, about 5 min for 40 s of video at 5 keyframes per second.
- Detection: 0.18 s per keyframe.
- A second run of the same video reuses the cached calibration and takes ~1.5 min.

## Measured on hand labels (D29)

Mohit labelled the Euro 2020 clip with `scripts/label_frames.py`: the ball once per second (40 frames, 38 with the ball visible) and every person's feet on 5 frames (103 people). `scripts/evaluate_broadcast.py` scores what the video shows; the history is in `local-euro-copenhagen.csv`.

| Run | People found | Ring precision | Ball within 15 px | Ball shown | Right when shown | False ball |
|---|---|---|---|---|---|---|
| baseline (D28) | 85.4% | 91.7% | 10.5% | 52% | – | 50% |
| full-resolution ball tracker | 90.3% | 83.8% | 10.5% | 95% | – | 100% |
| painted spots rejected | 90.3% | 83.8% | 50.0% | 88% | – | 100% |
| confirmed ball, no staff | 90.3% | 90.3% | 47.4% | 60% | 75% | 50% |
| **strict confirmed ball (current)** | **90.3%** | **90.3%** | 21.1% | 20% | **100%** | **0%** |

"False ball" is measured on only 2 labelled frames without a visible ball. The current setting shows the ball less often but never in the wrong place, and the coach analyses only those moments. These numbers come from the one clip the settings were tuned on.
