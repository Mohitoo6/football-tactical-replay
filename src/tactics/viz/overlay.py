"""Draw the tracking on the broadcast video itself, plus a game-style 2D map at the bottom.

On the footage: a ring on the grass at every tracked person's feet (team colour; grey when
unsure or a referee) and a TV-style marker on the ball. Rings are drawn in pitch metres and
projected with each frame's camera homography, so they lie flat on the grass.

The minimap shows the same players on a top-down pitch in the clip's orientation, with short
trails, the ball, and the part of the pitch the camera sees.
"""

from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from tactics.broadcast.calibrate import H_COLUMNS, pitch_line_points, project, to_pitch

TEAM_COLOURS = {"home": (40, 40, 230), "away": (230, 140, 30), "other": (175, 175, 175)}  # BGR: red, blue, grey
BALL_COLOUR = (0, 230, 255)  # yellow
RING_RADIUS_M = 0.8
MAP_WIDTH_SHARE = 0.26  # the minimap is this share of the frame width
TRAIL_FRAMES = 25  # 1 s at 25 fps


def _ring_m(x: float, y: float, radius: float, points: int = 28) -> np.ndarray:
    angle = np.linspace(0, 2 * np.pi, points, endpoint=False)
    return np.column_stack([x + radius * np.cos(angle), y + radius * np.sin(angle)])


def draw_rings(image: np.ndarray, homography: np.ndarray, people: pd.DataFrame) -> None:
    """A ring at each person's feet (columns x_m, y_m in the video's pitch coordinates, side)."""
    for x, y, side in people[["x_m", "y_m", "side"]].itertuples(index=False):
        ring = project(_ring_m(x, y, RING_RADIUS_M), homography)
        if np.isfinite(ring).all():
            cv2.polylines(image, [ring.astype(np.int32)], True, TEAM_COLOURS.get(side, TEAM_COLOURS["other"]), 3, cv2.LINE_AA)


def draw_ball(image: np.ndarray, px: float, py: float) -> None:
    """TV-style ball marker: a ring around the ball and a triangle pointing down at it."""
    centre = (int(round(px)), int(round(py)))
    cv2.circle(image, centre, 13, BALL_COLOUR, 2, cv2.LINE_AA)
    tip = np.array([[centre[0], centre[1] - 20], [centre[0] - 9, centre[1] - 36], [centre[0] + 9, centre[1] - 36]], np.int32)
    cv2.fillPoly(image, [tip], BALL_COLOUR, cv2.LINE_AA)


def draw_legend(image: np.ndarray, labels: dict[str, str]) -> None:
    entries = [(TEAM_COLOURS["home"], labels["home"]), (TEAM_COLOURS["away"], labels["away"]),
               (TEAM_COLOURS["other"], "Referee / unsure")]
    width = 64 + 13 * max(len(text) for _, text in entries)
    box = image[14:14 + 30 * len(entries) + 12, 14:14 + width]
    box[:] = (box * 0.35).astype(np.uint8)
    for i, (colour, text) in enumerate(entries):
        y = 40 + 30 * i
        cv2.ellipse(image, (40, y - 6), (13, 7), 0, 0, 360, colour, 3, cv2.LINE_AA)
        cv2.putText(image, text, (64, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)


class Minimap:
    """A top-down pitch in the style of a football game's radar, drawn at the bottom centre of each frame."""

    def __init__(self, frame_width: int, frame_height: int):
        self.width = int(MAP_WIDTH_SHARE * frame_width)
        self.margin = 12
        self.scale = (self.width - 2 * self.margin) / 105.0
        self.height = int(68 * self.scale) + 2 * self.margin
        self.x0 = (frame_width - self.width) // 2
        self.y0 = frame_height - self.height - 14
        self.background = self._pitch()
        self.trails: dict[str, deque] = defaultdict(lambda: deque(maxlen=TRAIL_FRAMES))

    def to_map(self, xy) -> np.ndarray:
        return ((np.asarray(xy, float) + [52.5, 34]) * self.scale + self.margin).astype(np.int32)

    def _pitch(self) -> np.ndarray:
        image = np.zeros((self.height, self.width, 3), np.uint8)
        stripes = 12
        for i in range(stripes):  # mowing stripes, as in a game
            x1, x2 = int(i * self.width / stripes), int((i + 1) * self.width / stripes)
            image[:, x1:x2] = (46, 120, 52) if i % 2 else (52, 132, 58)
        for points in pitch_line_points(step_m=0.5):
            cv2.polylines(image, [self.to_map(points)], False, (235, 235, 235), 1, cv2.LINE_AA)
        cv2.rectangle(image, (0, 0), (self.width - 1, self.height - 1), (20, 20, 20), 2)
        return image

    def draw(self, image: np.ndarray, players: pd.DataFrame, ball: tuple[float, float] | None,
             view: np.ndarray | None) -> None:
        """players: the clip's players this frame (x, y in the clip's orientation, team, jersey)."""
        panel = self.background.copy()
        if view is not None:
            shaded = panel.copy()
            cv2.fillPoly(shaded, [self.to_map(np.clip(view, [-60, -40], [60, 40]))], (95, 170, 100))
            cv2.addWeighted(shaded, 0.45, panel, 0.55, 0, panel)
        seen = set()
        for row in players.itertuples(index=False):
            key = f"{row.team}-{row.jersey}"
            seen.add(key)
            self.trails[key].append(self.to_map([row.x, row.y]))
        for key in list(self.trails):
            if key not in seen:
                del self.trails[key]  # out of view: no trail jumping across the map when they return
        for key, trail in self.trails.items():
            colour = TEAM_COLOURS["home" if key.startswith("home") else "away"]
            points = list(trail)
            for i in range(1, len(points)):  # fade: older segments thinner and darker
                fade = i / len(points)
                tone = tuple(int(c * (0.35 + 0.65 * fade)) for c in colour)
                cv2.line(panel, tuple(points[i - 1].tolist()), tuple(points[i].tolist()), tone, 1 + int(2 * fade), cv2.LINE_AA)
        for row in players.itertuples(index=False):
            centre = tuple(self.to_map([row.x, row.y]).tolist())
            cv2.circle(panel, centre, 9, TEAM_COLOURS.get(row.team, TEAM_COLOURS["other"]), -1, cv2.LINE_AA)
            cv2.circle(panel, centre, 9, (255, 255, 255), 2, cv2.LINE_AA)
            label = str(int(row.jersey))
            size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)[0]
            cv2.putText(panel, label, (centre[0] - size[0] // 2, centre[1] + size[1] // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.38, (255, 255, 255), 1, cv2.LINE_AA)
        if ball is not None:
            centre = tuple(self.to_map(ball).tolist())
            cv2.circle(panel, centre, 6, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(panel, centre, 6, (0, 0, 0), 2, cv2.LINE_AA)
        region = image[self.y0:self.y0 + self.height, self.x0:self.x0 + self.width]
        cv2.addWeighted(panel, 0.9, region, 0.1, 0, region)


def camera_view_m(homography: np.ndarray, width: int, height: int) -> np.ndarray | None:
    """The part of the pitch in view (image below the horizon), in pitch metres."""
    corners = np.array([[0, height * 0.35], [width, height * 0.35], [width, height], [0, height]], float)
    view = to_pitch(corners, homography)
    return view if np.isfinite(view).all() and np.abs(view).max() < 500 else None


def render_overlay(frames, clip, camera: pd.DataFrame, people: pd.DataFrame, ball: pd.DataFrame, out_path: Path) -> int:
    """Write the overlay video (H.264, 25 fps). Frames without a trusted camera are copied unchanged."""
    import subprocess

    sign = -1 if clip.meta.get("rotated") else 1  # clip coordinates may be turned 180 degrees from the video's
    labels = {side: clip.meta["teams"][side]["name"] for side in ("home", "away")}
    people_by_frame = dict(tuple(people.groupby("frame")))
    players_by_frame = dict(tuple(clip.players.groupby("frame")))
    ball_px = ball.set_index("frame")
    clip_ball = clip.ball.set_index("frame")
    cams = camera.set_index("frame")
    writer, minimap, written = None, None, 0
    for j, frame in enumerate(frames):
        if j not in cams.index:
            break
        frame = frame.copy()
        if writer is None:
            height, width = frame.shape[:2]
            minimap = Minimap(width, height)
            writer = subprocess.Popen(
                ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
                 "-r", str(clip.meta["frame_rate"]), "-i", "-", "-c:v", "h264_videotoolbox", "-b:v", "8M",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path)], stdin=subprocess.PIPE)
        row = cams.loc[j]
        if bool(row["valid"]):
            h = row[H_COLUMNS].to_numpy(dtype=float).reshape(3, 3)
            draw_rings(frame, h, people_by_frame.get(j, people.iloc[:0]))
            if j in ball_px.index and bool(ball_px.loc[j, "confirmed"]):  # never a guessed, wandering marker
                draw_ball(frame, ball_px.loc[j, "px"], ball_px.loc[j, "py"])
            view = camera_view_m(h, frame.shape[1], frame.shape[0])
            map_ball = None
            if j in clip_ball.index and bool(clip_ball.loc[j, "alive"]):
                map_ball = (clip_ball.loc[j, "x"], clip_ball.loc[j, "y"])
            minimap.draw(frame, players_by_frame.get(j, clip.players.iloc[:0]), map_ball,
                         None if view is None else sign * view)
            draw_legend(frame, labels)
        writer.stdin.write(np.ascontiguousarray(frame).tobytes())
        written += 1
    if writer is not None:
        writer.stdin.close()
        writer.wait()
    return written
