"""Tests for coordinate data a user uploads (our template, Excel, kloppy providers) -> clip."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tactics.ai.summary import build_summary
from tactics.data.clips import load_clip
from tactics.data.report import QualityReport
from tactics.data.upload import check_input, from_kloppy, from_template, load_provider, read_table, to_clip
from tactics.data.validate import find_problems

ROOT = Path(__file__).resolve().parents[1]


def synthetic(seconds: float = 5.0, fps: float = 25.0, keeper_x: float = -48.0, with_position: bool = True) -> pd.DataFrame:
    """11 v 11 standing in two blocks, the home keeper at `keeper_x`, plus a ball, in our template."""
    rng = np.random.default_rng(0)
    rows = []
    home = rng.uniform([-40, -30], [-5, 30], (10, 2))
    away = rng.uniform([5, -30], [40, 30], (10, 2))
    for k in range(int(seconds * fps)):
        t = round(k / fps, 3)
        rows.append((t, "home", "Keeper", 1, "GK" if with_position else "", keeper_x, 0.0))
        rows.append((t, "away", "Keeper", 1, "GK" if with_position else "", -keeper_x, 0.0))
        for i, (x, y) in enumerate(home, 2):
            rows.append((t, "home", f"H{i}", i, "", x + 0.01 * k, y))
        for i, (x, y) in enumerate(away, 2):
            rows.append((t, "away", f"A{i}", i, "", x - 0.01 * k, y))
        rows.append((t, "ball", "", None, "", 0.1 * k, 0.0))
    return pd.DataFrame(rows, columns=["time_s", "team", "player", "jersey", "position", "x", "y"])


def read(table: pd.DataFrame, **kwargs):
    report = QualityReport()
    data = from_template(table, report, **kwargs)
    if data is not None:
        check_input(data, report)
    return data, report


def test_example_file_reproduces_the_bundled_clip():
    original = load_clip(ROOT / "clips" / "musiala-winner")
    data, report = read(read_table(ROOT / "templates" / "example_musiala_winner.csv"))
    assert report.status in ("ok", "warning"), report.summary()
    clip = to_clip(data, "uploaded-musiala", "Uploaded copy", focus_team=original.meta["focus_team"])
    assert not find_problems(clip.players, clip.ball)
    assert len(clip.ball) == len(original.ball)
    first = original.players[original.players["frame"] == original.players["frame"].min()].sort_values("player_name")
    mine = clip.players[clip.players["frame"] == 0].sort_values("player_name")
    np.testing.assert_allclose(mine[["x", "y"]].to_numpy(), first[["x", "y"]].to_numpy(), atol=0.01)
    assert build_summary(clip)["timeline"]  # the coach's facts can be built from it


def test_excel_files_are_read_like_csv(tmp_path):
    path = tmp_path / "match.xlsx"
    synthetic(seconds=4).to_excel(path, index=False)
    data, report = read(read_table(path))
    assert report.status == "ok", report.summary()
    assert data.frame_rate == 25.0 and data.players.groupby(["frame", "team"]).size().max() == 11


def test_missing_columns_are_refused_with_a_clear_reason():
    data, report = read(synthetic().drop(columns=["y"]))
    assert data is None and report.status == "rejected"
    assert "missing: y" in report.summary()


def test_wrong_units_are_caught():
    corner_origin = synthetic().assign(x=lambda t: t["x"] + 52.5, y=lambda t: t["y"] + 34)
    data, report = read(corner_origin)  # read as centre-origin metres: half the pitch lands outside
    failed = [c.name for c in report.checks if not c.passed]
    assert report.status == "rejected" and "positions on the pitch" in failed
    data, report = read(corner_origin, units="metres_corner")
    assert report.status == "ok", report.summary()


def test_normalised_units_become_metres():
    table = synthetic().assign(x=lambda t: t["x"] / 105 + 0.5, y=lambda t: t["y"] / 68 + 0.5)
    data, report = read(table, units="normalised")
    keeper = data.players[(data.players["team"] == "home") & (data.players["player_name"] == "Keeper")]
    assert keeper["x"].iloc[0] == pytest.approx(-48.0)


def test_short_clips_are_refused():
    data, report = read(synthetic(seconds=2))
    assert report.status == "rejected" and "clip length" in [c.name for c in report.checks if not c.passed]


def test_keeper_is_inferred_and_the_focus_team_attacks_left_to_right():
    data, report = read(synthetic(keeper_x=48.0, with_position=False))  # home keeper on the right, no GK labels
    assert not [c for c in report.checks if not c.passed and c.blocking]
    clip = to_clip(data, "x", "x", focus_team="home")
    keepers = clip.players[clip.players["position"] == "Goalkeeper"]
    assert set(keepers["team"]) == {"home", "away"}
    assert keepers.loc[keepers["team"] == "home", "x"].mean() < 0  # turned so home attacks left to right
    assert clip.meta["rotated"] and clip.meta["direction_known"]


def test_kloppy_datasets_are_cut_to_a_window():
    times = pd.to_timedelta(np.arange(0, 10, 0.04), unit="s")
    wide = pd.DataFrame({"period_id": 1, "timestamp": times, "ball_x": 1.0, "ball_y": 2.0, "ball_z": 0.0,
                         "ball_state": "alive", "p1_x": -40.0, "p1_y": 0.0, "p2_x": 40.0, "p2_y": 0.0})
    player = lambda pid, jersey: SimpleNamespace(player_id=pid, name=None, jersey_no=jersey, starting_position="GK")
    dataset = SimpleNamespace(to_df=lambda: wide, metadata=SimpleNamespace(frame_rate=25, teams=[
        SimpleNamespace(ground="home", name="Reds", players=[player("p1", 1)]),
        SimpleNamespace(ground="away", name="Blues", players=[player("p2", 1)])]))
    data = from_kloppy(dataset, period=1, start_s=2.0, end_s=6.0, source="test")
    assert len(data.ball) == 101 and data.team_names == {"home": "Reds", "away": "Blues"}
    assert set(data.players["position"]) == {"Goalkeeper"}


# kloppy ships small sample files for each provider it reads; we use them as stand-ins for the paid feeds.
KLOPPY_FILES = Path(__import__("kloppy").__file__).parent / "tests" / "files"
INDUSTRY_SAMPLES = {
    "tracab": {"meta_data": "tracab_meta.xml", "raw_data": "tracab_raw.dat"},
    "secondspectrum": {"meta_data": "second_spectrum_fake_metadata.xml", "raw_data": "second_spectrum_fake_data.jsonl"},
    "hawkeye": {"ball_feeds": ["hawkeye_2_46.football.samples.ball"],
                "player_centroid_feeds": ["hawkeye_2_46.football.samples.centroids"]},
}


@pytest.mark.parametrize("provider", sorted(INDUSTRY_SAMPLES))
def test_industry_provider_files_become_tracking_input(provider):
    if not KLOPPY_FILES.exists():
        pytest.skip("this kloppy install has no sample files")
    files = {key: [KLOPPY_FILES / n for n in name] if isinstance(name, list) else KLOPPY_FILES / name
             for key, name in INDUSTRY_SAMPLES[provider].items()}
    dataset = load_provider(provider, files)
    period = 2 if provider == "hawkeye" else 1
    data = from_kloppy(dataset, period=period, start_s=0.0, end_s=120.0, source="test")
    assert set(data.players["team"]) == {"home", "away"} and len(data.ball) > 0
    assert data.players["x"].abs().max() < 60 and data.players["y"].abs().max() < 40  # metres, centre spot = 0


def test_unknown_providers_are_refused():
    with pytest.raises(ValueError, match="provider must be one of"):
        load_provider("statsbomb", {})


# --- robustness of provider uploads (D39) -----------------------------------------------------------------

def write_metrica(path: Path, side: str, first_jersey: int, rng, halves=((1, 60.0), (2, 60.0)), fps=25) -> Path:
    """A small file in Metrica's tracking CSV format: 3 header rows, then one row per frame; time counts from kick-off."""
    jerseys = range(first_jersey, first_jersey + 11)
    rows = [",,," + ",".join(f"{side},," [:-1] for _ in jerseys) + ",,",
            ",,," + ",".join(f"{j}," for j in jerseys) + ",,",
            "Period,Frame,Time [s]," + ",".join(f"Player{j}," for j in jerseys) + "Ball,"]
    frame, clock = 0, 0.0
    for period, seconds in halves:
        for _ in range(int(seconds * fps)):
            frame += 1
            clock += 1 / fps
            spots = rng.uniform(0.1, 0.9, size=22).round(5)
            rows.append(f"{period},{frame},{clock:.2f}," + ",".join(map(str, spots)) + ",0.5,0.5")
        clock += 600  # half-time
    path.write_text("\n".join(rows) + "\n")
    return path


@pytest.fixture
def metrica_files(tmp_path):
    rng = np.random.default_rng(3)
    return {"home_data": write_metrica(tmp_path / "home.csv", "Home", 1, rng),
            "away_data": write_metrica(tmp_path / "away.csv", "Away", 12, rng)}


def test_metrica_files_are_cut_to_the_window_with_the_same_times(metrica_files, tmp_path):
    from kloppy import metrica
    from tactics.data.upload import trim_metrica_csv

    full = metrica.load_tracking_csv(metrica_files["home_data"], metrica_files["away_data"], coordinates="secondspectrum")
    cut = load_provider("metrica", metrica_files, window=(2, 20.0, 30.0))
    times = lambda ds: sorted(round(f.timestamp.total_seconds(), 2) for f in ds.records if f.period.id == 2 and 20 <= f.timestamp.total_seconds() <= 30)
    assert times(cut) == times(full) and len(times(cut)) == 251
    # 3 header rows, the first and last row of both halves, and 20-30 s with a 1 s margin each side (301 rows)
    trimmed = trim_metrica_csv(metrica_files["home_data"], tmp_path / "t.csv", 2, 20.0, 30.0).read_text().splitlines()
    assert len(trimmed) == 3 + 4 + 301 and trimmed[:3] == metrica_files["home_data"].read_text().splitlines()[:3]


def test_provider_uploads_refuse_wrong_input_with_reasons(metrica_files, tmp_path, monkeypatch):
    from tactics import service
    monkeypatch.setattr(service, "USER", tmp_path / "clips")
    upload = lambda files, period=1, a=10.0, b=40.0: service.create_from_provider("metrica", files, "t", period, a, b)

    clip_id, report = upload(metrica_files)
    assert clip_id, report
    clip_id, report = upload({"home_data": metrica_files["away_data"], "away_data": metrica_files["home_data"]})
    assert clip_id and any(c["name"] == "home and away files" for c in report["checks"])  # swapped back, with a note
    for files, period, a, b, check in [
        (metrica_files, 1, 300.0, 330.0, "window inside the half"),  # after the half ended
        (metrica_files, 3, 0.0, 30.0, "window inside the half"),  # no third half
        ({"home_data": metrica_files["home_data"], "away_data": metrica_files["home_data"]}, 1, 10.0, 40.0, "two different teams"),
    ]:
        clip_id, report = upload(files, period, a, b)
        failed = [c for c in report["checks"] if not c["passed"]]
        assert clip_id is None and failed[0]["name"] == check, report


def test_unreadable_provider_files_say_what_each_box_takes():
    from tactics import service
    if not KLOPPY_FILES.exists():
        pytest.skip("this kloppy install has no sample files")
    clip_id, report = service.create_from_provider(
        "tracab", {"meta_data": KLOPPY_FILES / "tracab_raw.dat", "raw_data": KLOPPY_FILES / "tracab_meta.xml"}, "t", 1, 0, 30)
    assert clip_id is None and "The first box takes the metadata" in report["checks"][0]["value"]


def test_second_spectrum_reads_the_json_metadata_too():
    if not KLOPPY_FILES.exists():
        pytest.skip("this kloppy install has no sample files")
    meta = [KLOPPY_FILES / "second_spectrum_fake_metadata.xml", KLOPPY_FILES / "second_spectrum_fake_metadata.json"]
    dataset = load_provider("secondspectrum", {"meta_data": meta, "raw_data": KLOPPY_FILES / "second_spectrum_fake_data.jsonl"})
    assert [t.name for t in dataset.metadata.teams] == ["FK1", "FK2"]
