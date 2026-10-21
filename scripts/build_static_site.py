"""Build the online demo as a static site: the web app plus the bundled clips as files (D38).

    uv run python scripts/build_static_site.py web/dist          # after: cd web && VITE_STATIC=1 npm run build

Writes into the built app:
  data/clips/index.json                 the library (bundled clips only)
  data/clips/<id>.json                  a replay (every 2nd frame: 12.5 per second, blended smoothly on screen)
  data/clips/<id>.preview.json          a light copy for the library's hover preview (every 5th frame)
  data/clips/<id>/source.mp4            the original drone video, where the clip has one
  templates/                            the upload template and the example file
  app/.../index.html                    a copy of the app for each page, so links to any page work on a static host
  README.md                             the Hugging Face Space card
"""

import argparse
import json
import shutil
from pathlib import Path

from tactics.service import SOURCE_VIDEO, clip_folder, clip_payload, list_clips

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    return path.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dist", type=Path, help="the built web app (web/dist)")
    args = parser.parse_args()
    dist: Path = args.dist
    if not (dist / "index.html").exists():
        raise SystemExit(f"{dist} has no index.html: build the web app first (VITE_STATIC=1 npm run build)")

    clips = [c for c in list_clips() if c["origin"] == "bundled"]
    data = dist / "data" / "clips"
    total = write_json(data / "index.json", clips)
    for clip in clips:
        clip_id = clip["clip_id"]
        total += write_json(data / f"{clip_id}.json", clip_payload(clip_id, step=2))
        total += write_json(data / f"{clip_id}.preview.json", clip_payload(clip_id, step=5))
        source = clip_folder(clip_id) / SOURCE_VIDEO
        if source.exists():
            (data / clip_id).mkdir(exist_ok=True)
            shutil.copy2(source, data / clip_id / SOURCE_VIDEO)
            total += source.stat().st_size
        print(f"  {clip_id}")

    shutil.copytree(ROOT / "templates", dist / "templates", dirs_exist_ok=True)
    pages = ["app", "app/upload"] + [f"app/clip/{c['clip_id']}" for c in clips]
    for page in pages:
        (dist / page).mkdir(parents=True, exist_ok=True)
        shutil.copy2(dist / "index.html", dist / page / "index.html")
    shutil.copy2(dist / "index.html", dist / "404.html")  # any other address opens the app, which shows the library
    shutil.copy2(ROOT / "deploy" / "space" / "README.md", dist / "README.md")
    print(f"{len(clips)} clips, {total / 1e6:.1f} MB of clip data, {len(pages)} pages -> {dist}")


if __name__ == "__main__":
    main()
