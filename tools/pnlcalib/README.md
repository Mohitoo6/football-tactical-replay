# PnLCalib: per-frame camera calibration for broadcast clips

Broadcast clips need the camera calibrated in **every frame**, because the camera pans and zooms. We use [PnLCalib](https://github.com/mguti97/PnLCalib) (Gutiérrez-Pérez & Agudo, arXiv:2404.08401). It is an HRNet model that finds pitch keypoints and lines, followed by a line-based refinement.

## Licence boundary

- **PnLCalib is GPL-2.0.**
- **This repository is MIT.** To keep the two separate:
  - `setup.sh` installs PnLCalib into `data/tools/pnlcalib/`, which is git-ignored, with its own virtual environment. Nothing from PnLCalib is copied into this repository.
  - `run_pnlcalib.py` is a separate program that imports PnLCalib. That one file is licensed **GPL-2.0-or-later**.
  - `src/tactics/broadcast/calibrate.py` (MIT) runs it as a subprocess and only reads the JSON it writes.

## Setup (once, ~1.2 GB)

```bash
sh tools/pnlcalib/setup.sh
```

It runs on the Apple GPU (MPS) when available: ~1.4 s per frame on an M2, against ~2.4 s on the CPU. We calibrate 5 frames per second and interpolate in between.

## Where it works

| Camera | Result (DECISIONS.md, D28) |
|---|---|
| Main broadcast camera, side-on | 200/200 frames calibrated; projected lines on the painted lines in 88% of frames |
| High "tactical" camera looking along the pitch | Fails: the model was trained on side-on views and finds almost no keypoints |

Our pipeline checks every frame by drawing the calibrated pitch lines and measuring how many of them land on white paint (the line agreement). Frames that fail are dropped, and a clip with too few good frames is refused.
