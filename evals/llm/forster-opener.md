# LLM evaluation — forster-opener

- Model: `gemini-3.8-flash` via llm (prompt v3, 2026-10-11T07:00:20+00:00)
- Facts: [`clips/forster-opener/summary.json`](../../clips/forster-opener/summary.json)

## Explanation

**What happened**  
VfL Bochum 1848 showed a 4-4-2 shape in this clip against Bayer 04 Leverkusen, who had 10 players on the pitch. The ball moved between P. Förster (17:51), N. Amiri (17:52), K. Stöger (17:53), and T. Asano (17:58), ending with a goal by P. Förster at 18:03. Bochum advanced their back line—the average distance of the four deepest outfield players from their goal line—from 38 metres at 17:48 to 61 metres at 18:00. Meanwhile, Leverkusen’s back line retreated from 44 metres to 9 metres, leaving 0 players behind the ball from 17:56 to 18:00.

**Coach's view**  
* Bochum pushed their back line up to 61 metres with 10 players behind the ball, which typically pins opponents deep and maintains continuous attacking pressure.  
* Leverkusen dropping their back line to 9 metres while having 0 players behind the ball from 17:56 suggests their structure was bypassed near goal.  
* A coach would ask why Leverkusen allowed their defensive line to be isolated so close to their own net.

**Key numbers**  
* Leverkusen players behind the ball: fell from 3 at 17:48 to 0 at 17:56.  
* Leverkusen back line: dropped from 44 m (17:48) to 9 m (18:00).  
* Bochum back line: advanced from 38 m (17:48) to 61 m (18:00).

## Automatic grounding check

- Result: **PASS** (36 numbers, clocks and formations checked)
- Unsupported numbers: none
- Unsupported clocks: none
- Unsupported formations: none
- Capitalised words not in the facts (review by hand): none
- Format problems: none
- Repaired: yes, first answer from gemini-3.8-flash had too long: 238 words (limit 220)

## Human review

- [ ] "What happened" uses only facts present in summary.json
- [ ] Names the main tactical change correctly
- [ ] Coach's view: every point is tied to a stated fact and phrased as interpretation
- [ ] Coach's view: the football reasoning is sound (would a coach agree?)
- [ ] Readable for a non-expert (terms explained)
- [ ] No filler or invented events (passes, tackles, shot types, match context)

Reviewer notes:

