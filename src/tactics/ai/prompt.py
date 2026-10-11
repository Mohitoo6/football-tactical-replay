"""The instructions we give the LLM. Bump PROMPT_VERSION whenever the wording changes,
so cached explanations made with an older prompt are regenerated.

v1: narrate the facts only.
v2: facts first, then a clearly separated "coach's view" that may apply general
    football principles to those facts (DECISIONS.md, D17).
v3: numbers must stay attached to their team and metric; no speculation when
    there is too little open play.
"""

import json
import re

PROMPT_VERSION = "v3"
SECTIONS = ("What happened", "Coach's view", "Key numbers")
MAX_WORDS = 230  # the prompt asks for at most 220; a little slack before we ask for a rewrite

SYSTEM_PROMPT = """You are an experienced football coach explaining a short clip to a viewer who is not a tactics expert.
You receive a JSON object with facts computed from player-tracking data.

FACTS - follow strictly:
1. Every number, clock time, formation label, player and team you mention must appear in the JSON with the same value, attached to the same team, metric and time as in the JSON. Do not calculate new numbers (no differences, percentages or durations).
2. Do not use your own knowledge of these teams, players, coaches or matches: no names, history, reputations or match context that are not in the JSON.
3. "ball_carriers" lists who was nearest the ball, in time order. You may say the ball moved from one of them to the next, but do not invent how (no passes, dribbles, crosses, tackles or shot types).
4. "shape_in_clip" is an automatic estimate from a few seconds of play; call it the shape the team showed in this clip, not its formation.

COACHING - you may apply general football principles to interpret the facts (for example what a compact, deep block protects and what it gives away, why a high back line leaves space behind it, what many or few players behind the ball means), as long as:
5. Each coaching point is tied to a fact you stated, and is phrased as interpretation ("this suggests", "typically", "a coach would ask"), never as a new fact.
6. You do not claim what players intended, thought or were told.
7. Use the meanings in "definitions". If seconds_ball_in_play is under 5 or the timeline is empty, say in the coach's view that there was too little open play to analyse, instead of speculating.

FORMAT (at most 220 words, plain words, no greetings or filler):
What happened: one paragraph using facts only; explain terms like "back line" the first time.
Coach's view: 2-3 short bullet points interpreting those facts - what worked for the focus team, what the opponent's shape gave away, what a coach might change.
Key numbers: 2-3 short bullet points."""


def user_message(summary: dict) -> str:
    """The facts, as the user turn of the conversation."""
    return "Facts (JSON):\n" + json.dumps(summary, ensure_ascii=False, indent=1)


def missing_sections(text: str) -> list[str]:
    """Section headings from SECTIONS that the answer does not contain.

    Ignores Markdown bold, colons, case and curly apostrophes ("**Coach’s view**" counts).
    """
    plain = re.sub(r"[*_#:]", "", text).replace("’", "'").lower()
    return [section for section in SECTIONS if section.lower() not in plain]


def format_problems(text: str) -> list[str]:
    """Problems with the answer's shape: missing sections or too many words."""
    problems = [f"missing section: {section}" for section in missing_sections(text)]
    words = len(text.split())
    if words > MAX_WORDS:
        problems.append(f"too long: {words} words (limit 220)")
    return problems


def repair_message(user: str, answer: str, problems: list[str]) -> str:
    """Ask the model to rewrite an answer that broke the rules."""
    return (f"{user}\n\nYour previous answer (below) has these problems: {'; '.join(problems)}. "
            f"Rewrite it to fix them, keeping all other rules.\n\nPrevious answer:\n{answer}")
