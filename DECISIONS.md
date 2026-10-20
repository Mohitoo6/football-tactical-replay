# Decision Log

Each entry: the decision, alternatives considered, why we chose it, and known limitations.
Entries marked *(pending spike)* still need evidence from a test run.

---

## D1. Primary dataset: DFL / Sportec open data; Metrica as fallback and test fixture
*2026-10-10 · verified by `scripts/spike_phase0.py`*

- **Decision:** Use the Sportec Open DFL Tracking and Event Data (Bassek et al., 2025: 7 Bundesliga / 2. Bundesliga matches, 2022/23) as the main data source. Use Metrica Sports sample data for lightweight tests and as a fallback.
- **Alternatives:** Metrica Sports sample data (anonymised, 3 matches); SkillCorner open data (10 A-League matches, MIT license, but broadcast tracking at 10 fps with extrapolated off-camera players and ~97% identity accuracy).
- **Why:**
  - Real team and player names make the demo much clearer.
  - CC-BY 4.0 explicitly allows redistributing derived clip files, as long as we give attribution.
  - The match metadata includes the official formation (e.g. `4-2-3-1`), which gives us ground truth to evaluate our formation detection.
  - It is optical tracking at 25 Hz with full 22-player coverage.
- **Evidence (Phase 0 spike, Apple M2 / 16 GB, kloppy 3.19.1):**

  | | DFL J03WMX (Köln v Bayern) | Metrica sample game 1 |
  |---|---|---|
  | Frames | 145,967 at 25 fps | 145,006 at 25 fps |
  | Load time | 67 s (cold), 27 s (warm file cache) | 45 s (includes download) |
  | Peak memory | 3.9–4.2 GB | 1.7–2.4 GB |
  | Players with x/y in a mid-game frame | 11 + 11 | 11 + 11 |
  | Frames without ball position | 0.0% | 39.1% |
  | Real names | Yes ("F. Kainz", "E. Choupo-Moting") | No ("Home", "Away") |

- **Limitations:**
  - Each match's tracking file is a ~350–420 MB XML, so parsing is slow and memory-heavy. That is acceptable because we parse it once, offline (D2).
  - There are only 7 matches.
  - kloppy does not expose the official formation (`starting_formation` is `None`). We read the `LineUp` attribute from the match-information XML ourselves.
  - Metrica's terms are informal ("be responsible", attribution requested), with no formal license. Its ball position is missing in 39% of frames, which needs investigating before we use it.

## D2. Preprocess raw data once into small per-clip files
*2026-10-10*

- **Decision:** `scripts/build_clips.py` parses the raw data offline and writes 15–25 s clips defined in `clips/clips.toml`. Each clip is a folder: `clips/<clip_id>/players.parquet` (one row per player per frame), `ball.parquet` (one row per frame) and `meta.json` (teams, official formations, times, attribution). The app and tests read only these files.
- **Evidence:** A 20 s clip at 25 fps is about 90–120 KB. Building all three clips takes ~30 s, almost all of it loading the raw match.
- **Alternatives:** Parse the raw XML inside the app on demand; store the full match as parquet.
- **Why:** The app starts fast, the free hosting needs no large files, and the raw data never leaves the developer's machine (`data/raw/` is git-ignored).
- **Limitations:** Only pre-built clips are available in the app. To add a clip, you re-run the script locally.

## D3. Normalised coordinate system
*2026-10-10 · verified: kloppy's `secondspectrum` coordinates match this system*

- **Decision:** All positions are in metres with the pitch centre at (0, 0). Normalisation happens in two steps:
  1. **Per match** (`load.orient_home_left_to_right`): for each period, if the home goalkeeper's average x is positive, rotate that period by 180°. After this step the home team attacks left → right in both halves.
  2. **Per clip** (`normalize.orient_for_team`): each clip has a `focus_team`. If that team is away, rotate the whole clip by 180°, so the focus team always attacks left → right.
- **Alternatives:**
  - Keep each provider's native coordinates.
  - Use kloppy's `transform(to_orientation=...)`.
  - Flip per frame by ball possession. This was rejected because it makes the animation jump every time possession changes.
- **Why:**
  - Teams switch ends at half-time. Without a fixed direction, "the line pushed up" would mean opposite things in each half, and the geometry and the LLM summary would both be wrong.
  - The goalkeeper rule is easy to explain and easy to test, and it needs no knowledge of kloppy's orientation semantics.
  - We rotate by 180° instead of mirroring x, so a team's left wing stays on its left.
- **Evidence:** In all three built clips, the focus team's keeper is on the left and the opponent's keeper is at the right goal (x ≈ 42–52). The ball reaches x ≈ 52.5–55 at the exact goal times from the event data. A deliberate bug in the rule makes 2 tests fail.
- **Limitations:** The rule assumes the starting home goalkeeper stays in his half for most of each period, which held in the data we checked. Within a clip, the direction is fixed for the focus team even when the other team has the ball.

## D4. One OpenAI-compatible LLM client for all providers
*2026-10-10*

- **Decision:** Use the `openai` Python SDK. Gemini, Groq and OpenRouter differ only in `base_url`, model and API key (set in `.env`).
- **Alternatives:** One official SDK per provider (`google-genai`, `groq`, …); LiteLLM.
- **Why:** One code path and one dependency. Switching provider is a config change, not a code change.
- **Evidence (2026-10-11):**
  - All three providers work through one `openai` client (v3.28): Gemini `gemini-3.8-flash`, Groq `openai/gpt-oss-120b` and OpenRouter `nvidia/nemotron-3-super-120b-a12b:free`.
  - Free-tier reality showed up on day one:
    - Groq had removed `llama-3.3-70b-versatile` (404).
    - OpenRouter's Gemma models were rate-limited upstream (429).
    - Gemini returned 503 "high demand" on one call.
    - Gemini 3.x spends output tokens on "thinking", so with a small `max_tokens` the answer was empty. We set `reasoning_effort=low` and `max_tokens=2000`.
- **Limitations:**
  - Gemini's OpenAI compatibility is labelled beta, and unsupported parameters are silently ignored. If this causes problems, we swap `google-genai` in for that provider only.
  - Free model lists change often, so `.env.example` records the date the models were checked.

## D5. Pre-generate and commit LLM explanations
*2026-10-10*

- **Decision:** `scripts/generate_explanations.py` writes `clips/<clip_id>.explanation.json`, keyed by a hash of (summary + prompt). The app shows the cached text and calls the LLM only on a cache miss, with backoff on HTTP 429 and then the fallback provider.
- **Alternatives:** Call the LLM live on every view.
- **Why:** Free tiers have strict rate limits. The deployed demo then works without an API key and never hits a rate limit in front of an interviewer.
- **Evidence:** A re-run reuses `clips/<id>/explanation.json` with no API call, and changing the facts or the prompt changes the key and triggers one new call (unit-tested with a fake client). Retries cover 429, 5xx, timeouts and connection errors (pauses of 5 s and 10 s, three attempts per provider); 4xx errors such as a bad key or unknown model skip straight to the next provider.
- **Limitations:** Explanations are static until regenerated.

## D6. Automatic grounding check on LLM output
*2026-10-10*

- **Decision:** A checker extracts every number and player name from the LLM's explanation and verifies that each one appears in the structured input summary. Anything unmatched gets flagged. Outputs are saved to `evals/` with a manual checklist.
- **Alternatives:** Manual review only; an LLM-as-judge.
- **Why:** The LLM must never invent facts. A deterministic check is cheap, explainable and makes no extra API calls.
- **Evidence (`evals/llm/README.md`):**
  - All 4 clip explanations pass (21–30 numbers, clocks and formations checked each).
  - On the same facts, a naive "football pundit" prompt failed the check. It wrote "300" for 301, and pulled "Jamal" Musiala and "João" Cancelo from the model's own knowledge. All three were caught.
  - Disabling the number check makes a unit test fail.
- **Limitations:**
  - It catches invented numbers, clocks, formations and names, but not invented qualitative claims. The naive prompt's "slips it", "bottom corner" and "title race" all passed unflagged. Those still need the manual checklist.
  - The name check is a heuristic (capitalised words not in the facts).

## D7. Animation: matplotlib for exports, Plotly in the app
*2026-10-10 · (pending spike for Plotly smoothness)*

- **Decision:** Use matplotlib + mplsoccer to render MP4/GIF files for the README and checks. Use Plotly animation frames (subsampled to ~10 fps) for interactive playback in Streamlit.
- **Alternatives:** Show pre-rendered videos in the app (smooth but not interactive); a custom HTML canvas component (smooth and interactive, but more code to maintain).
- **Why:** Both are mature libraries with little custom code.
- **Evidence (export half):** `scripts/render_clip.py` renders the 23 s Musiala clip to MP4 (576 frames, 25 fps, 23.04 s, 3.4 MB, ~28 s to render) and GIF (288 frames × 80 ms = 23.04 s, 2.2 MB). Both play in real time. The video frame at 17 s matches the Phase 2 still for the same moment. Stills and video share one drawing class (`FramePainter`), so they cannot drift apart.
- **Limitations:** Plotly can get choppy with many frames and shapes. If so, we revisit this choice. MP4 export needs ffmpeg installed (GIF does not).

## D8. Formation detection by template matching
*2026-10-11 · evaluated in `evals/formation_eval.md`*

- **Decision:**
  1. Average each regular outfield player's position over a time window, oriented so the team attacks towards +x.
  2. Rescale that shape and 11 formation templates (4-4-2, 4-3-3, 4-2-3-1, 4-1-4-1, …) to the same 0..1 box.
  3. Pair players with template dots using the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`).
  4. Pick the template with the lowest mean squared distance. The pairing also gives each player a line: defence, midfield or attack.
- **Alternatives:**
  - Split players into lines at the largest depth gaps. This is simpler but cannot tell 4-2-3-1 from 4-5-1.
  - Clustering-based role assignment. This is more powerful but much more complex.
- **Why:**
  - It uses the whole 2-D shape, not just depth.
  - It needs no new dependency.
  - It can be explained in one sentence: "match the team's average shape to the closest standard formation."
  - It also produces the line assignment we use for the connection lines (D13).
  - Every template is recovered from its own shuffled, noisy copy (unit test).
- **Evidence (J03WMX, 5-min windows, ball in play):**

  | Team (official 4-2-3-1) | Variant | Exact | Official in top 2 | Back-line count correct |
  |---|---|---|---|---|
  | Köln | out of possession | 58% | 79% | 100% |
  | Köln | all frames | 40% | 70% | 80% |
  | Bayern | out of possession | 10% | 20% | 60% |
  | Bayern | in possession | 0% | 0% | 16% |
  | Bochum (official "4-3-3 Double-6", compared as 4-3-3) | all frames | 10% | 35% | 70% |
  | Bochum | in possession | 15% | 55% | 65% |
  | Leverkusen | — | only 1 window before a 7th-minute red card | | |

  Second match: J03WN1. For Bochum the detector most often says 4-2-3-1 (6 of 20 windows). A 4-3-3 with a "double six" (two holding midfielders) is close to a 4-2-3-1, so 30% exact if you accept that mapping. We report the stricter number.

- **Interpretation:**
  - The detector is reliable for a settled defensive block. Köln defended for most of this match.
  - It is poor for a team in possession. With the ball, Bayern looks like a 3-4-3 in 14 of 19 windows. This is consistent with a full-back pushing up, but the official data cannot confirm it.
  - Most errors are close neighbours (4-1-4-1 vs 4-2-3-1 differ only in midfield).
  - The official lineup is a nominal starting label, not the shape a team holds in every phase.
- **Limitations:**
  - It has been evaluated on two matches (4 teams, one of which played 83 minutes with 10 men). The other 5 open matches would give a better estimate.
  - Templates assume 10 outfield players. Windows or clips with fewer (red cards) are excluded from the evaluation and labelled "n/a" in the app.
  - Official labels can carry extra words ("4-3-3 Double-6"). `base_formation` keeps only the numbers.
  - Templates assume evenly spaced lines.
  - In the app we label the result "shape in clip", never as a fact about the team's formation.

## D9. Collaboration: one shared repo, honest co-credit, split ownership
*2026-10-10*

- **Decision:** Mohit (`Mohitoo6`) and Rohit (`Rohit-0612`) build the project together in one repository. Both credit it as co-built. Ownership:
  - **Rohit:** data and geometry (Phases 1–4).
  - **Mohit:** AI layer, app and deployment (Phases 5–6).
- **Alternatives:** Two copies of the repo, one under each account, with each person's commits hidden from the other (rejected); two fully separate projects.
- **Why:**
  - Git authorship reflects who actually wrote each part.
  - Each person can explain their own part in depth in interviews.
  - Two identical repos under different names would look like copying.
- **Limitations:** Commits are made on a shared machine, so the repo-local git identity has to be set to whoever is working before each session.

## D10. Tooling: uv, kloppy, mplsoccer, scipy (no shapely)
*2026-10-10*

- **Decision:**
  - `uv` for environments and the lockfile.
  - `kloppy` 3.19 for loading tracking data.
  - `mplsoccer` 1.8 for pitch drawing.
  - `numpy` + `scipy.spatial` for geometry.
- **Alternatives:** pip + venv; hand-written parsers per provider; `shapely` for polygons.
- **Why:**
  - `uv` gives a pinned, reproducible install in one command.
  - `kloppy` already supports both of our datasets through one data model.
  - `scipy`'s `ConvexHull` gives hull area and vertices, which is all we need, so `shapely` would be an unnecessary dependency.
- **Evidence:** kloppy 3.19.1 and mplsoccer 1.8.1 work with pandas 3.0.6 / numpy 2.4.6 (both spikes ran without errors and produced the expected frame plots). Loading with `coordinates="secondspectrum"` gives metres with the origin at the pitch centre (−52.5..52.5 × −34..34), which matches D3 with no custom conversion.
- **Limitations:** We rely on kloppy's parsers being correct. Positions slightly outside the pitch (up to ~6 m past the lines) are normal: players and the ball do leave the field. So any bounds checks need a margin.

## D11. Hide the ball while it is out of play
*2026-10-10*

- **Decision:** When the provider marks the ball as dead (`alive = False`), we do not draw it. A "Ball out of play" label appears instead. Validation also ignores the ball's position during dead-ball frames.
- **Alternatives:** Draw the frozen position; draw it faded; interpolate a guessed position.
- **Why:** In all three clips the ball's position is frozen during every dead-ball frame (it moves in 0 of 145, 486 and 123 dead frames). For the Ljubicic penalty, the frozen ball sits about 18 m from the penalty spot, then "jumps" to the spot at 457 m/s on the kick. Drawing a position we know is wrong would mislead viewers. Guessing a position would break the rule that we never invent data.
- **Limitations:**
  - During stoppages (throw-ins, penalties) viewers do not see where the ball is.
  - Live-ball tracking still has rare one-frame glitches (e.g. a single 51 m/s step in the Coman clip). We leave them unsmoothed because they are barely visible.

## D12. Player-speed sanity check
*2026-10-10*

- **Decision:** `validate.find_problems` flags any player moving faster than 12 m/s between consecutive frames.
- **Why:** Top sprinters reach about 10 m/s, so anything faster is a tracking jump. In our clips the fastest player is Leroy Sané at 9.4 m/s, and 99% of moves are under 8 m/s.
- **Limitations:** It catches teleport-style jumps but not small, plausible-looking errors.

## D13. Shape overlays: outfield hull, formation-line links, per-frame metrics
*2026-10-11*

- **Decision:** For each team in each frame we draw the convex hull of the outfield players, and lines joining neighbouring team-mates (ordered across the pitch) within each formation line. The metrics shown under the pitch are:
  - width (y range)
  - depth (x range)
  - hull area (m²)
  - defensive line height (distance from own goal to the deepest outfield player)

  Formation lines are assigned once per clip, from frames with the ball in play.
- **Alternatives:**
  - Delaunay "nearest neighbour" meshes. These are too busy to read.
  - Re-assigning lines every frame. This makes the lines flicker.
  - Including the goalkeeper. This distorts depth and area by 30+ m.
- **Why:** It is TV-analysis style (back four, midfield line), it is stable over the clip, and every number comes from pure, tested functions in `geometry/`. The overlay tests check that the drawn hull, links and metrics equal those functions' outputs.
- **Evidence:** Over the Musiala clip, Köln's block shrinks from 760 to 277 m², and its defensive line drops from 14 m to 5 m from goal by the time of the shot. Meanwhile Bayern's deepest defender moves from 39 m to 65 m from his own goal.
- **Limitations:**
  - Metrics are meaningless during dead-ball moments, e.g. a goal celebration ("line 77 m from goal"). Phase 5 summaries must use ball-in-play frames only.
  - In attacking phases, a formation line can stretch the length of the pitch, which reads as a long diagonal.

## D14. Generalization check on a second match
*2026-10-11*

- **Decision:**
  - `scripts/check_match.py <match_id>` runs our checks on every frame of a match, not just on clips.
  - Validation is split into **problems** (data unusable, the clip is rejected) and **warnings** (rare tracking jumps).
  - Before calling a feature general, we test it on a match we did not build it on.
- **Why:** Our first three clips all came from one match. Running the full pipeline on Bochum v Leverkusen (J03WN1) found five issues that the clips never showed:
  1. Frame numbers restart each period, so the "consecutive frames" check failed on full matches.
  2. Single-frame tracking jumps are real but rare (16 of 3.2 M moves in J03WMX, 239 of 3.0 M in J03WN1, mostly near the touchlines). Treating them as errors would reject good clips.
  3. Official formation labels can include extra words ("4-3-3 Double-6").
  4. Red cards: Leverkusen had 10 players for 83 minutes, but our clip test assumed 11 v 11 and formation templates assume 10 outfield players.
  5. Clip ids built from player names contained non-ASCII letters ("förster").
- **Evidence:** With these fixes, J03WN1 works with no code specific to it:
  - Orientation is correct in both periods (home keeper at x = −32.7 / −38.0).
  - No positions are more than 5 m outside the pitch.
  - No ball position is missing.
  - The data matches the events (red card at 7:03; 3 Bochum goals; result 3:0).
  - A new clip (`forster-opener`) builds, validates and renders (501 frames, 20.04 s).
  - Rebuilding the original clips reproduced their files byte for byte.
- **Limitations:**
  - Only DFL data is supported end-to-end. Another provider (e.g. Metrica) needs its own loader, because formations, goals and file naming are provider-specific.
  - The defensive-line height uses the single deepest outfield player, so one player on the goal line gives "1 m from goal". The Phase 5 summaries should use a more robust measure (e.g. the average of the back line).

## D15. Parallel tracks: AI layer and video-to-tracking
*2026-10-11*

- **Decision:** Add Phase 7, which turns top-view video into our clean tracking table, owned by Rohit on the branch `video-to-tracking`. In parallel, Mohit builds Phase 5 (AI explanation) and Phase 6 (app) on `main`.
- **Alternatives:** Video module first, then AI. AI and app first, then video.
- **Why:**
  - The clean table (frame, team, player, x, y) separates the two pieces of work. The AI layer only reads geometry outputs, which already exist, so it does not depend on where the coordinates come from.
  - Running both tracks keeps each person's ownership clear, and the AI part of this AI Engineer project does not wait behind the riskiest component.
- **Update (2026-10-11):** Rohit was unavailable, so Mohit took over Phase 7. The two branch commits first made under Rohit's name were re-authored to Mohit before being pushed, so the history shows who did the work.
- **Limitations:**
  - Phase 7 brings back the computer-vision accuracy risk that the original design avoided, so its output must be measured against ground truth before we trust it.
  - The detector models' licenses (e.g. AGPL for some YOLO versions) matter if the project is ever sold.
  - Two branches on one shared machine need discipline when switching driver.

## D16. What the LLM sees: a compact summary of ball-in-play facts
*2026-10-11*

- **Decision:** `ai/summary.py` builds a ~4 KB JSON per clip containing:
  - clip times and seconds of open play
  - each team's official formation, players on the pitch and "shape in clip"
  - goals from the DFL events
  - ball carriers (nearest player within 1.5 m, ball below 1 m, held for at least 0.12 s)
  - width, depth, area and back line per 2-second window
  - changes from the first to the last window above set thresholds
  - plain-language definitions of every metric

  Only ball-in-play frames up to the goal are used. The back line is the average of the 4 deepest outfield players, both in the summary and in the video overlay. The prompt (`ai/prompt.py`, v1) forbids outside knowledge, new numbers (no differences or durations) and invented event types.
- **Alternatives:** Send raw per-frame positions (far too large, and the model would do the maths); send only start and end values (loses the story).
- **Why:**
  - The model narrates numbers our tested code computed. It never computes them itself.
  - A small, fixed structure is cheap on free-tier token limits and easy to check.
  - Definitions let the model explain terms without making them up.
- **Evidence:**
  - Three issues found by reviewing real outputs were fixed in the facts, not the prompt:
    1. Post-goal frames inflated the last window, so we stop at the goal.
    2. One defender on the goal line dragged "defensive line" to ~1 m, so we use the back-line average.
    3. A penalty clip with 1 s of open play got a confident shape label, so under 5 s the shape is "n/a". The model then said so itself.
- **Limitations:**
  - "Ball carrier" is proximity, not possession: a defender running past the ball can appear.
  - Change thresholds (5 m, 150 m²) are hand-picked.
  - The model sometimes exceeds the 180-word target or adds causal words ("forced").

## D17. Coach-style explanations with a repair step
*2026-10-11*

- **Decision:** The answer has three sections:
  - **What happened**: facts only, same strict rules as before.
  - **Coach's view**: 2–3 points that may apply *general* football principles (what a deep compact block protects and gives away, what a high back line risks, what players behind the ball means). Each point must be tied to a stated fact and phrased as interpretation.
  - **Key numbers**.

  Two more facts give the coach something to reason with: players behind the ball and ball zone (third and lane), per 2-second window. If grounding or format checks find problems, the model gets **one** rewrite with the list of problems; the rewrite is kept only if it has fewer problems, and the first answer is stored in the record. Cached answers are reused only if they still pass the checks.
- **Alternatives:**
  - Keep facts-only narration. This is safer but less useful.
  - Let the model use its own knowledge of the teams. Rejected: that is exactly where "Jamal" Musiala and "title race" came from.
  - Fine-tuning. Not possible on the free tier, and not needed.
- **Why:** A viewer wants to know *why* a shape mattered, not just the numbers. Separating interpretation from facts keeps the facts checkable while allowing coaching insight.
- **Evidence (`evals/llm/README.md`):**
  - All 4 clips pass grounding and format checks on prompt v3. One answer was repaired live (238 → 212 words).
  - Coaching points were reviewed against the facts: the compact-block point (Musiala) is sound; the bypassed defence (Förster) is read correctly after the definition fix.
  - The penalty clip says there is too little open play instead of speculating.
  - Free tier, measured: `gemini-3.8-flash` allows **20 requests/day per model** (429 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`), far below figures quoted by blogs. So the chain is now gemini-3.8-flash → gemini-3.6-flash (separate quota) → Groq → OpenRouter.
- **Limitations:**
  - The automatic check verifies that each number exists in the facts, not that it is attached to the right team or metric. That, and the soundness of coaching reasoning, need human review.
  - Interpretation quality varies by model (the Groq fallback speculated more).
  - With 20 calls/day, regenerating all clips more than a few times a day exhausts the primary model.

## D18. The app plays pre-rendered videos instead of a Plotly animation
*2026-10-11 · replaces the app half of D7*

- **Decision:** The Streamlit app plays the MP4 that `render_clip.py --for-app` renders with the same `FramePainter` as the stills. Interactive parts are a chart of the shape metrics over time and the facts JSON. The app never calls an LLM. It shows the cached explanation and re-runs the grounding check live (no API needed).
- **Alternatives:**
  - Plotly animation frames (planned in D7). They are interactive (toggle overlays, hover), but mean a second drawing implementation, a new dependency and a risk of choppy playback.
  - Rendering frames on demand with a slider. Too slow.
- **Why:**
  - One drawing code path, so app, README GIF and stills always match.
  - Smooth 25 fps playback with standard video controls (pause, scrub).
  - No new dependency.
  - Free hosting needs nothing but the files in the repo.
- **Evidence:**
  - The videos are H.264 yuv420p, 900×684, 576 frames for the 23 s Musiala clip, which browsers play.
  - The local server reports healthy.
  - Streamlit's AppTest renders every clip with its explanation and a passing check.
  - A fresh clone with no `.env` and no raw data passes all 69 tests.
- **Limitations:**
  - Overlays cannot be toggled in the app.
  - The videos add ~18 MB to the repo, and re-rendering adds more to git history.
  - Streamlit resolved to 1.59.1 rather than the newest release because of dependency constraints. It works, but this is noted.

## D19. Phase 7 detector: stabilised background subtraction, not a pretrained deep detector
*2026-10-11 · `scripts/spike_phase7_detect.py`*

- **Data:** SoccerTrack top-view, from [kaggle.com/datasets/atomscott/soccertrack](https://www.kaggle.com/datasets/atomscott/soccertrack) (LGPL-3.0). DJI drone, 4K, 29.97 fps, 30 s segments. Ground truth is a 39×39 px box per player per frame (semi-automatic, from GNSS vests), and pitch keypoints map pixels to metres. We used one segment (`D_20220220_1_0030_0060`), kept in git-ignored `data/raw/soccertrack/`.
- **Decision:** Detect players by:
  1. aligning every frame to a reference frame (ECC, rotation + shift)
  2. taking the per-pixel median of 60 aligned frames as an empty pitch
  3. keeping player-sized blobs that differ from it inside the pitch (+2 m)

  Positions go to metres through the keypoint homography.
- **Alternatives:** RF-DETR (pretrained on COCO, Apache 2.0) on overlapping 640 px tiles; fine-tuning a detector on SoccerTrack boxes (needs a GPU).
- **Evidence** (10 frames, 220 player instances, match radius 1.5 m):

  | | Recall | Precision | Position error | Speed |
  |---|---|---|---|---|
  | Background subtraction, no stabilisation | 98.2% | 15.9% | 0.25 m | 0.03 s/frame |
  | **Background subtraction, stabilised** | **98.6–99.1%** | **74.6–75.4%** | **0.23 m** | **0.03 s/frame** |
  | RF-DETR base, tiled | 43.2% | 76.0% | 0.27 m | 3.0 s/frame |

  - **The drone drifts:** up to ~50 px and 1.5° within 30 s, about 2 m on the pitch. Without stabilisation, pitch lines shift against the background and produce ~114 false detections per frame. Stabilisation removes almost all of them.
  - **Remaining "false" detections are mostly real people:** the referee and staff near the touchlines, who are not in the 22-player ground truth.
  - **RF-DETR misses most players:** COCO people are mostly seen from the side, not straight down.
- **Why:** The classical method is 100× faster, needs no model download or GPU, and is more accurate in this setting. It is also easy to explain.
- **Limitations:**
  - It depends on a hovering camera, a mostly static scene and a long enough clip for the median. A player standing still for most of the clip could fade into the background.
  - Players in contact merge into one blob.
  - It does not detect the ball yet.
  - The keypoint calibration matches frame 0 to within ~0.5 m near the corners.
  - GNSS and video only agree to ~3 m (median, best offset ~1.2 s) in this segment, with player IDs numbered differently. So we evaluate against the annotation boxes, not GNSS.

## D20. Automatic pitch calibration from the painted lines
*2026-10-11*

- **Decision:** For raw footage with no hand-marked points, `video/pitch_lines.py` calibrates from the empty-pitch (median) image:
  1. green field mask
  2. white line pixels
  3. long Hough segments in two directions
  4. the outermost lines that run at least 60% as far as the longest line in their direction (touchlines and goal lines)
  5. four corner intersections → homography to a 105 × 68 m pitch
- **Alternatives:** Hand-mark four corners per video (reliable, but it is a manual step); a trained pitch-keypoint model (needs labelled data and a GPU).
- **Evidence:**
  - Against SoccerTrack's 65 hand-made keypoints: mean 0.45 m, median 0.36 m.
  - End to end on 3 segments, using **no dataset calibration at all**: player recall 98.6–99.1% and mean position error **0.43–0.55 m** (p90 ≤ 0.80 m), compared with 0.11–0.23 m using the dataset's calibration. Ground truth itself comes from the dataset calibration, so part of the gap is its error.
  - The first version picked the painted text "IMAGINE THE FUTURE" below the touchline as the boundary (1.78 m mean error). The 60% span rule fixed it (unit-tested on a synthetic pitch with text).
- **Limitations:**
  - It needs the whole outline visible, a near top-down view and a known pitch size.
  - It cannot tell the two ends apart: the result is correct up to mirror symmetry. On one of three segments the best mirror differed, so a clip must set its attacking direction.
  - It has only been tested on one ground.

## D21. Tracking, teams and ball from top-view video
*2026-10-11 · `scripts/video_to_tracks.py`, 3 SoccerTrack segments × 900 frames*

- **Decision:**
  - **Tracking:** our own point tracker in pitch metres. It predicts each track forward from its velocity, and matches tracks to detections with the Hungarian algorithm on distance + 2 × shirt-colour difference. Offline stitching then joins tracks that break and restart nearby in a similar colour.
  - **Teams:** 3-cluster k-means on each track's average shirt colour; the two biggest clusters are the teams. Goalkeepers are long tracks whose colour is far from their cluster. A keeper joins the team whose outfield player stands deepest towards that goal in most frames (offside logic).
  - **Ball:** small white blobs, followed forwards and backwards in time with a 35 m/s speed limit. Frames where the passes disagree, or the ball is hidden, are left empty.
- **Alternatives:**
  - supervision's ByteTrack. It is deprecated in supervision 0.28+ and was run as a baseline.
  - Adding the `trackers` package.
  - Deep re-identification models (need a GPU and training data).
- **Evidence:**

  | Segment | Coverage | Identity purity (ours / ByteTrack) | ID switches (ours / ByteTrack) | Team correct | Ball correct, all frames |
  |---|---|---|---|---|---|
  | 0:30–1:00 | 98.5% | 95.2% / 88.5% | 26 / 26 | 94.4% | 70.0% |
  | 5:00–5:30 | 99.6% | 99.6% / 99.5% | 18 / 7 | 99.6% | 40.7% |
  | 10:00–10:30 | 98.3% | 96.3% / 96.1% | 28 / 15 | 98.9% | 69.9% |

  - **Shirt colour in the cost:** cut ID switches from 33 to 27 and raised purity from 88% to 92% on segment 1. 74% of switches happened with another player within 2 m. Stitching then raised purity to 95% and cut tracks from 183 to 110.
  - **Team errors:** before the keeper rule, 91% of team errors came from the two goalkeepers (yellow shirts). A simpler "team leaning towards that goal" rule fixed segment 1 but failed when a team pressed high. The offside rule averages 97.6% across segments. We stopped after two attempts.
  - **Ball:** following both ways reached 70% against a ceiling of 71% (frames where any blob is near the ball). When no blob is near the ball, a player is within 1 m of it 90% of the time: it is at someone's feet, merged with their blob. Positions we do give are correct (within 1 m) 91–99% of the time.
- **Limitations:**
  - ByteTrack has fewer ID switches on two segments; ours keeps a player's identity longer (purity).
  - Same-team players crossing can still swap.
  - The keeper's team is wrong for one keeper in segment 1. Options: combine several cues, let the user confirm in the app, or give shirt colours as input.
  - The ball is unknown in 30–60% of frames, mostly when it is at a player's feet. Segment 2 is the weakest (41%).
  - All three segments are from one match on one ground.

## D22. End to end: drone video → clip → overlays → AI coach
*2026-10-11 · `scripts/video_to_clip.py`, clip `drone-0600-0630`*

- **Decision:** `video/export.py` turns our own tracks, teams and ball into the same clip format as the DFL clips (players/ball parquet + meta), so the overlays, facts summary, AI coach and app work unchanged. Rules:
  - Keep only the two teams' tracks of at least 1 s, at most 11 per team per frame.
  - Drop assistant referees (tracks that never come 2 m inside a touchline) *after* team assignment.
  - Name players "Player A3" and teams by shirt shade ("lighter" / "darker"). Colour names were wrong under the green-tinted light (blue measured as green).
  - The lighter team is "home" (drawn white) and attacks left to right.
  - When the ball is not visible it is hidden with the label "Ball not visible" (not "out of play").
- **Evidence:**
  - Segment 10:00–10:30 builds with no validation problems (25 speed warnings from identity jumps).
  - One keeper per team, each in its own half.
  - The ball is visible in 71% of frames.
  - The coach explanation passes grounding (29 items) and format checks after one live repair (253 → 223 words).
  - The app smoke test renders it.
  - We chose this segment for the demo because its team labels are best (98.9%). The scores of all three segments are in D21.
- **Bugs found on the way, each fixed:**
  - Segment names are seconds ("0600" = 10:00), not mm:ss.
  - Removing officials before team assignment dropped team accuracy from 99.6% to 86.0%.
  - The keeper test assumed an elite keeper (> 35 m); the amateur keeper averages 32 m.
- **Limitations:**
  - No player names or official formations from video.
  - A keeper who barely moves fades into the median background and is detected in fragments, as seen in segment 0:30–1:00.
  - Segment 0:30–1:00 still assigns one keeper to the wrong team.
  - Tested on one ground and one match. Goals are not detected from video, so "goals" is empty for drone clips.

## D23. Correction: the dataset's calibration had leaked into detection
*2026-10-11*

- **What was wrong:** Prompted by Mohit's question ("did the drone clip really use no given coordinates?"), we re-checked the code. The *pitch area* used to discard detections off the pitch (`pitch_mask`) was built from SoccerTrack's hand-marked keypoints, not from our automatic calibration. That held in both the detection spike and the full pipeline. Positions, teams and ball were already computed from the video, but D20–D22's claim of "no dataset calibration at all" was not fully true.
- **Fix:** The detector first builds the empty-pitch image with no mask, then calibrates automatically, then masks with *that* calibration. Dataset keypoints and boxes are now used only to score results. A unit test builds a clip from video-derived columns alone.
- **Re-measured** (D19–D22 figures replaced where they changed):

  | Segment | Detection recall / precision / auto-calibration error | Purity | Team correct | Ball correct |
  |---|---|---|---|---|
  | 0:30–1:00 | 98.6% / 75.3% / 0.55 m (unchanged) | 95.1% (was 95.2%) | 94.4% | 70.0% |
  | 5:00–5:30 | 99.1% / 84.8% / 0.43 m (unchanged) | 99.6% | 99.6% | 40.7% |
  | 10:00–10:30 | 99.1% / 78.7% / 0.52 m (unchanged) | 96.1% (was 96.3%) | 97.8% (was 98.9%) | **61.0% (was 69.9%)** |

  The demo clip `drone-0600-0630` was rebuilt: the ball is visible in 63% of frames (was 71%). The explanation was regenerated and passes grounding (34 items) after one length repair.
- **Lesson:** "Uses no ground truth" must be checked line by line, and guarded by a test, not asserted. The leak mattered most for the ball, whose candidates near the pitch edge depend on the mask.

## D24. Calibration picks the outline with a real pitch's proportions
*2026-10-12 · `evals/video/README.md`*

- **Problem found by testing more of the match:** On 3 of 12 new segments (22:30, 25:00, 27:30), only 2.7–4.8% of players landed in the right place. The cause was "take the outermost long lines": it chose a row of white practice goals beyond the left goal line, which runs the full height of the image. Before finding this, we briefly suspected the dataset's own calibration. A frame overlay proved the dataset right and us wrong.
- **Decision:** Collect all long lines in each direction, and choose the rectangle whose length/width ratio is closest to 105/68 (within 5%; among equals, the largest). A synthetic test now includes a row of goals beyond the pitch.
- **Evidence:**
  - Those 3 segments went from 2.7% / 4.6% / 4.8% to **99.5% / 98.1% / 98.1%** of players found, with errors of 0.59 / 0.44 / 0.37 m.
  - Segments that were already correct are unchanged.
  - Across all 13 segments: median 98.4% found, median error 0.51 m, worst 92.0% and 0.80 m.
- **Limitations:**
  - It assumes the standard 105 × 68 m ratio.
  - It is still one ground.
  - Ball accuracy on 20:00 is unexplained (13.7%) and not yet investigated.
- **Process note:** The low-heat run (`taskpolicy -b`, efficiency cores) took ~18 min per segment against ~4.5 min normally. Runs now carry a thermal watcher that pauses the job if macOS reports a thermal or performance warning. None was reported.

## D25. Full-resolution ball detector: better on average, not yet adopted
*2026-10-12 · `scripts/spike_phase7_ball.py`*

- **Diagnosis:** Ball misses came from detection, not the follower. Whenever a candidate existed, the follower found the ball, except in 0–9% of frames. The half-resolution player detector closes gaps and glues a ball at someone's feet onto the player.
- **Change:** `BallDetector` works at full resolution with no closing. It keeps small, round, white blobs off the painted lines, against a full-resolution median background computed in strips (a plain median would need ~12 GB). `mark_candidates` demotes candidates within 0.3 m of a player-blob centre: they cannot start a track and carry an 8 m penalty. The data showed white-shirt fragments sit a median 0.29 m from a player centre (roundness 0.65), while the ball sits 2.2 m away (roundness 0.88). Dropping them outright lost the ball at players' feet: 61% → 42% on 5:00.
- **Evidence:**
  - Ball-candidate ceiling rose from 41–75% to 79–97% of frames.
  - On the 3 tuning segments, ball correct went 70.0 / 40.7 / 61.0% → 82.1 / 63.1 / 65.0%.
  - On 3 **held-out** segments it went 63.7 / 60.1 / 67.4% → **97.3 / 77.2 / 38.0%**: better on 5 of 6 segments and +10 points on average, but much worse on 12:30, where the follower locks onto wrong blobs.
- **Decision:** It is not yet used in the app's drone clip. The spike scores candidates in dataset metres, so adopting it also needs automatic-calibration coordinates. We stopped after two follower attempts, as the project rules require.
- **Next:** A tracklet-based follower: link candidates into short tracks, drop ones that never move or move with a player, then pick the most ball-like path.

## D26. One pipeline for any drone clip, with a quality report that can refuse
*2026-10-12 · `src/tactics/video/pipeline.py`, `scripts/process_video.py`*

- **Decision:** `process_video(path, clip_id, title, length_m, width_m, progress, start_s)` turns any top-view clip into a standard clip plus a `QualityReport`.
  - Everything comes from the file itself (frame rate, length). Background frames are sampled across the actual clip.
  - Tracker time limits are set in seconds and converted with the clip's frame rate.
  - The SoccerTrack names, paths and the hardcoded 29.97 fps / 900 frames now live only in the evaluation script. Ground-truth scoring moved to `video/scoring.py`.
  - `scripts/video_to_tracks.py` evaluates the exact production path; `video_to_clip.py` was retired.
- **Quality gates** (blocking unless noted):
  - clip at least 10 s long
  - pitch outline found, and its ratio within 5% of 105:68
  - calibrations from the first and second half of the clip agree within 2 m
  - camera drift at most 200 px, with at most 5% unaligned frames
  - median player blobs per frame between 14 and 30
  - non-blocking: ball visible in at least 30% of frames, and one keeper per team
- **Found and fixed while building it:**
  1. **Teams split when there is no third colour.** With no referee or staff in view, the 3-colour k-means split one team in two. This was caught by a synthetic clip, where 8 of 11 blue players were kept. A third cluster within 15 Lab units of a team is now merged back. On real segment 0:30 this also raised team accuracy from 94.4% to 99.0%.
  2. **A touchline cut out of the field mask.** On segment 22:30 the top touchline sat outside the green mask (the strip beyond it was not green enough), and the new pipeline rejected the clip. The mask is now grown by ~0.8% of the image size before taking line pixels.
  3. **Speed.** Blob colours are now computed with `np.bincount`, and players and ball candidates come from one foreground pass. This takes ~2 min per 30 s 4K clip on an M2, down from ~4.5 min, with colours identical to the old loop.
- **Evidence (`evals/video/README.md`):**
  - All 13 segments pass the quality report.
  - Median: 98.4% of players found, 0.49 m error, 97.4% identity purity, 98.5% correct teams, ball 61.7%.
  - Synthetic tests: an end-to-end clip passes, while a 4 s clip and a clip with a third of the pitch cut off are rejected.
- **Honest regressions:**
  - Identity purity median fell from 98.5% to 97.4%; the worst segment (15:00) fell from 94.9% to 90.2%. Different background frames and the grown mask change detections slightly, and tracking is sensitive to that. Not yet investigated.
  - It is still one ground and one match. The gates catch obvious failures, but only for the conditions we have seen.

## D27. Robustness suite: edit real clips the ways they differ, fix what breaks
*2026-10-15 · `scripts/robustness.py`, `src/tactics/video/pitch_lines.py`, `src/tactics/video/pipeline.py`, `evals/video/robustness.md`*

- **Decision:** before claiming "any drone clip", stress-test the production pipeline on edited copies of segment 10:00. The ground truth is moved the same way as each copy.
  - **Edits:** rotate 90° and 180°, two crops, 30% darker, 1080p, 720p, 20 s, 25 fps.
  - **Pass rule:** keep working (players found ≥ 90%) or refuse the clip. Quietly wrong output fails.
- **Alternatives:**
  - Transform frames inside the pipeline. This is cheaper, but it would need a test-only hook in production code and would skip real decoding.
  - Wait for clips from other grounds. These are still needed, but give no ground truth.
- **Found and fixed** (the first run passed 4 of 7 edits):
  1. **Line grouping.** One touchline's pieces were binned along the other touchline's direction, 0.8° off, and dropped as too short. Pieces are now grouped when they lie on one straight line. This caused refused 1080p, cropped and 25 fps copies. A test reproduces the failure: the old code lost the line at 8 of 12 heights tried.
  2. **White paint relative to the grass.** Paint is now brighter than 1.17 × this pitch's median grass, not a fixed V ≥ 170 (the same value on the original footage). Comparing with the *nearby* grass instead was tried and rejected: it added shadow edges and doubled the corner error (0.71 → 1.21 m on the 13 backgrounds).
  3. **Resolution-independent detection.** Blob sizes are in pixels, tuned at ~14 px per metre. Each clip is now processed at the scale that gives about that, measured from the calibrated outline. 4K keeps its old scale of 0.5; 1080p uses 1.0.
  4. **Refuse low resolution.** At 720p of a full pitch (9.3 px/m), only 76% of players were found, so clips below 10 px/m are now refused.
  5. **Outline ratio** is measured from the mean of opposite sides, so it no longer depends on which corner comes first.
- **Evidence:**
  - All 10 edits pass. Every accepted edit stays within 0.3 points of the baseline for players found and within 0.02 m for position error (`evals/video/robustness.md`).
  - On saved backgrounds of all 13 segments, the new calibration moves the corners by at most 0.14 m. It stays identical at 30% and 50% brightness.
  - 97 tests pass. The two new calibration tests fail on the old code. The synthetic clips are now drawn at a realistic 14 px/m, and a new test checks that a low-resolution clip is refused.
- **Limits:**
  - One segment of one ground. Other grounds, partial shadows and tilted cameras are untested.
  - On segment 10:00 the position error went from 0.49 to 0.54 m with the new calibration. The 13-segment table predates D27 and needs a re-run.
  - All runs used low-power mode (efficiency cores), so they took ~8 min per clip instead of ~2.

## D28. Broadcast clips: calibrate the camera in every frame, draw the analysis on the footage
*2026-10-15 · `src/tactics/broadcast/`, `src/tactics/viz/overlay.py`, `tools/pnlcalib/`, `evals/broadcast/`*

- **Why:** most football video online is TV footage, where the camera pans and zooms. The drone pipeline refuses it: no fixed view, no whole outline.
- **Decision:**
  - Calibrate **each keyframe**, 5 per second, with **PnLCalib**, a pretrained keypoint-and-line model.
  - Find people and the ball with **RF-DETR**. A player's feet are on the ground, so the homography places them on the pitch.
  - Then reuse the drone pipeline unchanged in pitch metres: tracker, stitching, teams, ball follower and export. Positions in metres do not depend on where the camera points.
  - Interpolate to 25 fps, and keep one homography per frame so the analysis can be **drawn on the footage itself**: team shapes on the grass, rings at players' feet, the ball, and a corner map showing the camera's view.
  - `process_video.py --mode auto` tries the drone checks first and falls back to the broadcast path.
- **Alternatives:**
  - Roboflow's 32-keypoint YOLOv8-pose model: Ultralytics is AGPL and the weights licence is unclear (same reasoning as D19).
  - The SoccerNet game-state baseline: GPL-3.0, and far too heavy for the laptop (YOLO, ReID and OCR).
  - Measuring shapes in image pixels: perspective makes far players look closer together, so all numbers would be wrong.
- **Licence boundary:**
  - PnLCalib is GPL-2.0. `tools/pnlcalib/setup.sh` installs it outside the repository, in git-ignored `data/tools/` with its own venv.
  - Only `tools/pnlcalib/run_pnlcalib.py` imports it, and that one file is GPL-2.0-or-later.
  - Our MIT code runs it as a subprocess and reads JSON.
- **Our own check of every calibration (line agreement):** draw the calibrated pitch lines into the frame and measure the share that lands on white paint. Good fits score 0.7–0.9, wrong ones below 0.1. Keyframes under 0.5 are dropped, and a clip with under 70% good keyframes is refused.
- **Spike findings:**
  - PnLCalib fails on the high "tactical" camera that looks along the pitch (two World Cup clips: 0 of 11 keyframes; lowering the thresholds gave 7 calibrations, all wrong).
  - It works on the standard side-on camera: Euro 2020 clip, 200/200 keyframes, median agreement 0.84.
  - We support the side-on camera and refuse the rest.
- **Found while building:**
  1. **Variable frame rate.** A screen recording labelled 60 fps averaged 36. Frames are now resampled to an exact rate with ffmpeg, and other aspect ratios are padded to 16:9, not stretched.
  2. **ID chains mixed teams.** At 5 fps one "track" was the referee, then a white player, then a dark player; its average colour made all three "white". A player cannot change team, so tracks are now cut where the shirt colour changes (`broadcast/teams.py`). Colour disagreement fell from 7.7% to 3.3%. This is self-consistency, not accuracy.
  3. **Facts the camera cannot support.** The first coach text said the defence was "bypassed" because the deepest defenders were off screen. For partial views:
     - the facts keep only width and area of visible players, and only when at least 7 of a team's outfield players are in view;
     - back line, depth, players behind the ball and the formation are left out;
     - prompt v4 adds a rule: say the camera shows part of the pitch, and draw no conclusions outside it.

     Clips with full tracking data get exactly the same facts as before (checked on all 5 committed clips).
- **Limits:**
  - **No ground-truth evaluation yet.** SoccerNet-GSR has true positions for broadcast clips; download and scoring are the next step (disk permitting).
  - Only the side-on camera works.
  - Only players in view are tracked.
  - The referee is drawn as the white team on the test clip: their light-blue shirt is too close to white in our colour measure.
  - A ball in the air is placed wrongly, because the homography is for the ground.
  - The ball is kept in 39% of frames.
  - One test clip so far.

## D29. Broadcast tracking measured on hand labels: players over time, a full-resolution ball tracker, a confirmed ball
*2026-10-16 · `scripts/label_frames.py`, `scripts/evaluate_broadcast.py`, `src/tactics/broadcast/{ball,detect,teams,pipeline}.py`, `src/tactics/geometry/pressure.py`, `src/tactics/viz/overlay.py`, `src/tactics/ai/summary.py`*

- **Why:** Mohit's review of the first broadcast video:
  - players were missed;
  - the ball was "badly tracked";
  - hull lines cluttered the picture;
  - later, staff got rings, team players got grey rings, and the ball marker wandered.
- **Ground truth first.**
  - A click tool collects labels: the ball once per second (40 frames, 38 with the ball visible) and every person's feet on 5 frames (103 people), about 10 minutes of Mohit's time.
  - `evaluate_broadcast.py` scores what the video shows.
  - The labels stay local (copyrighted footage); the scores are in `evals/broadcast/local-euro-copenhagen.csv`.
- **Detector spike on the labels:**

  | Setup | People found | Ball found |
  |---|---|---|
  | RF-DETR Base, whole frame | 87% | 32% |
  | 2 tiles | 88% | – |
  | 6 tiles (8× the cost) | 89% | 58% |
  | RF-DETR Large in a 704 px window around the ball | – | 63% |

  So:
  - **People:** Base on the whole frame every 2nd frame (12.5 fps). The missing players are hidden behind others, so **tracking** fills gaps up to 0.5 s instead of a bigger model.
  - **Ball:** a Kalman filter predicts the ball and Large searches a full-resolution window there (tiles every 5th frame when lost); forward and backward linking follows.
- **Found and fixed while measuring:**
  1. **Painted marks.** The penalty and centre spots score like a ball (0.4–0.56) and captured the tracker, whose window then followed them. Candidates on known spots, or in a pitch cell seen in ≥ 2 s of frames, are dropped (ball within 15 px 10.5% → 50%).
  2. **Staff.** The 3 m on-pitch margin let managers in. It is now 1 m, and tracks whose median position is outside the lines are dropped (ring precision 84% → 90%).
  3. **Grey team players.** Short colour pieces had been labelled "other". Grey is now only for a shirt unlike both teams, and two rings within 0.8 m merge.
  4. **A wandering ball.** Showing every linked ball put the marker on the wrong object 25–43% of the time. The ball is now shown, and analysed, **only when confirmed**: the forward and backward passes agree, no jump faster than 40 m/s, gaps ≤ 0.2 s filled.
     - Strict confirmation: right 8/8 when shown.
     - Looser rule (a nearby detection also confirms): right 18/24 when shown.

     Mohit chose strict: better no ball than a wrong ball.
  5. **Direction of play.** Without a goalkeeper in view it is unknown which goal a team attacks. The first coach text called spells "backwards" on a guess. Thirds and progress are now left out and the facts say the direction is unknown.
- **Analysis for a partial view.** TV cameras follow the ball, so the facts describe the play around it, from confirmed-ball moments only (`geometry/pressure.py`, prompt v5):
  - possession share and how the ball moved between team-mates and teams;
  - pressure on the ball (nearest opponent);
  - players of each team within 15 m;
  - possession spells.
- **Results on Mohit's labels:**

  | | Baseline (D28) | Now |
  |---|---|---|
  | People found | 85.4% | 90.3% |
  | Ring precision | 91.7% | 90.3% |
  | Ball shown | 52% of frames | 20% |
  | Ball right when shown | – | 100% |
  | False ball | 50% | 0% |

- **Limits:**
  - One clip with 38 ball labels and 103 people labels; the settings were tuned on it, so the numbers are optimistic until other clips are labelled.
  - The ball is confirmed in only ~26% of frames, so the coach analyses ~11 s of a 40 s clip.
  - The referee can still be coloured as a team.
  - A specialised football-ball detector would be the real fix for the ball, but it needs training (heavy on a laptop).

## D30. Correct the ground truth per segment: the drone drifts, the dataset's calibration does not
*2026-10-18 · `scripts/truth_calibration.py`, `scripts/video_to_tracks.py`, `evals/video/`*

- **What we saw:**
  - The first truly unseen segment (18:30) scored 68.5% of players found and a 0.82 m error, against a tuned median of 98.4% and 0.49 m.
  - Players were tracked fine in pixels (coverage 99%, purity 97%). Only positions in metres disagreed.
  - Drawing both calibrations on that segment settled it: ours sat on the painted lines; the dataset's penalty boxes were visibly shifted.
- **Cause:**
  - SoccerTrack gives one set of pitch keypoints for the whole match, but the hovering drone slowly moves and turns over 30 minutes.
  - The share of the dataset's pitch lines landing on paint varies from 37% to 88% across segments. The ground-truth boxes are turned into metres with it, so the "truth" itself was off by up to ~2 m.
  - Within a segment the drone barely moves (5 px), so this is drift between segments, not shake.
- **Decision:**
  - Move the dataset's keypoints to each segment by image registration: ORB features and a RANSAC homography from the best-fitting segment (0:30, 88% on paint) to each other segment, over the whole image.
  - This does not use our pitch-line calibration, so we are not grading ourselves with our own map.
  - The moved calibrations land on the paint 87–89% of the time in every segment. That is the dataset's own precision; even at the reference it is 88%.
  - Scoring uses them by default. `--dataset-truth` and `segments_dataset_truth.csv` keep the original for comparison.
- **Alternatives rejected:**
  - Score with our own calibration: circular.
  - Keep the single calibration: it punishes the pipeline for the drone's drift, and the error grows with time.
- **Results (all 15 segments, after-D27 code):**
  - **13 tuned segments, median:** 98.6% found, 0.35 m error (0.49 m with the old truth), purity 97.4%, team 98.2%, ball 63%.
  - **2 unseen segments:**
    - 18:30: 99.1% found, 0.44 m;
    - 0:00: 96.3% found, 0.55 m, team 91.9%.
  - The unseen segment's ground-truth file was moved out of the data folder while it was processed.
  - Runs are now saved, so re-scoring needs no video processing (`--rescore`).
- **Limits:**
  - Still one match and one ground; the unseen segments differ only in time.
  - The corrected truth inherits the dataset's own keypoint precision (88% on paint).
  - The "on paint" check favours our calibration, because ours is fitted to the same paint. That is why it is not used as the truth.
- **Addendum: 5 more unseen segments** (6:00, 11:00, 16:00, 21:00, 26:00), processed before their ground truth was downloaded.
  - **The 6 accepted unseen segments, median:** 96.9% found, 0.44 m, purity 92.5%, team 92.5%, ball 54.5%. On the 13 tuned segments: 98.6%, 0.35 m, 97.4%, 98.2%, 63.4%. **That gap is the honest generalisation cost.**
  - **The quality report missed twice:**
    - 16:00 was accepted at 80.0% found.
    - 11:00 was refused (37 blobs per frame, limit 30), although it reached 96.7% found and 0.27 m.
  - Both are next to investigate.

## D31. Keep `main` focused on drone footage; the TV-broadcast experiment moves to a branch
*2026-10-18 · branch `broadcast-experiment`*

- **Decision:** remove the broadcast pipeline from `main` and keep it, complete, on the branch `broadcast-experiment`. That covers:
  - `src/tactics/broadcast/`, the on-video overlay;
  - the PnLCalib tool setup;
  - the hand-label tool and its evaluation script;
  - its tests;
  - the broadcast mode of `process_video.py`.

  The pitch-line model it shared moved to `video/pitch_lines.pitch_line_points`.
- **Why:**
  - The drone pipeline is the product, measured on 20 segments (D30).
  - The broadcast path works only on the main camera of professional stadiums. It confirms the ball in only ~20% of frames, and free footage to test it on does not exist.
  - Keeping it on `main` meant a GPL tool to install, ~1.4 GB of models, extra code to explain, and a weaker story.
- **Kept on `main`:**
  - the partial-view support in the facts and prompt (inactive for drone clips, whose facts are unchanged);
  - `geometry/pressure.py`;
  - D28–D29 and `evals/broadcast/`, as the record of what was tried and measured.
- **Alternative:** delete it outright. That would lose a measured experiment that is useful to show in interviews ("what we tried, how we measured it, why we stopped").

## D32. The backend product: coordinate data or drone video in, one analysis out, behind an HTTP API
*2026-10-18 · `src/tactics/data/upload.py`, `src/tactics/service.py`, `src/tactics/api.py`, `templates/`*

- **Decision:** two ways in, both ending in the same standard clip and the same geometry, facts and coach.
  1. **Coordinate data (the main way in):**
     - our long template (`time_s, team, player, x, y`, optional `jersey, position`), as CSV or Excel;
     - or a provider format through kloppy (Metrica, SkillCorner, Sportec/DFL), cut to a window of up to 120 s.
  2. **A top-view drone video (the side way in):** the Phase 7 pipeline, run as a background job.
- **Why tracking data is the main way in:**
  - No computer-vision error.
  - Instant, and light enough for a free server.
  - Most people with real tracking data are analysts and clubs.
  - The drone path shows the vision work, but needs footage few people have and minutes of processing on a laptop.
- **The quality report decides for uploads too** (`data/report.py`, moved out of the video module so the upload path needs no OpenCV). It refuses:
  - unreadable files or missing columns;
  - unknown team values;
  - wrong units (more than 2% of positions over 5 m outside the pitch);
  - fewer than 7 players per team;
  - clips outside 3–120 s or 5–60 fps.

  It warns about a missing ball and unmarked keepers.
- **Keepers when not marked:** the deepest regular player whose average position is in front of goal (within the penalty area's width). On Metrica data the plain "deepest player" picked a winger taking a corner.
- **API (FastAPI, uvicorn):**
  - Endpoints: clips, the per-clip payload, video, explanation, template downloads, tracking and provider uploads, and drone jobs with progress.
  - The payload is frames, players, ball and per-team hull and metrics, so the frontend can animate without the backend rendering video. It is gzipped to ~76 KB per clip at 12.5 fps.
  - Uploads go to git-ignored `data/user_clips/`.
- **Alternatives:**
  - Streamlit only: no real API for a React frontend.
  - Flask: FastAPI gives typed forms, file uploads and interactive docs for free.
  - Rendering every upload to MP4: slower, and the frontend would lose interactivity.
- **Evidence:**
  - The example file reproduces the bundled clip to 0.01 m.
  - Real Metrica (game 1) and SkillCorner open data pass the report and produce shapes and ball carriers.
  - 15 new tests:
    - 8 for upload;
    - 7 for the API, run in-process with a fake LLM and temporary storage, including a drone job on a synthetic video.
  - The API was also called over real HTTP.
- **Limits:**
  - Drone video runs only where the video dependencies are installed (locally).
  - Jobs live in one process's memory.
  - Provider uploads are tested through kloppy on open data, not through the API with real files.
  - A free deployment would serve the tracking-data path only.

## D33. Drone clips: never mirrored, and the original video plays under the 2D pitch
*2026-10-19 · `src/tactics/video/pitch_lines.py`, `src/tactics/video/export.py`, `src/tactics/service.py`, `src/tactics/api.py`, `web/src/app/Replay.tsx`, `scripts/fix_drone_orientation.py`, `scripts/add_source_video.py`*

- **Bug found:** while building the "original video under the replay" view, the dots did not sit on the players.
  - The pitch outline alone does not say which corner is which. The old corner assignment could give the **mirror image** of the real pitch, depending on which corner `pitch_corners` returned first.
  - The evaluation hid this: `scoring.py` scores against the truth under the best of the four pitch symmetries, so recall and error were unaffected.
  - For a user, a mirror swaps left and right: in the map, and in the facts the AI coach reads ("attacking third, left" became "right").
  - Measured on the four drone clips we had: three of them were mirrored.
- **Fix:**
  - **Calibration:** a camera looking down never sees the pitch mirrored. Pitch y points up (as every clip is drawn) while image rows go down, so the pitch corners and their image positions must wind opposite ways (shoelace sign). If they don't, the pitch's y is flipped. The 180° ambiguity (which end is which) stays; it is still resolved by where the keepers stand.
  - **Test:** a drawn pitch, as is and flipped or turned, never calibrates to a mirror image.
  - **Existing clips:** `scripts/fix_drone_orientation.py` places a clip's positions on a few video frames in each of the four symmetries and keeps the one that lands on the moving players. The right one scores 0.97–1.0, the others ~0.2. Mirrored clips were reflected, their facts rebuilt, and the two bundled drone explanations regenerated from the corrected facts (both still pass the grounding check).
- **Original video beside the replay:**
  - **Kept, not deleted:** a drone upload now keeps its video next to the clip, re-encoded for browsers with ffmpeg (H.264, at most 1920 px wide, no sound, ~3.5 MB for 30 s), served at `/api/clips/{id}/source` with range requests so it can be seeked.
  - **Bundled clips:** `scripts/add_source_video.py` attaches the video to the bundled clips (SoccerTrack, LGPL-3.0).
  - **One clock:** in the replay, the video sits under the pitch. While it plays, the video is the clock and the pitch follows it, so the two cannot drift (measured gap ≤ 0.06 s); seeks, speed and the coach's clickable clocks move both.
  - **Same orientation:** `meta.video_rotation` records how the video shows the pitch, so the map can be turned to match it.
- **Alternatives:**
  - Burn the dots into the video: no interactivity, and a second render per upload.
  - Sync two independent clocks: drifts and stutters when the video buffers.
  - Keep the original upload as is: 4K files of hundreds of MB, and not every codec plays in a browser.
- **Limits:**
  - Without ffmpeg the clip still works, just without the video.
  - A video turned 90° (portrait) keeps the usual landscape map, with a note.

## D34. Evaluating the AI coach: four layers, from free automatic checks to human review
*2026-10-20 · `src/tactics/ai/evaluate.py`, `scripts/evaluate_explanations.py`, `evals/llm/`*

- **Problem:** grounding only proves each number exists *somewhere* in the facts. A number can still be given to the wrong team, read the wrong way round ("dropped from 42 to 72"), or the answer can skip the goal entirely.
- **Decision:** four layers, cheapest first.
  1. **Grounding** (unchanged): every number, clock and formation is in the facts. It runs on every answer, and a failure triggers one rewrite.
  2. **Claims, coverage, invented events** (new, pure Python, no LLM):
     - each "from X to Y" is checked against that team's own changes, in order, and against the direction of the wording;
     - key facts must be said (goal and scorer, shapes, each team's biggest change);
     - event words (passes, shots...) are flagged in the facts section.
  3. **Trap tests** (new, 5 LLM calls, then cached): one fact of a real clip is changed, and the coach must follow it: no goal, too little play, unknown shape, partial camera, mirrored numbers.
  4. **Human review**: the checklist on each sheet, for meaning that is not a number.
- **Results:**
  - 6/6 grounded; 24/24 claims right; key-fact coverage 96%.
  - 5/5 traps passed.
  - Reading the traps by hand found an unsupported zone word ("final third" with an empty timeline): a known limit of layers 1–3.
- **Alternatives:**
  - An LLM judge (a second model scoring faithfulness): useful as a signal, but it can be wrong in the same ways and costs free-tier calls on every run. Kept as a possible fifth layer.
  - Exact-match tests: impossible for free text.
- **Limits:**
  - The claims check reads "from X to Y" sentences only.
  - Coverage is a quality signal, not a failure: the 220-word limit forces choices.

## D35. The calibration-stability check asks whether the same outline holds, not what each half's best outline is
*2026-10-20 · `src/tactics/video/pipeline.py`, `src/tactics/video/pitch_lines.py`*

- **Found by the first video from another match** (the NASK top-view dataset, Poland, CC BY 4.0, Zenodo 14867795): it was refused on "calibration stable over the clip".
  - The whole clip calibrated correctly.
  - The check searched each half of the sample frames for its own best pitch outline. In the first half, players near one goal hid part of the goal line (only 56% of it showed white), so the halfway line was taken as the pitch end, and the halves "disagreed" by 52 m.
  - The drone itself moved 58 px, well within limits.
- **Fix:**
  - Each half is checked against the outline found for the whole clip. Every side is searched a few pixels either way, and the move is measured in metres; the limit is unchanged at 2 m.
  - The offset is taken at the middle of the plateau of near-equal fits, so the widened line does not bias it.
  - A side counts as lost only when less than 40% of it lies on painted line.
- **Evidence:**
  - NASK preview: moved 0.04 m (was a false 52 m).
  - SoccerTrack 18:30 and 16:00: 0.04 and 0.03 m, as before.
  - New tests: a partly hidden side is still found, a 6 px camera shift is measured, an erased side is lost.
- **Honest note:** this fix was made after seeing this video, so its preview clip is no longer a blind test. The dataset's other videos (10 GB, not yet downloaded) can serve as one.
