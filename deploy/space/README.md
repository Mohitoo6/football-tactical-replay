---
title: Vyuh · football tactical replay
emoji: ⚽
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Football tactics from tracking data, explained by an AI coach
---

# Vyuh (व्यूह) · football tactical replay

Replays real football moments from player-tracking data, draws each team's shape as it moves, and has an LLM explain the tactics using only facts the code has measured. Every number in the explanation is checked automatically.

- **Code, results and decisions:** [github.com/Mohitoo6/football-tactical-replay](https://github.com/Mohitoo6/football-tactical-replay)
- **On this demo:**
  - the six bundled clips, with their cached explanations;
  - uploads of coordinate data (our template, Metrica, SkillCorner, Sportec/DFL, TRACAB, Second Spectrum, Hawk-Eye).
  - Uploads are visible only from the browser that made them, and are removed when the Space restarts.
  - Drone video is processed locally (see the GitHub README), not on this free server.
- **Data:** Sportec Open DFL Tracking and Event Data (Bassek et al., Scientific Data 2025, CC-BY 4.0); SoccerTrack (LGPL-3.0).

Built by Mohit ([@Mohitoo6](https://github.com/Mohitoo6)) and Rohit ([@Rohit-0612](https://github.com/Rohit-0612)).
