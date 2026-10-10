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
- **Limitations:** Gemini's OpenAI compatibility is labelled beta, and unsupported parameters are silently ignored. If this causes problems, we swap `google-genai` in for that provider only.

## D5. Pre-generate and commit LLM explanations
*2026-10-10*

- **Decision:** `scripts/generate_explanations.py` writes `clips/<clip_id>.explanation.json`, keyed by a hash of (summary + prompt). The app shows the cached text and calls the LLM only on a cache miss, with backoff on HTTP 429 and then the fallback provider.
- **Alternatives:** Call the LLM live on every view.
- **Why:** Free tiers have strict rate limits. The deployed demo then works without an API key and never hits a rate limit in front of an interviewer.
- **Limitations:** Explanations are static until regenerated.

## D6. Automatic grounding check on LLM output
*2026-10-10*

- **Decision:** A checker extracts every number and player name from the LLM's explanation and verifies that each one appears in the structured input summary. Anything unmatched gets flagged. Outputs are saved to `evals/` with a manual checklist.
- **Alternatives:** Manual review only; an LLM-as-judge.
- **Why:** The LLM must never invent facts. A deterministic check is cheap, explainable and makes no extra API calls.
- **Limitations:** It catches invented numbers and names, but not wrong *qualitative* claims (e.g. "pressed high"). Those still need the manual checklist.

## D7. Animation: matplotlib for exports, Plotly in the app
*2026-10-10 · (pending spike for Plotly smoothness)*

- **Decision:** Use matplotlib + mplsoccer to render MP4/GIF files for the README and checks. Use Plotly animation frames (subsampled to ~10 fps) for interactive playback in Streamlit.
- **Alternatives:** Show pre-rendered videos in the app (smooth but not interactive); a custom HTML canvas component (smooth and interactive, but more code to maintain).
- **Why:** Both are mature libraries with little custom code.
- **Evidence (export half):** `scripts/render_clip.py` renders the 23 s Musiala clip to MP4 (576 frames, 25 fps, 23.04 s, 3.4 MB, ~28 s to render) and GIF (288 frames × 80 ms = 23.04 s, 2.2 MB). Both play in real time. The video frame at 17 s matches the Phase 2 still for the same moment. Stills and video share one drawing class (`FramePainter`), so they cannot drift apart.
- **Limitations:** Plotly can get choppy with many frames and shapes. If so, we revisit this choice. MP4 export needs ffmpeg installed (GIF does not).

## D8. Formation detection from average positions
*2026-10-10*

- **Decision:** Average each player's position over a time window, group players into lines by depth, and output a label such as `4-2-3-1`. Evaluate against the official DFL lineups.
- **Alternatives:** Template matching against known formations; clustering-based role assignment (more complex).
- **Why:** It is simple, explainable, and we can measure it against ground truth.
- **Limitations:** It is reliable only in settled phases of play, and unreliable in transitions and set pieces. Teams also change shape in and out of possession, which an official lineup does not capture.

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
