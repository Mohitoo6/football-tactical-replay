"""HTTP API for the frontend (D32).

    uv run uvicorn tactics.api:app --reload          # http://localhost:8000/docs for the interactive docs

Endpoints:
    GET  /api/health                      status and whether drone video can be processed here
    GET  /api/clips?mine=a,b              every clip (deployed: the bundled ones and the visitor's own uploads)
    GET  /api/clips/{id}?step=2           frames, players, ball, team shapes, facts and explanation
    GET  /api/clips/{id}/video            the rendered replay, if there is one
    GET  /api/clips/{id}/source           the original video the clip was made from (drone clips), if kept
    POST /api/clips/{id}/explanation      the coach's explanation (cached; one LLM call on a miss)
    GET  /api/template, /api/template/example   the upload template and a full example file
    POST /api/uploads/tracking            our CSV/Excel template -> clip (or the reasons it was refused)
    POST /api/uploads/provider            provider files (Metrica, SkillCorner, Sportec, TRACAB, Second Spectrum,
                                          Hawk-Eye) + time window -> clip
    POST /api/uploads/drone               a drone video -> background job
    GET  /api/jobs/{id}                   that job's progress and result

Deployed (D38), the same app also serves the built web app (WEB_DIST) and keeps uploads private (VYUH_PUBLIC=1).
"""

import importlib.util
import os
import shutil
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from tactics import service
from tactics.ai.llm import AllProvidersFailed

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
MAX_TABLE_MB = 50
MAX_VIDEO_MB = 1500
COMPLETE_FN = None  # tests replace this with a fake LLM
# Deployed for the public: a visitor's library shows the bundled clips and only their own uploads.
PUBLIC = os.environ.get("VYUH_PUBLIC") == "1"
WEB_DIST = Path(os.environ["WEB_DIST"]) if os.environ.get("WEB_DIST") else None  # the built web app, if served here

app = FastAPI(title="Vyuh API (football tactical replay)", version="1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)  # clip payloads shrink ~6x
app.add_middleware(CORSMiddleware, allow_methods=["*"], allow_headers=["*"],
                   allow_origins=os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(","))

jobs: dict[str, dict] = {}  # drone-video jobs, in memory (one local process)


def video_supported() -> bool:
    return importlib.util.find_spec("cv2") is not None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "drone_video": video_supported()}


@app.get("/api/clips")
def clips(mine: str = "") -> list[dict]:
    """`mine`: the visitor's own upload ids (the web app remembers them), shown when deployed for the public."""
    listed = service.list_clips()
    if not PUBLIC:
        return listed
    own = set(mine.split(","))
    return [c for c in listed if c["origin"] == "bundled" or c["clip_id"] in own]


@app.get("/api/clips/{clip_id}")
def clip(clip_id: str, step: int = 1) -> dict:
    try:
        return service.clip_payload(clip_id, step=min(max(step, 1), 10))
    except service.ClipNotFound:
        raise HTTPException(404, f"no clip {clip_id!r}")


@app.get("/api/clips/{clip_id}/video")
def clip_video(clip_id: str) -> FileResponse:
    try:
        video = service.clip_folder(clip_id) / "video.mp4"
    except service.ClipNotFound:
        raise HTTPException(404, f"no clip {clip_id!r}")
    if not video.exists():
        raise HTTPException(404, "this clip has no rendered video")
    return FileResponse(video, media_type="video/mp4")


@app.get("/api/clips/{clip_id}/source")
def clip_source(clip_id: str) -> FileResponse:
    try:
        video = service.clip_folder(clip_id) / service.SOURCE_VIDEO
    except service.ClipNotFound:
        raise HTTPException(404, f"no clip {clip_id!r}")
    if not video.exists():
        raise HTTPException(404, "this clip has no original video")
    return FileResponse(video, media_type="video/mp4")


@app.post("/api/clips/{clip_id}/explanation")
def clip_explanation(clip_id: str) -> dict:
    try:
        return service.explanation(clip_id, complete_fn=COMPLETE_FN, providers=[] if COMPLETE_FN else None)
    except service.ClipNotFound:
        raise HTTPException(404, f"no clip {clip_id!r}")
    except AllProvidersFailed as error:
        raise HTTPException(503, f"no LLM available right now ({error}); try again later")


@app.get("/api/template")
def template() -> FileResponse:
    return FileResponse(TEMPLATES / "tracking_template.csv", media_type="text/csv", filename="tracking_template.csv")


@app.get("/api/template/example")
def template_example() -> FileResponse:
    return FileResponse(TEMPLATES / "example_musiala_winner.csv", media_type="text/csv", filename="example_musiala_winner.csv")


@app.post("/api/uploads/tracking")
def upload_tracking(file: UploadFile = File(...), title: str = Form("Uploaded clip"), units: str = Form("metres"),
                    focus_team: str = Form("home"), home_name: str = Form("Home"), away_name: str = Form("Away"),
                    start_s: float = Form(0.0)) -> dict:
    if units not in ("metres", "metres_corner", "normalised") or focus_team not in ("home", "away"):
        raise HTTPException(422, "units must be metres, metres_corner or normalised; focus_team home or away")
    with _saved(file, MAX_TABLE_MB) as path:
        clip_id, report = service.create_from_table(path, title, units, focus_team,
                                                    {"home": home_name, "away": away_name}, start_s)
    return {"clip_id": clip_id, "report": report}


# The two file boxes of each provider. Hawk-Eye writes one file per minute, so its boxes take several files.
PROVIDER_FILES = {"metrica": ("home_data", "away_data"), "skillcorner": ("meta_data", "raw_data"),
                  "sportec": ("meta_data", "raw_data"), "tracab": ("meta_data", "raw_data"),
                  "secondspectrum": ("meta_data", "raw_data"), "hawkeye": ("ball_feeds", "player_centroid_feeds")}
MULTI_FILE_PROVIDERS = {"hawkeye"}


@app.post("/api/uploads/provider")
def upload_provider(provider: str = Form(...), file_a: list[UploadFile] = File(...), file_b: list[UploadFile] = File(...),
                    period: int = Form(1), start_s: float = Form(...), end_s: float = Form(...),
                    title: str = Form("Uploaded clip"), focus_team: str = Form("home")) -> dict:
    """file_a / file_b: metrica = home CSV / away CSV; hawkeye = ball files / player centroid files (one per minute);
    the others = metadata / tracking data."""
    if provider not in PROVIDER_FILES:
        raise HTTPException(422, f"provider must be one of {sorted(PROVIDER_FILES)}")
    if provider not in MULTI_FILE_PROVIDERS and (len(file_a) != 1 or len(file_b) != 1):
        raise HTTPException(422, f"{provider} takes one file in each box")
    if not 0 < end_s - start_s <= 120:
        raise HTTPException(422, "choose a window of up to 120 s (end_s > start_s)")
    with _saved(file_a, MAX_TABLE_MB * 10) as a, _saved(file_b, MAX_TABLE_MB * 10) as b:
        if provider not in MULTI_FILE_PROVIDERS:
            a, b = a[0], b[0]
        clip_id, report = service.create_from_provider(provider, dict(zip(PROVIDER_FILES[provider], (a, b))), title,
                                                       period, start_s, end_s, focus_team)
    return {"clip_id": clip_id, "report": report}


@app.post("/api/uploads/drone")
def upload_drone(file: UploadFile = File(...), title: str = Form("Drone clip"), start_s: float = Form(0.0)) -> dict:
    if not video_supported():
        raise HTTPException(501, "drone video needs the video dependencies: run locally with `uv sync --group video`")
    folder = Path(tempfile.mkdtemp(prefix="drone-"))
    path = folder / Path(file.filename or "clip.mp4").name
    _copy_limited(file, path, MAX_VIDEO_MB)
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"state": "running", "progress": 0.0, "message": "starting", "clip_id": None, "report": None}

    def run() -> None:
        def progress(fraction: float, message: str) -> None:
            jobs[job_id].update(progress=round(fraction, 3), message=message)
        try:
            clip_id, report = service.create_from_drone_video(path, title, start_s, progress=progress)
            jobs[job_id].update(state="done" if clip_id else "rejected", progress=1.0, clip_id=clip_id, report=report,
                                message="done" if clip_id else "the video is not suitable")
        except Exception as error:  # report, never crash the server
            jobs[job_id].update(state="failed", message=f"{type(error).__name__}: {error}")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(404, f"no job {job_id!r}")
    return jobs[job_id]


class _saved:
    """Context manager: uploaded file(s) saved to a temporary folder (each size-limited), removed afterwards.

    One upload gives its path; a list of uploads gives a list of paths."""

    def __init__(self, upload: UploadFile | list[UploadFile], max_mb: int):
        self.upload, self.max_mb = upload, max_mb

    def __enter__(self) -> Path | list[Path]:
        self.folder = Path(tempfile.mkdtemp(prefix="upload-"))
        uploads = self.upload if isinstance(self.upload, list) else [self.upload]
        paths = []
        for i, upload in enumerate(uploads):
            path = self.folder / str(i) / Path(upload.filename or "upload").name  # own folder: same names cannot clash
            path.parent.mkdir()
            _copy_limited(upload, path, self.max_mb)
            paths.append(path)
        return paths if isinstance(self.upload, list) else paths[0]

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.folder, ignore_errors=True)


def _copy_limited(upload: UploadFile, path: Path, max_mb: int) -> None:
    written = 0
    with open(path, "wb") as out:
        while chunk := upload.file.read(1 << 20):
            written += len(chunk)
            if written > max_mb * (1 << 20):
                raise HTTPException(413, f"file larger than {max_mb} MB")
            out.write(chunk)


def serve_web_app(server: FastAPI, dist: Path) -> None:
    """Serve the built web app from `server`: its files, and index.html for every other page (the app routes it)."""
    from fastapi.staticfiles import StaticFiles

    server.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @server.get("/{path:path}", include_in_schema=False)
    def web_app(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, f"no endpoint /{path}")
        file = (dist / path).resolve()
        if path and file.is_file() and dist.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(dist / "index.html")


if WEB_DIST and WEB_DIST.is_dir():  # deployed: one server for the API and the web app (in development Vite serves it)
    serve_web_app(app, WEB_DIST)
