# Testing the checks: planted mistakes

Each correct explanation was copied with one planted mistake, at every place that mistake can go, and checked again (`scripts/plant_mistakes.py`, no LLM calls; D39). *Caught* means the copy got a problem the original did not have. Names are a soft check: flagged for review, not failed.

| Planted mistake | Copies | Caught | Rate | Caught by |
|---|---|---|---|---|
| number not in the facts | 96 | 96 | 100% | claims, grounding |
| a real value in the wrong place | 96 | 28 | 29% | claims |
| change reversed (from/to swapped) | 24 | 24 | 100% | claims |
| change given to the other team | 24 | 24 | 100% | claims |
| wrong match clock | 65 | 65 | 100% | grounding |
| wrong formation | 10 | 10 | 100% | grounding |
| invented event in What happened | 30 | 30 | 100% | invented |
| invented player name | 6 | 6 | 100% | names (soft) |

**Total:** 283/351 planted mistakes caught.

## Missed (examples)

- coman-opener: a real value in the wrong place: 20 -> 22
- coman-opener: a real value in the wrong place: 14 -> 13
- coman-opener: a real value in the wrong place: 1 -> 1.5
- coman-opener: a real value in the wrong place: 1 -> 1.5
- coman-opener: a real value in the wrong place: 58 -> 55
- coman-opener: a real value in the wrong place: 1 -> 1.5
- coman-opener: a real value in the wrong place: 13 -> 14
- coman-opener: a real value in the wrong place: 3 -> 2
- coman-opener: a real value in the wrong place: 54 -> 55
- coman-opener: a real value in the wrong place: 8 -> 7
- coman-opener: a real value in the wrong place: 1 -> 1.5
- coman-opener: a real value in the wrong place: 1 -> 1.5
- coman-opener: a real value in the wrong place: 839 -> 863
- coman-opener: a real value in the wrong place: 44 -> 43
- drone-0600-0630: a real value in the wrong place: 19 -> 17
- drone-0600-0630: a real value in the wrong place: 63 -> 61
- drone-0600-0630: a real value in the wrong place: 50 -> 49
- drone-0600-0630: a real value in the wrong place: 63 -> 61
- drone-0600-0630: a real value in the wrong place: 1 -> 1.5
- drone-0600-0630: a real value in the wrong place: 11 -> 10
- drone-0600-0630: a real value in the wrong place: 50 -> 49
- drone-0600-0630: a real value in the wrong place: 63 -> 61
- drone-0600-0630: a real value in the wrong place: 26 -> 27
- drone-0600-0630: a real value in the wrong place: 1002 -> 1084
- drone-0600-0630: a real value in the wrong place: 836 -> 833

