# Coach explanations: scoreboard

Automatic checks of every cached explanation against its facts (no LLM calls). Made by `scripts/evaluate_explanations.py`; see DECISIONS.md D34.

| Clip | Grounding | Claims right | Key facts said | Invented events | Format | Words |
|---|---|---|---|---|---|---|
| coman-opener | pass (38 checked) | 5/5 | 100% | none | ok | 207 |
| drone-0600-0630 | pass (31 checked) | 4/4 | 100% | none | ok | 224 |
| drone-1110-1140 | pass (27 checked) | 5/5 | 100% | none | ok | 216 |
| forster-opener | pass (36 checked) | 5/5 | 75% | none | ok | 212 |
| ljubicic-equaliser | pass (18 checked) | 0/0 | 100% | none | ok | 196 |
| musiala-winner | pass (26 checked) | 5/5 | 100% | none | ok | 217 |

**Total:** 6/6 grounded; 24/24 claims right; average key-fact coverage 96%.

- **forster-opener**: not said: VfL Bochum 1848 area_m2 384 -> 1226
