# LLM evaluation — coman-opener

- Model: `gemini-3.8-flash` via llm (prompt v1, 2026-10-11T06:31:53+00:00)
- Facts: [`clips/coman-opener/summary.json`](../../clips/coman-opener/summary.json)

## Explanation

FC Bayern München had 11 players on the pitch and displayed a 4-1-4-1 shape in this clip. The ball moved across several players, starting with Ryan Gravenberch, going to T. Müller, Jonas Hector of 1. FC Köln, Leroy Sané, and finally Kingsley Coman, who scored a goal at 7:49. 1. FC Köln also had 11 players on the pitch and showed a 4-4-2 shape in this clip. During this sequence, 1. FC Köln retreated toward their goal, meaning their back line—the average distance of their four deepest outfield defenders from their own goal line—shifted from 58 meters to 11 meters. At the same time, their total area, which is the physical space covered around all outfield players, condensed from 1081 square meters down to 754 square meters. FC Bayern München pushed forward, with their own back line advancing from 17 meters to 57 meters.

Key numbers:
- 1. FC Köln's back line dropped from 58 meters at 7:35 to 11 meters at 7:49.
- 1. FC Köln's occupied area shrank from 1081 square meters to 754 square meters.
- FC Bayern München's back line advanced from 17 meters to 57 meters before Kingsley Coman scored at 7:49.

## Automatic grounding check

- Result: **PASS** (25 numbers, clocks and formations checked)
- Unsupported numbers: none
- Unsupported clocks: none
- Unsupported formations: none
- Capitalised words not in the facts (review by hand): none

## Human review

- [ ] Mentions only facts present in summary.json
- [ ] Names the main tactical change correctly
- [ ] Readable for a non-expert (terms explained)
- [ ] No filler or invented events (passes, tackles, shot types)

Reviewer notes:

