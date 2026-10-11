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
