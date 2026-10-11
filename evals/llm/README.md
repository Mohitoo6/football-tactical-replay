# LLM explanation evaluation

Generated with `uv run python scripts/generate_explanations.py` (prompt v1, 2026-10-11).
Each clip has a sheet in this folder with the explanation, the automatic grounding report and a checklist for human review.

## Results (prompt v3: facts + coach's view)

| Clip | Model | Words | Grounding | Repaired | First-pass review (Claude; to be confirmed by a human) |
|---|---|---|---|---|---|
| coman-opener | gemini-3.6-flash | 207 | PASS | no | Claims checked by hand against the timeline (Bayern width 47 → 34 m, Köln 2–3 players behind the ball): correctly attributed. |
| forster-opener | gemini-3.8-flash | 212 | PASS | yes (too long: 238 words (limit 220)) | Coach's view now reads 0 players behind the ball correctly (defence bypassed). First answer was rewritten for length by the repair step. |
| ljubicic-equaliser | gemini-3.8-flash | 196 | PASS | no | Penalty with no open play before the shot: says there was too little open play to analyse instead of speculating. |
| musiala-winner | gemini-3.8-flash | 230 | PASS | no | Sound coaching point: a deep, compact block (757 → 388 m²) protects the box but cedes control outside it. |

How we got here (each step was found by reading real outputs):

- **v1 (facts only):** all passed, but a penalty clip with 1 s of open play still got a shape label. Fix in the facts: shape is "n/a" under 5 s of open play.
- **v2 (adds a coach's view):**
  - Answers ran long (254–324 words). Fix: length and missing sections now count as problems and trigger one rewrite.
  - A fallback model (gpt-oss-120b) wrote "1 226" with a thin space and "4‑4‑2" with non-breaking hyphens. Fix: the checker normalises typography and reads number words ("nine").
  - One coaching point read "0 players behind the ball" as "no screen in front of the defence". The facts were the problem: the last window was taken after the shot, when the ball was already in the net. Fix: facts stop 1 s before the goal.
- **v3:**
  - Numbers must stay attached to the same team and metric.
  - With too little open play, the model must say so instead of speculating.
  - The definition of `players_behind_ball` now says what 0 means.

Known limit: the automatic check confirms each number exists in the facts, **not** that it is attached to the right team or metric. We checked the Coman claims by hand.

## Why the rules matter: naive prompt vs strict prompt

Same facts (`clips/musiala-winner/summary.json`), two system prompts:

| Prompt | Grounding | What went wrong |
|---|---|---|
| Naive: "You are a football pundit. Explain this clip to a fan in about 150 words." | **FAIL** | Number "300" (fact: 301); names "Jamal" Musiala and "João" Cancelo from the model's own knowledge (facts: "J. Musiala", "Joao Cancelo"); invented events and context ("slips it", "bottom corner", "title race", "championship-defining") |
| Strict (`src/tactics/ai/prompt.py`) | PASS | — |

The automatic check caught the invented number and both names, but **not** the invented events and context. Those are words, not numbers or names. That is the known limit of the check (DECISIONS.md, D6), and it is why each sheet also has a human checklist.

<details><summary>Naive-prompt output (gemini-3.8-flash)</summary>

Talk about drama in the title race! Look at Bayern München’s desperation and composure here in the 89th minute. 

After Köln try to relieve pressure, Joshua Kimmich snuffs out the clearance at midfield. Notice Bayern’s tactical squeeze: their defensive line pushes aggressively from 42 meters right up to 75 meters, compressing the entire team into an ultra-compact 790 square meters. They essentially trap Köln in their own defensive third, pinning their back line just 10 meters off their goal line into a desperate 300-square-meter block.

Bayern stay patient, stretching play wide through João Cancelo before feeding Serge Gnabry. Then comes the magic. Gnabry slips it to Jamal Musiala on the edge of the box. With virtually no space against Köln’s crowded defense, Musiala creates half a yard of separation and arrows a clinical finish into the bottom corner at 88:15. Pure ice in his veins—a championship-defining moment!

</details>
