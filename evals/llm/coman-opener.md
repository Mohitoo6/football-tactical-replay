# LLM evaluation — coman-opener

- Model: `gemini-3.6-flash` via fallback1 (prompt v3, 2026-10-11T06:59:55+00:00)
- Facts: [`clips/coman-opener/summary.json`](../../clips/coman-opener/summary.json)

## Explanation

**What happened**
In this 20-second clip from 7:35 to 7:55 (with 14 seconds of ball in play), FC Bayern München lined up in a 4-1-4-1 shape in this clip against 1. FC Köln's 4-4-2 shape in this clip. Ball carriers went from Ryan Gravenberch at 7:35 to T. Müller at 7:39, Jonas Hector at 7:39, Leroy Sané at 7:40, and Kingsley Coman at 7:45, before Coman scored at 7:49. FC Bayern München's back line—the average distance of a team's four deepest outfield players from their own goal line—pushed up from 17m to 54m, while 1. FC Köln's back line dropped from 58m to 13m.

**Coach's view**
* As 1. FC Köln's back line dropped deep to 13m, their players behind the ball fell from 7 at 7:35 down to 3 at 7:47, which typically leaves open space for attackers in dangerous areas.
* FC Bayern München squeezing up to a 54m back line with 8 players behind the ball at 7:47 allowed them to push 1. FC Köln deep into their attacking third.

**Key numbers**
* 1. FC Köln's team area shrank from 1081 m² at 7:35 to 839 m² at 7:47.
* FC Bayern München's team depth expanded from 27m at 7:35 to 44m at 7:47.

## Automatic grounding check

- Result: **PASS** (38 numbers, clocks and formations checked)
- Unsupported numbers: none
- Unsupported clocks: none
- Unsupported formations: none
- Capitalised words not in the facts (review by hand): none
- Format problems: none
- Repaired: no

## Human review

- [ ] "What happened" uses only facts present in summary.json
- [ ] Names the main tactical change correctly
- [ ] Coach's view: every point is tied to a stated fact and phrased as interpretation
- [ ] Coach's view: the football reasoning is sound (would a coach agree?)
- [ ] Readable for a non-expert (terms explained)
- [ ] No filler or invented events (passes, tackles, shot types, match context)

Reviewer notes:

