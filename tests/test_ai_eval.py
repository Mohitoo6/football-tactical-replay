"""The explanation checks catch the mistakes they are meant to catch, on small hand-made facts."""

from tactics.ai.evaluate import evaluate, team_aliases

FACTS = {
    "teams": [
        {"name": "FC Bayern München", "shape_in_clip": "4-1-4-1"},
        {"name": "1. FC Köln", "shape_in_clip": "3-5-2"},
    ],
    "goals": [{"clock": "88:15", "player": "J. Musiala", "team": "FC Bayern München"}],
    "notable_changes": [
        {"team": "FC Bayern München", "metric": "back_line_m", "from": 42, "to": 72, "from_clock": "87:57", "to_clock": "88:13"},
        {"team": "1. FC Köln", "metric": "area_m2", "from": 757, "to": 388, "from_clock": "87:57", "to_clock": "88:13"},
    ],
    "timeline": [],
}
GOOD = ("Bayern showed a 4-1-4-1 and Köln a 3-5-2. Bayern's back line pushed up from 42 metres to 72 metres. "
        "Köln's area dropped from 757 m² to 388 m². J. Musiala scored at 88:15.")


def test_a_correct_explanation_passes_every_check():
    report = evaluate(GOOD, FACTS)
    assert report.claims_ok == len(report.claims) == 2
    assert report.coverage == 1.0 and not report.invented


def test_a_change_given_to_the_wrong_team_is_caught():
    report = evaluate("Köln's back line went from 42 to 72 metres.", FACTS)
    assert not report.claims[0].ok and "belongs to FC Bayern München" in report.claims[0].reason


def test_wording_that_goes_the_wrong_way_is_caught():
    report = evaluate("Bayern's back line dropped from 42 to 72 metres.", FACTS)
    assert not report.claims[0].ok and "other way" in report.claims[0].reason


def test_numbers_in_the_wrong_order_are_caught():
    report = evaluate("Bayern's back line moved from 72 to 42 metres.", FACTS)
    assert not report.claims[0].ok


def test_missing_key_facts_and_invented_events_are_reported():
    report = evaluate("Bayern passed the ball well and took a shot.", FACTS)
    assert report.coverage == 0.0 and "goal by J. Musiala at 88:15" in report.missing
    assert {"passed", "shot"} <= set(report.invented)


def test_a_goal_that_is_not_in_the_facts_is_reported():
    report = evaluate("Bayern scored late on.", {**FACTS, "goals": []})
    assert "a goal that is not in the facts" in report.invented


def test_team_aliases():
    assert "Köln" in team_aliases("1. FC Köln")
    assert "Team A" in team_aliases("Team A (lighter shirts)") and "lighter" not in team_aliases("Team A (lighter shirts)")


def test_units_written_without_a_space_and_changes_with_clocks_in_between():
    report = evaluate("Bayern's back line pushed up from 42m at 87:57 to 72m at 88:13. "
                      "J. Musiala scored at 88:15. Bayern 4-1-4-1, Köln 3-5-2, area from 757 m² to 388 m² for Köln.", FACTS)
    assert report.coverage == 1.0
    assert [c.ok for c in report.claims] == [True, True]


def test_general_football_talk_in_the_coachs_view_is_not_an_invented_event():
    text = "**What happened**\nBayern pushed up.\n\n**Coach's view**\n* A deep block can invite late shots."
    assert evaluate(text, FACTS).invented == []
