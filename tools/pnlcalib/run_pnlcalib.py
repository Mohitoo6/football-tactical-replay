# SPDX-License-Identifier: GPL-2.0-or-later
# This file is a separate program, licensed GPL-2.0-or-later because it imports PnLCalib
# (https://github.com/mguti97/PnLCalib, GPL-2.0). The rest of this repository (MIT) never imports it;
# it only runs it as a subprocess and reads the JSON it writes (see tools/pnlcalib/README.md).
"""Calibrate every frame in a folder with PnLCalib; write {frame name: 3x3 pitch->image homography or null}.

    <pnlcalib checkout>/.venv/bin/python run_pnlcalib.py --pnlcalib <checkout> --frames <dir> --out <file.json>

Pitch coordinates are metres with the origin at the centre spot, x along the length (as in the clips).
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torchvision.transforms as T
import torchvision.transforms.functional as F
import yaml
from PIL import Image

KP_THRESHOLD, LINE_THRESHOLD = 0.3434, 0.7867  # PnLCalib's defaults


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pnlcalib", type=Path, required=True, help="PnLCalib checkout (with weights/)")
    parser.add_argument("--frames", type=Path, required=True, help="folder of .jpg frames, all the same size")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--weights", default="SV", help="weights prefix in <checkout>/weights (default SV)")
    parser.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    args = parser.parse_args()

    sys.path.insert(0, str(args.pnlcalib))
    from inference import projection_from_cam_params
    from model.cls_hrnet import get_cls_net
    from model.cls_hrnet_l import get_cls_net as get_cls_net_l
    from utils.utils_calib import FramebyFrameCalib
    from utils.utils_heatmap import (complete_keypoints, coords_to_dict, get_keypoints_from_heatmap_batch_maxpool,
                                     get_keypoints_from_heatmap_batch_maxpool_l)

    def load(config: str, build, weights: str):
        model = build(yaml.safe_load((args.pnlcalib / "config" / config).read_text()))
        state = torch.load(args.pnlcalib / "weights" / weights, map_location="cpu", weights_only=True)  # tensors only
        model.load_state_dict(state)
        return model.to(args.device).eval()

    model = load("hrnetv2_w48.yaml", get_cls_net, f"{args.weights}_kp")
    model_lines = load("hrnetv2_w48_l.yaml", get_cls_net_l, f"{args.weights}_lines")
    paths = sorted(args.frames.glob("*.jpg"))
    width, height = Image.open(paths[0]).size
    calibrator = FramebyFrameCalib(iwidth=width, iheight=height, denormalize=True)
    resize = T.Resize((540, 960))

    results, start = {}, time.perf_counter()
    for i, path in enumerate(paths, 1):
        frame = resize(F.to_tensor(Image.open(path).convert("RGB")).float().unsqueeze(0)).to(args.device)
        with torch.no_grad():
            heat, heat_lines = model(frame), model_lines(frame)
        keypoints = coords_to_dict(get_keypoints_from_heatmap_batch_maxpool(heat[:, :-1].cpu()), threshold=KP_THRESHOLD)
        lines = coords_to_dict(get_keypoints_from_heatmap_batch_maxpool_l(heat_lines[:, :-1].cpu()), threshold=LINE_THRESHOLD)
        keypoints, lines = complete_keypoints(keypoints[0], lines[0], w=960, h=540, normalize=True)
        calibrator.update(keypoints, lines)
        params = calibrator.heuristic_voting(refine_lines=True)
        if params is None:
            results[path.stem] = None
        else:
            projection = projection_from_cam_params(params)  # 3x4, pitch metres (x, y, z) -> pixels
            homography = projection[:, [0, 1, 3]]  # on the ground (z = 0)
            results[path.stem] = (homography / homography[2, 2]).tolist()
        print(f"calibrated {i}/{len(paths)} frames", flush=True)
    args.out.write_text(json.dumps(results))
    seconds = (time.perf_counter() - start) / max(len(paths), 1)
    found = sum(h is not None for h in results.values())
    print(f"done: {found}/{len(paths)} frames, {seconds:.2f} s per frame on {args.device}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
