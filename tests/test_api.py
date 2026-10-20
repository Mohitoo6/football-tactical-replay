"""The HTTP API, end to end with FastAPI's test client: no network, a fake LLM, uploads in a temporary folder."""

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tactics import api, service
from tactics.ai.llm import Provider

ROOT = Path(__file__).resolve().parents[1]
FAKE_TEXT = ("What happened: the teams moved as the facts describe.\n"
             "Coach's view:\n- a coach would look at the shape.\n"
             "Key numbers:\n- see the facts.")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "USER", tmp_path / "user_clips")  # uploads never touch the committed clips
    monkeypatch.setattr(api, "COMPLETE_FN", lambda system, user, providers: (FAKE_TEXT, Provider("fake", "", "fake-model", "")))
    return TestClient(api.app)


def upload_example(client, **form):
    with open(ROOT / "templates" / "example_musiala_winner.csv", "rb") as f:
        return client.post("/api/uploads/tracking", files={"file": ("example.csv", f, "text/csv")},
                           data={"title": "Uploaded Musiala", "focus_team": "away", **form})


def test_health_and_clip_list(client):
    assert client.get("/api/health").json()["status"] == "ok"
    ids = [c["clip_id"] for c in client.get("/api/clips").json()]
    assert {"musiala-winner", "drone-0600-0630"} <= set(ids)


def test_clip_payload_has_frames_shapes_and_facts(client):
    payload = client.get("/api/clips/musiala-winner", params={"step": 5}).json()
    frame = payload["frames"][0]
    assert payload["frame_rate"] == 5.0 and len(frame["players"]) == 22
    assert {"hull", "width_m", "area_m2", "back_line_m"} <= set(frame["shapes"]["home"])
    assert payload["facts"]["timeline"] and payload["explanation"]["text"]
    # the cached explanation is re-checked against the facts without calling an LLM
    assert payload["grounding"]["passed"] and payload["grounding"]["numbers_checked"] > 10
    assert payload["checks"]["claims_ok"] == payload["checks"]["claims_checked"] > 0 and payload["checks"]["coverage"] == 1.0


def test_unknown_or_unsafe_clip_ids_are_404(client):
    assert client.get("/api/clips/no-such-clip").status_code == 404
    assert client.get("/api/clips/..%2F..%2Fetc").status_code == 404


def test_template_downloads(client):
    assert client.get("/api/template").text.startswith("time_s,team,player")
    assert client.get("/api/template/example").status_code == 200


def test_upload_makes_a_clip_that_can_be_read_and_explained(client):
    body = upload_example(client).json()
    assert body["report"]["status"] in ("ok", "warning") and body["clip_id"]
    payload = client.get(f"/api/clips/{body['clip_id']}").json()
    assert payload["meta"]["data_kind"] == "uploaded" and len(payload["frames"]) > 400
    explained = client.post(f"/api/clips/{body['clip_id']}/explanation").json()
    assert explained["model"] == "fake-model" and explained["grounding"]["passed"]
    assert body["clip_id"] in [c["clip_id"] for c in client.get("/api/clips").json()]


def test_bad_uploads_are_refused_with_reasons(client):
    response = client.post("/api/uploads/tracking", files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")})
    report = response.json()["report"]
    assert response.json()["clip_id"] is None and report["status"] == "rejected"
    assert any("missing" in c["value"] for c in report["checks"])
    assert upload_example(client, units="feet").status_code == 422


def test_drone_video_upload_runs_as_a_job(client, tmp_path):
    pytest.importorskip("cv2")
    from test_pipeline import write_video  # a small synthetic top-view clip with known players

    video = tmp_path / "drone.mp4"
    write_video(video)
    with open(video, "rb") as f:
        job_id = client.post("/api/uploads/drone", files={"file": ("drone.mp4", f, "video/mp4")},
                             data={"title": "Synthetic drone"}).json()["job_id"]
    for _ in range(300):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.2)
    assert job["state"] == "done", job
    payload = client.get(f"/api/clips/{job['clip_id']}").json()
    assert payload["meta"]["title"] == "Synthetic drone"
    if shutil.which("ffmpeg"):  # the original video is kept to play beside the replay, and can be seeked
        assert payload["has_source"]
        source = client.get(f"/api/clips/{job['clip_id']}/source", headers={"Range": "bytes=0-99"})
        assert source.status_code == 206 and source.headers["content-type"] == "video/mp4"
