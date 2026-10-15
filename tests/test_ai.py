"""Tests for the AI layer: facts summary, grounding check, and LLM calls (with fakes, no network)."""

from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pandas as pd
import pytest

from tactics.ai.grounding import check_grounding
from tactics.ai.llm import AllProvidersFailed, Provider, complete, explain, providers_from_env
from tactics.ai.prompt import format_problems, missing_sections
from tactics.ai.summary import ball_carriers, build_summary, in_play, notable_changes, timeline
from tactics.data.clips import Clip, load_clip
from tactics.geometry.shape import shape_over_time

CLIPS_DIR = Path(__file__).resolve().parents[1] / "clips"


@pytest.fixture(scope="module")
def musiala():
    return load_clip(CLIPS_DIR / "musiala-winner")


# --- summary.py -------------------------------------------------------------

def test_in_play_drops_dead_ball_and_post_goal_frames(musiala):
    players, ball = in_play(musiala)
    assert ball["alive"].all()
    assert ball["time_s"].max() <= musiala.meta["goals"][0]["time_s"] - 1.0  # stops at the shot
    assert set(players["frame"]) <= set(ball["frame"])


def test_timeline_values_equal_geometry_functions(musiala):
    rows = timeline(musiala)
    players, ball = in_play(musiala)
    first_window = ball[ball["time_s"] < ball["time_s"].iloc[0] + 2.0]  # clip starts with the ball in play
    expected = shape_over_time(players[players["frame"].isin(first_window["frame"])], "home", attacking_right=False)
    assert rows[0]["1. FC Köln"]["area_m2"] == round(expected["hull_area_m2"].mean())
    assert rows[0]["1. FC Köln"]["back_line_m"] == round(expected["line_height_m"].mean())


def test_summary_has_goal_teams_and_definitions(musiala):
    summary = build_summary(musiala)
    assert summary["goals"] == [{"clock": "88:15", "player": "J. Musiala", "team": "FC Bayern München"}]
    assert [t["name"] for t in summary["teams"]] == ["FC Bayern München", "1. FC Köln"]  # focus team first
    assert summary["ball_carriers"][-1]["player"] == "J. Musiala"
    assert set(summary["definitions"]) >= {"width_m", "depth_m", "area_m2", "back_line_m"}


def test_short_open_play_gets_no_shape_estimate():
    summary = build_summary(load_clip(CLIPS_DIR / "ljubicic-equaliser"))  # a penalty: ~1 s in play
    assert summary["clip"]["seconds_ball_in_play"] < 5
    assert all(t["shape_in_clip"].startswith("n/a") for t in summary["teams"])


def test_partial_view_states_the_camera_limit_and_needs_enough_players_in_view(musiala):
    partial = Clip({**musiala.meta, "view": "partial"}, musiala.players, musiala.ball)
    summary = build_summary(partial)
    assert "only part of the pitch" in summary["clip"]["camera"]
    assert "visible_players" in summary["definitions"]
    assert "most_players_visible" in summary["teams"][0]
    assert all(t["shape_in_clip"].startswith("n/a") for t in summary["teams"])
    assert all(row[name]["visible_players"] >= 7 for row in summary["timeline"] for name in ("1. FC Köln", "FC Bayern München"))
    # Metrics that need the deepest players (often out of view) are left out.
    assert all(set(row["1. FC Köln"]) == {"width_m", "area_m2", "visible_players"} for row in summary["timeline"])
    # With only 6 Köln outfield players in view, no shape is measured for Köln, so no window is reported.
    keep = partial.players.groupby(["frame", "team"]).cumcount() < 7  # keeper + 6 outfield per team
    few = Clip(partial.meta, partial.players[keep | (partial.players["team"] != "home")], partial.ball)
    assert timeline(few) == []
    assert "camera" not in build_summary(musiala)["clip"]  # full-pitch tracking data is unchanged


def carrier_clip() -> Clip:
    """Ball at the origin; who stands next to it changes over 12 frames."""
    nearest = ["A"] * 5 + ["B"] * 2 + ["C"] * 5  # B only for 2 frames = noise
    rows = []
    for frame, who in enumerate(nearest):
        for pid in "ABC":
            x = 0.5 if pid == who else 20.0 + ord(pid)
            rows.append({"frame": frame, "team": "home" if pid != "C" else "away", "player_id": pid,
                         "player_name": f"Player {pid}", "position": "Midfield", "x": x, "y": 0.0})
    ball = pd.DataFrame({"frame": range(12), "time_s": [f * 0.04 for f in range(12)], "x": 0.0, "y": 0.0,
                         "z": 0.1, "alive": True, "owning_team": "home"})
    meta = {"period": 1, "frame_rate": 25.0, "focus_team": "home", "goals": [],
            "teams": {"home": {"name": "Home FC"}, "away": {"name": "Away FC"}}}
    return Clip(meta, pd.DataFrame(rows), ball)


def test_ball_carriers_ignores_brief_noise():
    carriers = ball_carriers(carrier_clip())
    assert [(c["player"], c["team"]) for c in carriers] == [("Player A", "Home FC"), ("Player C", "Away FC")]


def test_notable_changes_uses_thresholds():
    metrics = {"width_m": 30, "depth_m": 40, "area_m2": 800, "back_line_m": 30}
    rows = [{"clock": "1:00", "T": metrics},
            {"clock": "1:10", "T": {**metrics, "width_m": 34, "area_m2": 600, "back_line_m": 20}}]
    changes = notable_changes(rows, ["T"])
    assert [(c["metric"], c["from"], c["to"]) for c in changes] == [("area_m2", 800, 600), ("back_line_m", 30, 20)]


# --- grounding.py -----------------------------------------------------------

SUMMARY = {"goals": [{"clock": "88:15", "player": "J. Musiala", "team": "FC Bayern München"}],
           "teams": [{"name": "1. FC Köln", "shape_in_clip": "3-5-2"}],
           "timeline": [{"clock": "87:57", "1. FC Köln": {"area_m2": 1398, "back_line_m": 25}}]}


def test_grounding_passes_on_supported_facts():
    text = ("J. Musiala scored at 88:15. Köln's area was 1,398 m² and their back line 25 m from goal "
            "at 87:57, in a 3-5-2 shape.")
    report = check_grounding(text, SUMMARY)
    assert report.passed and report.unknown_capitalised == []
    assert report.numbers_checked == 5  # 88:15, 87:57, 3-5-2, 1,398, 25


def test_grounding_flags_invented_numbers_clocks_and_formations():
    text = "Köln dropped by 12 m in 4 seconds at 88:30 into a 4-4-2."
    report = check_grounding(text, SUMMARY)
    assert not report.passed
    assert report.unsupported_numbers == ["12", "4"]  # differences and durations are not in the facts
    assert report.unsupported_clocks == ["88:30"]
    assert report.unsupported_formations == ["4-4-2"]


def test_grounding_flags_names_not_in_the_facts():
    report = check_grounding("The goal came after a run by Lewandowski. Then Musiala scored.", SUMMARY)
    assert report.unknown_capitalised == ["Lewandowski"]  # "The"/"Then" start sentences; Musiala is a fact


def test_missing_sections_accepts_markdown_headings():
    text = "**What happened**\nfacts\n\n**Coach’s view**\n* point\n\nKey numbers:\n* n"
    assert missing_sections(text) == []
    assert missing_sections("What happened: facts only") == ["Coach's view", "Key numbers"]


# --- llm.py (fake clients, no network) --------------------------------------

def api_error(cls, status):
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://example.test"))
    return cls("fake error", response=response, body=None)


class FakeClient:
    """Plays back a script of results: an exception to raise or a text to return."""

    def __init__(self, script, calls):
        self.script, self.calls = script, calls
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=result))])


def fake_factory(scripts, calls):
    def factory(api_key, **kwargs):
        return FakeClient(scripts[api_key], calls)
    return factory


PROVIDERS = [Provider("llm", "https://a.test", "model-a", "key-a", reasoning_effort="low"),
             Provider("fallback1", "https://b.test", "model-b", "key-b")]


def test_complete_retries_busy_provider_then_falls_back():
    calls, pauses = [], []
    scripts = {"key-a": [api_error(openai.RateLimitError, 429)] * 2 + [api_error(openai.InternalServerError, 503)],
               "key-b": ["An explanation."]}
    text, provider = complete("sys", "user", PROVIDERS, client_factory=fake_factory(scripts, calls), sleep=pauses.append)
    assert (text, provider.name) == ("An explanation.", "fallback1")
    assert pauses == [5, 10]  # two pauses between the three attempts on the first provider
    assert calls[0]["reasoning_effort"] == "low" and "reasoning_effort" not in calls[-1]


def test_complete_skips_provider_on_client_error_and_empty_answer():
    calls, pauses = [], []
    scripts = {"key-a": [api_error(openai.NotFoundError, 404)], "key-b": ["  "]}
    with pytest.raises(AllProvidersFailed, match="NotFoundError 404.*empty answer"):
        complete("sys", "user", PROVIDERS, client_factory=fake_factory(scripts, calls), sleep=pauses.append)
    assert pauses == [] and len(calls) == 2  # no pointless retries


def test_explain_uses_cache_until_facts_change(tmp_path):
    calls = []

    def fake_complete(system, user, providers):
        calls.append(user)
        return f"answer {len(calls)}", PROVIDERS[0]

    cache = tmp_path / "explanation.json"
    first = explain({"a": 1}, cache, providers=[], complete_fn=fake_complete)
    again = explain({"a": 1}, cache, providers=[], complete_fn=fake_complete)
    changed = explain({"a": 2}, cache, providers=[], complete_fn=fake_complete)

    assert (first["from_cache"], again["from_cache"], changed["from_cache"]) == (False, True, False)
    assert again["text"] == "answer 1" and changed["text"] == "answer 2"
    assert len(calls) == 2


def test_providers_from_env_skips_incomplete_entries(tmp_path, monkeypatch):
    for prefix in ("LLM", "FALLBACK1", "FALLBACK2", "FALLBACK3"):
        for field in ("BASE_URL", "MODEL", "API_KEY", "REASONING_EFFORT"):
            monkeypatch.delenv(f"{prefix}_{field}", raising=False)
    env = tmp_path / ".env"
    env.write_text("LLM_BASE_URL=https://a.test\nLLM_MODEL=m\nLLM_API_KEY=k\nLLM_REASONING_EFFORT=low\n"
                   "FALLBACK1_BASE_URL=https://b.test\nFALLBACK1_MODEL=m2\nFALLBACK1_API_KEY=\n")
    providers = providers_from_env(env)
    assert [(p.name, p.model, p.reasoning_effort) for p in providers] == [("llm", "m", "low")]


def test_explain_repairs_ungrounded_answer_once(tmp_path):
    answers = iter(["Köln dropped 12 m.", "Köln dropped to 10 m."])
    calls = []

    def fake_complete(system, user, providers):
        calls.append(user)
        return next(answers), PROVIDERS[0]

    result = explain({"back_line_m": 10}, tmp_path / "e.json", providers=[], complete_fn=fake_complete,
                     check=lambda text: check_grounding(text, {"back_line_m": 10}).problems)
    assert result["text"] == "Köln dropped to 10 m."
    assert result["repair"]["first_problems"] == ["not in the facts: 12"]
    assert "not in the facts: 12" in calls[1] and "Köln dropped 12 m." in calls[1]


def test_explain_keeps_first_answer_if_repair_is_not_better(tmp_path):
    answers = iter(["Köln dropped 12 m.", "Köln dropped 12 m in 3 s."])
    result = explain({"back_line_m": 10}, tmp_path / "e.json", providers=[],
                     complete_fn=lambda s, u, p: (next(answers), PROVIDERS[0]),
                     check=lambda text: check_grounding(text, {"back_line_m": 10}).problems)
    assert result["text"] == "Köln dropped 12 m." and result["repair"] is None


def test_grounding_normalises_typography_and_number_words():
    summary = {"teams": [{"shape_in_clip": "4-4-2", "players_behind_ball": 9, "area_m2": 1226}]}
    assert check_grounding("A 4\u20114\u20112 shape, 1\u202f226 m² and nine players behind the ball.", summary).passed
    assert check_grounding("Eleven players were behind the ball.", summary).unsupported_numbers == ["11"]


def test_explain_regenerates_a_cached_answer_that_fails_the_check(tmp_path):
    cache = tmp_path / "e.json"
    explain({"back_line_m": 10}, cache, providers=[], complete_fn=lambda s, u, p: ("Line at 12 m.", PROVIDERS[0]))
    result = explain({"back_line_m": 10}, cache, providers=[],
                     complete_fn=lambda s, u, p: ("Line at 10 m.", PROVIDERS[0]),
                     check=lambda text: check_grounding(text, {"back_line_m": 10}).problems)
    assert result["from_cache"] is False and result["text"] == "Line at 10 m."


def test_format_problems_flags_missing_sections_and_length():
    good = "What happened: x\nCoach's view: y\nKey numbers: z"
    assert format_problems(good) == []
    assert format_problems(good + " word" * 230) == ["too long: 239 words (limit 220)"]  # 9 heading words + 230
    assert format_problems("Key numbers: z") == ["missing section: What happened", "missing section: Coach's view"]


def test_explain_keeps_a_shorter_rewrite_when_problem_counts_tie(tmp_path):
    answers = iter(["one two three four five six", "one two three four"])
    result = explain({"a": 1}, tmp_path / "e.json", providers=[],
                     complete_fn=lambda s, u, p: (next(answers), PROVIDERS[0]),
                     check=lambda text: ["too long"] if len(text.split()) > 3 else [])
    assert result["text"] == "one two three four"
