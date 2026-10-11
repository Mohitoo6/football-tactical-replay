"""Phase 7 end to end: a top-view drone segment -> a clip the app, overlays and AI coach can use.

    uv run --group video python scripts/video_to_tracks.py 0030_0060   # once: detection + scores (cached)
    uv run --group video python scripts/video_to_clip.py 0030_0060
    uv run python scripts/render_clip.py --for-app drone-0030-0060
    uv run python scripts/generate_explanations.py drone-0030-0060

Uses only what was computed from the video (automatic calibration, our tracks,
teams and ball); the SoccerTrack ground truth is not used here.
"""

import sys
from pathlib import Path

import pandas as pd

from tactics.data.clips import match_clock, save_clip
from tactics.data.validate import find_problems, find_warnings, players_per_team
from tactics.video.ball import follow_ball_both_ways, is_white
from tactics.video.export import tracks_to_clip
from tactics.video.track import PointTracker, assign_teams, fix_goalkeepers, officials, stitch_tracks, track_points

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
FPS = 29.97


def main(segment: str) -> None:
    name = f"D_20220220_1_{segment}"
    detections = pd.read_parquet(PROCESSED / f"{name}_detections.parquet")
    small = pd.read_parquet(PROCESSED / f"{name}_small_blobs.parquet")

    tracks = stitch_tracks(track_points(detections, PointTracker(max_distance_m=1.5, max_missing_frames=30, colour_weight=2.0)))
    # Teams first: the officials help k-means form its third ("other") colour group.
    teams = fix_goalkeepers(tracks, assign_teams(tracks))
    tracks = tracks[~tracks["track_id"].isin(officials(tracks))]  # then drop the assistant referees from the clip
    ball = follow_ball_both_ways(small[is_white(small)], FPS)  # x_m, y_m: automatic calibration

    start_s, end_s = int(segment[:4]), int(segment[5:])  # SoccerTrack names segments in seconds: 0600_0630 = 600-630 s
    clip_id = f"drone-{segment.replace('_', '-')}"
    title = f"Drone clip {match_clock(1, start_s)}–{match_clock(1, end_s)} (SoccerTrack university match)"
    clip = tracks_to_clip(tracks, teams, ball, FPS, clip_id, title, start_s)
    folder = save_clip(clip, ROOT / "clips")
    print(f"{clip_id}: {len(clip.ball)} frames, ball visible in {clip.ball['alive'].mean():.0%}, "
          f"players per team {players_per_team(clip.players).to_dict('index')}, "
          f"teams {[t['name'] for t in clip.meta['teams'].values()]} -> {folder.relative_to(ROOT)}")
    for problem in find_problems(clip.players, clip.ball):
        print(f"  PROBLEM: {problem}")
    for warning in find_warnings(clip.players, FPS):
        print(f"  warning: {warning}")


if __name__ == "__main__":
    for seg in sys.argv[1:] or ["0030_0060"]:
        main(seg)
