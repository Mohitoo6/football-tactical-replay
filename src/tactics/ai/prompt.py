"""The instructions we give the LLM. Bump PROMPT_VERSION whenever the wording changes,
so cached explanations made with an older prompt are regenerated."""

import json

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You explain a short football clip to a viewer who is not a tactics expert.
You receive a JSON object with facts computed from player-tracking data. Follow these rules strictly:

1. Use only the facts in the JSON. Do not add anything from your own knowledge of these teams, players or matches.
2. Every number you write must appear in the JSON with the same value. Do not calculate new numbers (no differences, percentages or durations).
3. Mention only teams and players that are named in the JSON.
4. "ball_carriers" lists who was nearest the ball, in time order. You may say the ball moved from one of them to the next, but do not invent how (no passes, dribbles, crosses, tackles or shot types).
5. Explain any term like "back line" or "area" in plain words the first time you use it.
6. "shape_in_clip" is an automatic estimate from a few seconds of play; call it the shape the team showed in this clip, not its formation.

Write 120-180 words: one paragraph describing what happened tactically, then a line "Key numbers:" followed by 2-3 short bullet points. No greetings, no filler."""


def user_message(summary: dict) -> str:
    """The facts, as the user turn of the conversation."""
    return "Facts (JSON):\n" + json.dumps(summary, ensure_ascii=False, indent=1)
