# LLM evaluation — forster-opener

- Model: `gemini-3.8-flash` via llm (prompt v1, 2026-10-11T06:31:59+00:00)
- Facts: [`clips/forster-opener/summary.json`](../../clips/forster-opener/summary.json)

## Explanation

In this clip, VfL Bochum 1848 displayed a 4-2-3-1 shape the team showed in this clip while Bayer 04 Leverkusen had 10 players on pitch. The ball moved from P. Förster at 17:51 to N. Amiri at 17:52, then to K. Stöger at 17:53, and to T. Asano at 17:58 before P. Förster scored a goal at 18:03. During this attack, VfL Bochum 1848 pushed their back line—the average distance of the 4 deepest outfield players from their own goal line—from 38 meters at 17:48 to 65 meters at 18:02. Meanwhile, Bayer 04 Leverkusen's back line dropped from 44 meters to 6 meters. Bochum also expanded their total area, which is the space covered by all outfield players, from 384 square meters to 1217 square meters across that same period.

Key numbers:
• Bochum's back line pushed up from 38 meters to 65 meters between 17:48 and 18:02.
• Leverkusen's back line retreated from 44 meters to 6 meters from 17:48 to 18:02.
• Bochum's occupied area expanded from 384 square meters to 1217 square meters.

## Automatic grounding check

- Result: **PASS** (30 numbers, clocks and formations checked)
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

