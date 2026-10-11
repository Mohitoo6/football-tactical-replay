# LLM explanation evaluation

Generated with `uv run python scripts/generate_explanations.py` (prompt v1, 2026-10-11).
Each clip has a sheet in this folder with the explanation, the automatic grounding report and a checklist for human review.

## Results

| Clip | Model | Words | Grounding (automatic) | First-pass review notes (Claude; to be confirmed by a human) |
|---|---|---|---|---|
| coman-opener | gemini-3.8-flash | 197 | PASS (25 checked) | Accurate; slightly over the 180-word target. |
| forster-opener | gemini-3.8-flash | 176 | PASS (30 checked) | Correctly says Leverkusen had 10 players and calls the shape an estimate. |
| ljubicic-equaliser | gemini-3.8-flash | 187 | PASS (21 checked) | Penalty: says the shape is not available (under 5 s of open play) and that the ball was in play for 1 s of 20 s. |
| musiala-winner | gemini-3.8-flash | 180 | PASS (24 checked) | Accurate ball-carrier sequence and shape changes. |

Recurring issues for human review: word counts sometimes exceed the 180-word limit, and the model occasionally adds causal wording ("forced", "pushed back") that the facts do not state. The grounding check cannot catch these.

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
