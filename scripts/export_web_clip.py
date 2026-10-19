"""Write a clip's frontend payload as a static JSON file for the website (the landing page's live replay).

    uv run python scripts/export_web_clip.py musiala-winner web/public/data/musiala-winner.json --step 5

Same data as GET /api/clips/{id}, so the landing page works without the backend running.
"""

import argparse
import json
from pathlib import Path

from tactics.service import clip_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip_id")
    parser.add_argument("out", type=Path)
    parser.add_argument("--step", type=int, default=5, help="keep every n-th frame (5 = 5 fps from 25 fps)")
    args = parser.parse_args()
    payload = clip_payload(args.clip_id, step=args.step)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"{args.out}: {len(payload['frames'])} frames, {args.out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
