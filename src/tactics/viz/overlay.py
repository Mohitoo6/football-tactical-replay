"""Draw the analysis on the broadcast video itself (augmented reality), plus a small 2D map in the corner.

Everything is computed in pitch metres (where distances are true) and then
projected into each frame with that frame's camera homography, so shapes sit
on the grass and follow the camera as it pans and zooms. Perspective is why we
cannot measure in pixels directly: far players look closer together than they are.
"""

from collections.abc import Iterable
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.broadcast.calibrate import H_COLUMNS, pitch_line_points, project, to_pitch
from tactics.geometry.shape import hull_vertices

TEAM_COLOURS = {"home": (40, 40, 230), "away": (230, 140, 30)}  # BGR: red, blue
BALL_COLOUR = (0, 230, 255)  # yellow
MARKER_RADIUS_M = 0.9
MAP_SCALE = 3.2  # px per metre in the corner map


def _ellipse_m(x: float, y: float, radius: float, points: int = 24) -> np.ndarray:
    angle = np.linspace(0, 2 * np.pi, points, endpoint=False)
    return np.column_stack([x + radius * np.cos(angle), y + radius * np.sin(angle)])


def _video_coords(frame_players: pd.DataFrame, rotated: bool) -> np.ndarray:
    """Clip positions back to the video's pitch coordinates (the clip may be turned 180 degrees)."""
    xy = frame_players[["x", "y"]].to_numpy(dtype=float)
    return -xy if rotated else xy


def draw_overlay(frame: np.ndarray, homography: np.ndarray, players: pd.DataFrame, ball: pd.Series | None,
                 rotated: bool, team_labels: dict[str, str]) -> np.ndarray:
    """One frame with team shapes, player markers, the ball, a legend and a corner map."""
    out = frame.copy()
    shapes = out.copy()
    for side, colour in TEAM_COLOURS.items():
        team = players[(players["team"] == side) & (players["position"] != "Goalkeeper")]
        xy = _video_coords(team, rotated)
        corners = hull_vertices(xy)
        if len(corners) >= 3:
            hull = project(corners, homography).astype(np.int32)
            cv2.fillPoly(shapes, [hull], colour)
            cv2.polylines(out, [hull], True, colour, 2, cv2.LINE_AA)
    cv2.addWeighted(shapes, 0.22, out, 0.78, 0, out)  # translucent team shapes on the grass

    for side, colour in TEAM_COLOURS.items():
        for x, y in _video_coords(players[players["team"] == side], rotated):
            ring = project(_ellipse_m(x, y, MARKER_RADIUS_M), homography).astype(np.int32)
            cv2.polylines(out, [ring], True, colour, 3, cv2.LINE_AA)
    if ball is not None:
        bx, by = (-ball["x"], -ball["y"]) if rotated else (ball["x"], ball["y"])
        ring = project(_ellipse_m(bx, by, 0.6), homography).astype(np.int32)
        cv2.polylines(out, [ring], True, BALL_COLOUR, 3, cv2.LINE_AA)

    _legend(out, team_labels)
    _corner_map(out, homography, players, ball, rotated)
    return out


def _legend(image: np.ndarray, team_labels: dict[str, str]) -> None:
    width = 70 + 15 * max(len(label) for label in team_labels.values())
    box = image[12:128, 12:12 + width]
    box[:] = (box * 0.35).astype(np.uint8)  # darken behind the text so it reads on any background
    y = 40
    for side, colour in TEAM_COLOURS.items():
        cv2.rectangle(image, (24, y - 18), (48, y + 4), colour, -1)
        cv2.putText(image, team_labels.get(side, side), (58, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        y += 34
    cv2.circle(image, (36, y - 7), 11, BALL_COLOUR, 3)
    cv2.putText(image, "Ball", (58, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)


def _corner_map(image: np.ndarray, homography: np.ndarray, players: pd.DataFrame, ball: pd.Series | None,
                rotated: bool) -> None:
    """A small top-down pitch in the bottom-right corner, with the camera's view shaded."""
    margin = 10
    w, h = int(105 * MAP_SCALE) + 2 * margin, int(68 * MAP_SCALE) + 2 * margin
    panel = np.full((h, w, 3), (50, 110, 50), np.uint8)
    to_map = lambda xy: ((np.asarray(xy) + [52.5, 34]) * MAP_SCALE + margin).astype(np.int32)
    flip = -1 if rotated else 1  # the map is drawn in the clip's orientation (home attacks left to right)

    height, width = image.shape[:2]
    corners = np.array([[0, height * 0.35], [width, height * 0.35], [width, height], [0, height]])
    view = to_pitch(corners, homography) * flip
    if np.isfinite(view).all() and np.abs(view).max() < 500:
        shaded = panel.copy()
        cv2.fillPoly(shaded, [to_map(np.clip(view, [-60, -40], [60, 40]))], (90, 160, 90))
        cv2.addWeighted(shaded, 0.6, panel, 0.4, 0, panel)
    for points in pitch_line_points(step_m=1.0):
        cv2.polylines(panel, [to_map(points)], False, (235, 235, 235), 1, cv2.LINE_AA)
    for side, colour in TEAM_COLOURS.items():
        for x, y in players.loc[players["team"] == side, ["x", "y"]].to_numpy():
            cv2.circle(panel, tuple(to_map([x, y]).tolist()), 4, colour, -1, cv2.LINE_AA)
    if ball is not None:
        cv2.circle(panel, tuple(to_map([ball["x"], ball["y"]]).tolist()), 3, BALL_COLOUR, -1, cv2.LINE_AA)
    image[height - h - 16:height - 16, width - w - 16:width - 16] = panel


def render_overlay(frames: Iterable[np.ndarray], clip, camera: pd.DataFrame, out_path: Path) -> int:
    """Write the overlay video (H.264, 25 fps); frames without a valid camera are copied unchanged. Returns frames written."""
    import subprocess

    rotated = bool(clip.meta.get("rotated", False))
    labels = {side: clip.meta["teams"][side]["name"] for side in ("home", "away")}
    players_by_frame = dict(tuple(clip.players.groupby("frame")))
    ball = clip.ball.set_index("frame")
    cams = camera.set_index("frame")
    writer = None
    written = 0
    for j, frame in enumerate(frames):
        if j not in cams.index or j not in ball.index:
            break
        if writer is None:
            height, width = frame.shape[:2]
            writer = subprocess.Popen(
                ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
                 "-r", str(clip.meta["frame_rate"]), "-i", "-", "-c:v", "h264_videotoolbox", "-b:v", "8M",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)], stdin=subprocess.PIPE)
        row = cams.loc[j]
        if bool(row["valid"]):
            h = row[H_COLUMNS].to_numpy(dtype=float).reshape(3, 3)
            visible_ball = ball.loc[j] if bool(ball.loc[j, "alive"]) else None
            frame = draw_overlay(frame, h, players_by_frame.get(j, clip.players.iloc[:0]), visible_ball, rotated, labels)
        writer.stdin.write(np.ascontiguousarray(frame).tobytes())
        written += 1
    if writer is not None:
        writer.stdin.close()
        writer.wait()
    return written
