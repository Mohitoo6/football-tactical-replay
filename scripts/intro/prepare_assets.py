"""Prepare the intro's photo assets from the two reference images (made by Mohit with ChatGPT).

    uv run --group video python scripts/intro/prepare_assets.py --lama /path/to/big-lama.pt

Writes to web/public/intro/:
  shot1.jpg        the keeper's view before the kick (unchanged, re-encoded)
  shot2-clean.jpg  the moment after the kick, with the photo's own ball removed (LaMa inpainting)
  ball.webp        that ball cut out with a soft edge, used as the sprite our physics moves
  camera.json      the measurements the intro uses to project the computed flight into shot 2

LaMa: big-lama TorchScript from the lama-cleaner project (Apache-2.0), md5 e3aa4aaa15225a33ec84f9f4bc47e500.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "web" / "intro-src"
OUT = ROOT / "web" / "public" / "intro"

# Measured by eye on shot2 (1600 x 900): the ball, the striker's kicking boot, his plant foot and head.
BALL_CENTRE = (959, 320)
BALL_RADIUS = 322
BOOT = (607, 547)
PLANT_FOOT_Y = 632
HEAD_TOP_Y = 390
STRIKER_HEIGHT_M = 1.85


def inpaint(image: np.ndarray, mask: np.ndarray, model_path: Path) -> np.ndarray:
    """Fill the masked area with LaMa (RGB uint8 in, RGB uint8 out)."""
    model = torch.jit.load(str(model_path), map_location="cpu").eval()
    h, w = image.shape[:2]
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = np.pad(image, ((0, ph), (0, pw), (0, 0)), mode="reflect")
    msk = np.pad(mask, ((0, ph), (0, pw)), mode="reflect")
    img_t = torch.from_numpy(img).permute(2, 0, 1)[None].float() / 255
    msk_t = torch.from_numpy((msk > 127).astype(np.float32))[None, None]
    with torch.no_grad():
        out = model(img_t, msk_t)[0].permute(1, 2, 0).numpy()
    out = np.clip(out * 255, 0, 255).astype(np.uint8)[:h, :w]
    # keep the original pixels outside the hole
    keep = (mask < 128)[..., None]
    return np.where(keep, image, out)


def ball_sprite(image: np.ndarray) -> np.ndarray:
    """The photo's ball as a square RGBA sprite with a feathered round edge."""
    cx, cy = BALL_CENTRE
    r = BALL_RADIUS + 4
    size = 2 * r
    canvas = np.zeros((size, size, 3), np.uint8)
    x0, y0 = cx - r, cy - r
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(image.shape[1], x0 + size), min(image.shape[0], y0 + size)
    canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = image[sy0:sy1, sx0:sx1]
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx - r + 0.5, yy - r + 0.5)
    alpha = np.clip((BALL_RADIUS - d) / 6 + 0.5, 0, 1)
    # the top of the ball is cut by the photo's edge: mirror the missing rows so the sprite stays round
    missing = sy0 - y0
    if missing > 0:
        canvas[:missing] = canvas[2 * missing:missing:-1]
    return np.dstack([canvas, (alpha * 255).astype(np.uint8)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lama", type=Path, required=True, help="big-lama.pt (TorchScript)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    shot1 = cv2.imread(str(SRC / "shot1.jpg"))
    shot2 = cv2.imread(str(SRC / "shot2.jpg"))
    cv2.imwrite(str(OUT / "shot1.jpg"), shot1, [cv2.IMWRITE_JPEG_QUALITY, 90])

    cv2.imwrite(str(OUT / "ball.webp"), cv2.cvtColor(ball_sprite(cv2.cvtColor(shot2, cv2.COLOR_BGR2RGB)), cv2.COLOR_RGBA2BGRA),
                [cv2.IMWRITE_WEBP_QUALITY, 92])

    mask = np.zeros(shot2.shape[:2], np.uint8)
    cv2.circle(mask, BALL_CENTRE, BALL_RADIUS + 26, 255, -1)
    clean = inpaint(cv2.cvtColor(shot2, cv2.COLOR_BGR2RGB), mask, args.lama)
    cv2.imwrite(str(OUT / "shot2-clean.jpg"), cv2.cvtColor(clean, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])

    focal = (PLANT_FOOT_Y - HEAD_TOP_Y) * 11.5 / STRIKER_HEIGHT_M   # pinhole: px = f * metres / distance
    camera = {
        "image": [shot2.shape[1], shot2.shape[0]],
        "focal_px": round(focal, 1),
        "boot_px": BOOT, "ball_px": BALL_CENTRE, "ball_radius_px": BALL_RADIUS,
        "plant_foot_y_px": PLANT_FOOT_Y,
        "note": "focal from the striker's height (242 px for ~1.85 m at ~11.5 m)",
    }
    (OUT / "camera.json").write_text(json.dumps(camera, indent=2))
    print(json.dumps(camera))


if __name__ == "__main__":
    main()
