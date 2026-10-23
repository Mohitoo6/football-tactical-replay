# ⚽ Vyuh · football tactical replay

*Vyuh* is Sanskrit for a battle formation (the Mahabharata's Chakravyuh is the famous one); a football formation is the same idea.

[![tests](https://github.com/Mohitoo6/football-tactical-replay/actions/workflows/tests.yml/badge.svg)](https://github.com/Mohitoo6/football-tactical-replay/actions/workflows/tests.yml)

**Vyuh turns raw player-tracking data into a tactical story you can read in a minute.** Pick a moment, and you get a replay of all 22 players, each team's shape as it moves, the key numbers, and an AI coach's explanation in plain language. **Every number the AI writes is checked against the measured facts.**

**▶ Live demo: [huggingface.co/spaces/Mohitrks/vyuh](https://huggingface.co/spaces/Mohitrks/vyuh)**: six real clips with the replay, numbers and AI coach. Uploading your own data runs locally ([Run it](#run-it)).

![The replay screen: Musiala's winner with live team shapes and the AI coach's grounded explanation](docs/app-replay.jpg)

*Musiala's 89th-minute winner (1. FC Köln 1–2 FC Bayern München, 27 May 2023). Shaded areas are each team's outfield shape. The coach's text is checked against the measured facts: 26 numbers, clocks and shapes found, 5/5 changes on the right team.*

## Why this exists

**The data already exists.** In professional football, optical tracking systems such as TRACAB, Second Spectrum and Hawk-Eye film every match from cameras around the stadium. They record the position of every player and the ball 25 times a second. That is about **3 million positions per match** (measured on our two Bundesliga matches).

**The hard part is reading it.** A table of x and y numbers does not tell a coach why a goal was conceded. Today an analyst turns this data into clips, drawings and talking points by hand, for every moment that matters.

**Vyuh does that step for one moment at a time:**
- **Input:** the tracking data a club or league already receives, in its own format (or our simple CSV template). You choose a window of 3 to 120 seconds.
- **Output:**
  - a replay;
  - each team's shape, frame by frame;
  - the numbers that changed;
  - a short explanation: *what happened*, *what a coach would see*, *the key numbers*.

**Who it is for:**
- **Analysts** preparing a video session: the shapes and numbers are ready, and the explanation is a first draft to edit.
- **Coaches and players** reviewing a goal they scored or conceded, without reading raw data.
- **Scouts** checking how a team defends or attacks in real moments, not only on paper.
- **Media and fans** learning why a goal happened.

The core is coordinate data, the way the industry works. Turning raw drone video into the same data is an [experimental feature](#experimental-drone-video-to-tracking-data) we are still building.

## What it measures

All measurements are deterministic, tested code that runs on the positions. The AI does not compute any of them.

| Measurement | What it is | The tactical question it answers |
|---|---|---|
| **Width** | distance between a team's widest outfield players | Is the team stretching the pitch, or staying narrow and compact? |
| **Depth** | distance from the deepest to the most advanced outfield player | How far apart are the defence and the attack? |
| **Area** | area of the shape around all outfield players | How much space is there between the lines? (smaller = more compact) |
| **Back-line height** | average distance of the four deepest outfield players from their own goal | A high line that squeezes the pitch, or a deep block that protects the box? |
| **Players behind the ball** | outfield players between the ball and their own goal | How many defenders are goal-side? 0 means the defence has been bypassed. |
| **Ball zone** | the third and lane where the ball mostly was | Where is the play happening? |
| **Shape (formation)** | the closest formation template, e.g. 4-4-2 or 5-3-2 | How is the team set up in this moment, compared with the official lineup? |
| **Ball carriers** | the player nearest the ball, in order | Who had the ball, and how did it move between players and teams? |
| **Notable changes** | the biggest shifts, with match clocks | What changed during the move? (e.g. Köln's area fell from 757 to 388 m² as they dropped into their box) |

Each measurement is averaged over 2-second windows of ball-in-play time; stoppages are left out. The formation estimate is reliable for a team defending in a settled block, and weaker for a team in possession (see [Results](#results)).

## The AI coach: grounded, checked and evaluated

The AI engineering is in what the LLM is *not* allowed to do: invent a number, a player or an event. Each step below is there to stop that.

1. **Facts only.** The measurements above are turned into a compact JSON summary (~4 KB per clip). The LLM receives this summary, never the raw data and never a free hand.
2. **Rules in the prompt.** Use only numbers from the facts; keep each number with its team and metric; say "too little play" when there is too little play; three fixed sections, at most ~220 words.
3. **Free models, with fallbacks.** Gemini → Gemini → Groq → OpenRouter, all on free tiers. When one is busy (HTTP 429), the next is tried, and every answer is cached per clip.
4. **An automatic checker.** Every number, clock and formation in the answer must appear in the facts. If not, the model gets one chance to rewrite; then the answer is shown with a badge showing what was checked.

**Evaluation** (run with `scripts/evaluate_explanations.py`, last run 2026-10-23; [D34](DECISIONS.md)):

| Layer | What it checks | Result |
|---|---|---|
| Grounding | every number, clock and formation exists in the facts | **6/6 clips**, 176 values checked, 0 invented |
| Claims | every "from X to Y" change is on the right team, in the right order and direction | **24/24 right** |
| Coverage | the key facts are said: the goal and scorer, each team's shape, each team's biggest change | **96%** average (one change not mentioned) |
| Invented events | no passes, shots or tackles that are not in the facts | **0** |
| Trap tests | one fact is changed (goal removed, too little play, shape unknown, partial camera, mirrored numbers) and the coach must follow it | **5/5 passed** |
| Naive prompt, for comparison | the same facts with a simple prompt | invented a number and two names; the checker caught them |
| **Testing the checks** | 351 copies of the real explanations with one planted mistake each, at every place it can go | **283/351 caught** (below) |

**Do the checks themselves work?** A checker that passes everything would also give 6/6. So we planted mistakes in copies of the real explanations and ran the checks again (`scripts/plant_mistakes.py`, [results](evals/llm/checker_mutations.md)):
- **Caught every time:** a number not in the facts (96/96), a wrong clock (65/65) or formation (10/10), a change reversed (24/24) or given to the other team (24/24), an invented pass, cross, tackle, shot or header (30/30), and an invented player name (6/6, flagged for review).
- **The weak spot:** a *real* number from the clip put in the wrong place is caught only 28 times out of 96. The check knows the number exists, not always where it belongs; it catches it only inside a "from X to Y" claim.

**Why not RAGAS or an LLM judge?** RAGAS measures retrieval-augmented answers with an LLM as the judge (for example its *faithfulness* score). Here there is no retrieval: the facts are given, and every claim can be checked exactly. Code checks are free, give the same answer every run, and cannot be talked round. An LLM judge would add a second opinion on wording, the part code cannot check; it is a possible next step, not a replacement.

**What these numbers do not show:**
- The evaluation set is small (6 clips and 5 traps), and the checks are our own code, written for this task.
- The checks catch invented numbers, names and events, and numbers on the wrong team. They cannot judge whether a coaching point is wise, or catch a wrong word that is not a number. One example: in a trap answer the coach said the ball reached "the final third", which no fact supports.
- So each clip also has a human-review sheet ([evals/llm](evals/llm/README.md)). The first pass was done with Claude; a full read by us is still to do.

## Highlights for engineers

- **One analysis, many inputs.** Every input becomes the same standard clip after a quality report. The report refuses data it cannot analyse, and says why, instead of guessing.
  - our CSV/Excel template;
  - six provider formats read through [kloppy](https://kloppy.pysport.org): TRACAB, Second Spectrum, Hawk-Eye, Sportec/DFL (the Bundesliga's), Metrica and SkillCorner;
  - experimental: a raw top-view drone video.
- **A full product, not a notebook.**
  - FastAPI backend: clips, uploads, background jobs.
  - React web app.
  - 141 Python tests and 6 web tests, with CI.
  - A live static demo on Hugging Face Spaces, and a Docker image that runs the full app with uploads.
- **Decisions on record.** Every choice, with the alternatives and the evidence, is in [`DECISIONS.md`](DECISIONS.md).

## The web app

![Landing page of the Vyuh web app](docs/app-landing.jpg)

- **Library:** six real clips.
  - Four goals from Bundesliga optical tracking (25 frames per second, all 22 players and the ball).
  - Two clips computed from drone video.
- **Replay:**
  - the pitch animated from the data, with team shapes, width and depth, ball trail and shirt numbers;
  - for drone clips, the original video plays in sync beside the replay;
  - the **AI coach** tab (*What happened* · *Coach's view* · *Key numbers*), with a badge showing the grounding checks;
  - a **Numbers** tab with charts of each team's metrics, and an **Events** tab;
  - clocks in the text are clickable and jump to that moment.
- **New analysis:**
  - upload any of the inputs above;
  - for CSV files, a preview of the first moment before upload;
  - the quality report, then the new replay.

The same moment as an exported video (matplotlib renderer, used for offline clips):

![Musiala's 89th-minute winner for Bayern at Köln, with team shapes and live metrics](docs/demo.gif)

## How it works

```mermaid
flowchart LR
    U1[Your tracking data<br/>CSV / Excel template,<br/>Metrica · SkillCorner · DFL ·<br/>TRACAB · Second Spectrum · Hawk-Eye] --> Q{Quality report}
    U2[Top-view drone video] -->|stabilise · calibrate from lines ·<br/>detect · track · teams · ball| Q
    Q -->|refused: the reasons| R[Message to the user]
    Q -->|accepted| C[Clip<br/>frame · team · player · x · y · ball]
    C --> D[Geometry<br/>hull · width · depth · back line ·<br/>players behind ball · shape estimate]
    D --> F[Facts JSON<br/>~4 KB per clip]
    F --> G[LLM<br/>Gemini → Gemini → Groq → OpenRouter<br/>free tiers, cached]
    G --> H{Grounding + format check}
    H -->|problems| G
    H -->|pass| I[Explanation]
    D --> API[FastAPI backend<br/>clips · uploads · jobs]
    I --> API
    API --> FE[React web app]
```

**Core design principle:**
- Positions come from tracking data, so the geometry starts from real coordinates. The geometry itself is deterministic, tested code.
- The LLM sits only at the top and narrates facts it is given. It never computes or invents numbers, and a checker enforces that.

## Results

| What | How it was measured | Result |
|---|---|---|
| Data quality | 2 full matches, ~6.2 M player positions | 0 positions > 5 m off the pitch; ball never missing; tracking glitches in 0.004 % of moves |
| Orientation | Goalkeeper side per half, 2 matches | 4 / 4 halves correct |
| Generalisation | Ran the pipeline on a second match it was not built on | Worked after fixing 5 issues the first match never showed (D14) |
| Formation estimate | 5-min windows vs official DFL lineups | Settled defensive block: back line 100 %, official shape in top-2 79 %. Team in possession: poor (0–16 %) |
| AI coach | 6 clips, automatic checks + trap tests (D34) | 6/6 grounded; 24/24 claims right; 96 % key-fact coverage; 5/5 traps passed |
| Naive vs strict prompt | Same facts, two prompts | The naive prompt invented a number and two names (caught by the checker); the strict one did not |
| Tests | `uv run pytest`, `npm test` | 119 passing (+22 video tests with `--group video`), 6 web tests; LLM layer tested with fake clients (no network) |

Details: [`evals/formation_eval_J03WMX.md`](evals/formation_eval_J03WMX.md), [`evals/formation_eval_J03WN1.md`](evals/formation_eval_J03WN1.md), [`evals/llm/README.md`](evals/llm/README.md), [`evals/llm/scoreboard.md`](evals/llm/scoreboard.md), [`evals/llm/traps.md`](evals/llm/traps.md).

## Experimental: drone video to tracking data

**Why:** most clubs below the top leagues have no tracking system, but many can fly a drone over a match. If a video can become the same coordinate data, the whole analysis above works for them too.

**Status:** it works on the footage it was built and measured on (numbers below). A first test on another ground found new problems (below), and that work is ongoing.

The system finds the players and the ball itself:

1. Stabilise the hovering drone's drift.
2. Build an empty-pitch image (per-pixel median of the frames).
3. Calibrate from the painted pitch lines.
4. Detect players as blobs that differ from the empty pitch.
5. Track them with a colour-aware tracker, split teams by shirt colour (with an offside-logic goalkeeper rule) and follow the ball.

The result is exported as a normal clip (`clips/drone-0600-0630`), so the overlays and the AI coach work on it unchanged. It works on any clip file:

```bash
uv sync --group video
uv run --group video python scripts/process_video.py my_drone_clip.mp4 --render --explain
```

Before any tracking, the pipeline prints a **quality report**:
- clip length;
- pitch outline shape;
- calibration stable over the clip;
- camera holding still;
- plausible player count;
- enough pixels per metre of pitch (1080p of a full pitch is fine; 720p is not).

If a check fails, it refuses the clip instead of producing wrong positions.

**Accuracy.** Measured on **20 × 30 s SoccerTrack segments** of one match:
- 13 segments were used while building, and 7 were never seen.
- Five of the unseen ones were processed before their ground truth was downloaded.
- The ground truth is used **only for scoring**, with its calibration corrected per segment because the drone drifts ([evals/video](evals/video/README.md), [D19–D30](DECISIONS.md)).

| What | 13 tuned segments: median (worst) | 6 accepted unseen segments: median (worst) |
|---|---|---|
| Players found (recall) | 98.6% (97.7%) | 96.9% (80.0%) |
| Position error, automatic calibration (no hand-marked points) | 0.35 m (0.52 m) | 0.44 m (0.55 m) |
| Identity kept (purity) | 97.4% (91.4%) | 92.5% (84.6%) |
| Correct team | 98.2% (94.3%) | 92.5% (89.5%) |
| Ball correct, all frames | 63% (34%) | 55% (22%) |

- The unseen numbers are the honest ones.
- The quality report refused one unseen segment.
- The ball is the weak part: it is often hidden at players' feet (D25).
- Speed: ~2 min per 30 s of 4K video on an Apple M2 (offline).
- A pretrained deep detector (RF-DETR, tiled) found only 43% of players from straight above, at 100× the cost, so the classical method was kept.

**Robustness** ([evals/video/robustness.md](evals/video/robustness.md), [D27](DECISIONS.md)):
- One segment was edited the ways real clips differ: rotated 90° and 180°, cropped, 30% darker, 1080p, 20 s, 25 fps.
- The pipeline still found 98% of players within 0.55 m on every copy.
- A copy with a goal line cut off, and a 720p copy, were refused.

**Next steps:**
- **A second ground.** The first test on another ground (NASK, Poland) found six failure modes.
  - One is fixed: the calibration check mistook the halfway line for the end of the pitch (D35).
  - Fixes for two more (painted lines and goal nets taken for players) are written and being verified.
  - Still open: light changing during the clip, sun shadows, people on the touchline, and players standing still.
- **The ball.** The ball is found correctly in about 55–63% of frames. A full-resolution ball detector is being tested (D25).
- **Online processing.** Today drone video is processed on the user's machine. Free hosting with enough computing power for video is the open question.

## Experiment: TV broadcast footage (branch `broadcast-experiment`)

We also tried the usual panning TV camera:
- the camera calibrated in every frame;
- players and ball found with RF-DETR;
- the analysis drawn on the footage.

- **Result:** on one hand-labelled Euro 2020 clip it found 90% of players, but confirmed the ball in only ~20% of frames.
- **Why it is on its own branch:** free broadcast footage to test it on does not exist (broadcast rights), so the drone pipeline stayed the product.
- **Details:** [D28, D29 and D31](DECISIONS.md) and [evals/broadcast](evals/broadcast/README.md).

## Use your own data

Two ways in, one analysis. Both go through a quality report that refuses data it cannot analyse, and says why.

1. **Tracking (coordinate) data:**
   - **Our template**, CSV or Excel ([`templates/tracking_template.csv`](templates/tracking_template.csv)), with one row per player (and the ball) per moment:

     | Column | Meaning |
     |---|---|
     | `time_s` | seconds from the start of the clip |
     | `team` | `home`, `away` or `ball` |
     | `player` | name or number |
     | `x`, `y` | position |
     | `jersey`, `position` | optional; `GK` marks a keeper, otherwise the deepest player in front of goal is taken |

     Positions can be in metres from the centre spot, metres from a corner, or 0–1 along each side. A full example is [`templates/example_musiala_winner.csv`](templates/example_musiala_winner.csv).
   - **Provider formats** through kloppy, cut to a window of up to 120 s:

     | Provider | Files |
     |---|---|
     | Metrica Sports | home CSV + away CSV |
     | SkillCorner | match JSON + tracking JSONL |
     | Sportec / DFL | match information XML + positions XML |
     | TRACAB | metadata XML/JSON + tracking `.dat`/JSON |
     | Second Spectrum | metadata XML/JSON + tracking JSONL |
     | Hawk-Eye | ball files + player centroid files (one per minute; several allowed) |

   - **Tested on:**
     - the example file, which reproduces the bundled clip to 0.01 m;
     - Metrica open data;
     - SkillCorner open data (10 fps);
     - kloppy's sample files for TRACAB, Second Spectrum and Hawk-Eye. A Hawk-Eye minute goes all the way to a clip and a grounded explanation (D37).
2. **A top-view drone video (experimental):** see [above](#experimental-drone-video-to-tracking-data). It runs locally (minutes of processing).

**Accepted data needs:**
- 3–120 s at 5–60 frames per second;
- at least 7 players per team;
- positions on the pitch (otherwise the units are probably wrong).

**Ball:** without the ball the shapes are still measured, but there are no ball-based facts.

## Backend API

```bash
uv run uvicorn tactics.api:app --reload     # interactive docs at http://localhost:8000/docs
```

| Endpoint | What it does |
|---|---|
| `GET /api/clips` | every clip (bundled and uploaded) |
| `GET /api/clips/{id}?step=2` | frames, players, ball, team shapes (hull, width, depth, area, back line), facts, explanation and its checks; ~76 KB gzipped |
| `GET /api/clips/{id}/source` | the original drone video, to play beside the replay |
| `POST /api/clips/{id}/explanation` | the coach's explanation (cached; one LLM call on a miss) |
| `POST /api/uploads/tracking` | template CSV/Excel → clip, or the reasons it was refused |
| `POST /api/uploads/provider` | provider files + time window → clip |
| `POST /api/uploads/drone`, `GET /api/jobs/{id}` | drone video as a background job with progress (local, needs `--group video`) |
| `GET /api/template`, `GET /api/template/example` | the template and the example file |

Uploaded clips are stored in `data/user_clips/` (git-ignored).

## Run it

**Requirements:**
- macOS or Linux;
- Python 3.11+ with [uv](https://docs.astral.sh/uv/);
- Node.js 20.19+ or 22.12+ for the web app.

The six clips, their videos and explanations are in the repo, so **the app needs no data download and no API keys**.

```bash
git clone https://github.com/Mohitoo6/football-tactical-replay.git
cd football-tactical-replay
uv sync
uv run uvicorn tactics.api:app --reload        # backend API: http://localhost:8000/docs

# in a second terminal: the web app (http://localhost:5173, /api is proxied to the backend)
cd web
npm install --legacy-peer-deps
npm run dev
```

**Tests:**

```bash
uv run pytest                                  # 119 tests (video tests skip without --group video)
cd web && npm test                             # 6 tests
```

**With Docker** (the full app with uploads, as one container: http://localhost:7860):

```bash
docker build -t vyuh .
docker run -p 7860:7860 --env-file .env vyuh   # .env (free LLM keys) is only needed for new explanations
```

**Quick viewer without Node:** `uv run streamlit run app/streamlit_app.py` (http://localhost:8501).

### Rebuild everything from raw data (optional)

1. Download a match's three XML files (match information, events, positions) from the [Sportec Open DFL dataset on figshare](https://doi.org/10.6084/m9.figshare.28196177) into `data/raw/dfl/` (git-ignored). Each positions file is ~400 MB.
2. Then:

```bash
uv run python scripts/check_match.py J03WMX        # health report + suggested clips for every goal
uv run python scripts/build_clips.py               # clips defined in clips/clips.toml
uv run python scripts/render_clip.py --for-app     # videos (needs ffmpeg: brew install ffmpeg)
cp .env.example .env                               # add free API keys (Gemini, Groq, OpenRouter)
uv run python scripts/generate_explanations.py     # cached per clip; re-runs cost nothing
uv run python scripts/evaluate_explanations.py     # scoreboard of the explanations (add --traps for the trap tests)
uv run python scripts/evaluate_formations.py J03WMX
```

## Project layout

```
src/tactics/
  service.py the backend in one place: list, read, create (template, provider, drone video) and explain clips
  api.py     FastAPI app over service.py
  data/      load DFL tracking with kloppy, orient, validate, build/save clips; upload.py reads user data
  video/     drone video to tracking: stabilise, calibrate from lines, detect, track, teams, ball
  geometry/  shape metrics, formation template matching, formation-line links
  viz/       pitch drawing and animation (one FramePainter for stills and video)
  ai/        facts summary, prompt, LLM client with fallbacks/cache/repair, grounding check, evaluation
web/         React + TypeScript web app (Vite): landing page, library, replay + AI coach, upload
templates/   upload template and a full example file
deploy/      the online demo's Space card (scripts/deploy_space.sh builds and uploads the demo; Dockerfile runs the full app)
app/         Streamlit test viewer
scripts/     offline pipeline: check_match, build_clips, render_clip, generate/evaluate explanations, evaluate_formations
clips/       committed clips: players/ball parquet, meta, summary, explanation, video
evals/       formation, video and LLM evaluations
tests/       119 tests + 22 video tests
```

## Scope and limitations

- **Moments, not full matches.**
  - Vyuh explains clips of 3–120 s. This was a scope choice: a full match loads fine on a laptop.
  - Full-match reports would need more design: load a match once, split it into phases, and summarise in two steps (per phase, then the match).
- **Positions only.** The coach does not read pass, shot or tackle event feeds. "Ball carrier" means the nearest player to the ball.
- **Formation estimate:** reliable for a settled defensive block, not for a team in possession, which reshapes as it attacks.
- **Coaching judgement:** the checks catch wrong numbers, teams and directions, but whether a coaching point is wise still needs human review (`evals/llm/`).
- **Industry feeds:** TRACAB, Second Spectrum and Hawk-Eye are tested on sample files only, because full matches are licensed to clubs. Wrong or mismatched files are refused with a reason (23 cases tested, D39).
- **Memory:** reading a full-match Bundesliga positions file (400 MB of XML) takes ~30 s and ~5.5 GB of memory. That is fine on a laptop, too much for a small free server.
- **Drone video (experimental):**
  - It needs a hovering top-down camera with the whole pitch in view, and it was tuned on one ground.
  - A first test on another ground (NASK, Poland) found new failure modes: lighting changes, shadows, people on the touchline. That work is in progress.
- **Free hosting:** the online demo is a static site (free Docker hosting now needs a paid plan). It shows the six clips with their cached explanations; uploads and new explanations run locally or in Docker.

## Data and attribution

- **Tracking and event data:** **Sportec Open DFL Tracking and Event Data**. Bassek, M., Rein, R., Weber, H. & Memmert, D. *An integrated dataset of spatiotemporal and event data in elite soccer.* Scientific Data 12, 195 (2025). doi:[10.1038/s41597-025-04505-y](https://doi.org/10.1038/s41597-025-04505-y). Licensed **CC-BY 4.0**.
- **Drone video and ground truth:** **SoccerTrack**, Scott et al., CVPR Workshops 2022 ([Kaggle](https://www.kaggle.com/datasets/atomscott/soccertrack)), LGPL-3.0. The drone clips contain positions we computed, a rendered video, and the matching 30 s of the original video (re-encoded, same LGPL-3.0 licence) to play beside the replay. The full raw videos are not redistributed.
- **Upload testing (not redistributed):**
  - Metrica Sports sample data ([github.com/metrica-sports/sample-data](https://github.com/metrica-sports/sample-data));
  - SkillCorner open data ([github.com/SkillCorner/opendata](https://github.com/SkillCorner/opendata));
  - the NASK top-view dataset ([Zenodo 14867795](https://zenodo.org/records/14867795), CC BY 4.0);
  - kloppy's sample provider files.
- **Images on the web app:** sources and licences in [`web/public/img/CREDITS.md`](web/public/img/CREDITS.md).
- **Built with:**
  - Python: kloppy, mplsoccer, numpy, scipy, pandas, OpenCV, FastAPI, Streamlit;
  - web: React, Vite, GSAP;
  - LLMs: the OpenAI-compatible APIs of Google Gemini, Groq and OpenRouter.

## License

- **Code:** [MIT](LICENSE).
- **Data:** the tracking-derived files in `clips/` (positions, summaries, videos) come from the Sportec Open DFL dataset and remain under **CC-BY 4.0**. If you reuse them, credit Bassek et al. (2025) as above.

## Authors

Co-built by two brothers:

- **Rohit** ([@Rohit-0612](https://github.com/Rohit-0612)): Phases 1–4.
  - data pipeline, orientation and validation;
  - geometry and formation detection;
  - visualisation.
- **Mohit** ([@Mohitoo6](https://github.com/Mohitoo6)):
  - the AI layer (facts summary, prompts, fallbacks, caching, grounding, repair) and its evaluation (Phases 5–6);
  - video-to-tracking from drone footage (Phase 7) and the TV-footage experiment (Phase 8);
  - the backend API (Phase 9) and the web app.

Developed with Claude Code as a pair programmer; every decision and its evidence is recorded in `DECISIONS.md`.
