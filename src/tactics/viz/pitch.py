"""Draw clip frames on a pitch.

`FramePainter` creates the pitch, markers and labels once; `show(frame)` then
moves them to a given frame. A still image calls `show` once, an animation
calls it for every frame, so both always look the same.
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from mplsoccer import Pitch

from tactics.data.clips import Clip, match_clock
from tactics.geometry.formation import detect_formation
from tactics.geometry.links import line_links
from tactics.geometry.shape import hull_vertices, outfield, team_shape

PITCH_LENGTH_M = 105
PITCH_WIDTH_M = 68
PITCH_COLOUR = "#2e6b3f"
LINE_COLOUR = "#e8efe9"
# Close to the real kits in our match (Köln white at home, Bayern red away).
TEAM_COLOURS = {"home": "#f5f5f5", "away": "#d7263d"}
NUMBER_COLOURS = {"home": "#111111", "away": "#ffffff"}
BALL_COLOUR = "#ffd23f"
PLAYER_SIZE = 260
DATA_CREDIT = "Data: DFL / Bassek et al. 2025, CC-BY 4.0"
BALL_OUT_TEXT = "Ball out of play"


def make_pitch() -> Pitch:
    """A pitch in our coordinate system: metres, origin at the centre spot."""
    return Pitch(
        pitch_type="secondspectrum",
        pitch_length=PITCH_LENGTH_M,
        pitch_width=PITCH_WIDTH_M,
        pitch_color=PITCH_COLOUR,
        line_color=LINE_COLOUR,
        linewidth=1.5,
    )


def team_label(clip: Clip, side: str) -> str:
    """Legend label for a team, e.g. "1. FC Köln (4-2-3-1)"."""
    info = clip.meta["teams"][side]
    return f"{info['name']} ({info['formation']})"


class FramePainter:
    """Draws a clip on a pitch; call `show(frame)` to display any frame.

    With `overlays=True` it also draws each team's shape (convex hull of the
    outfield players), lines joining team-mates in the same formation line,
    and the shape metrics under the pitch.
    """

    def __init__(self, clip: Clip, ax: Axes | None = None, overlays: bool = True):
        self.clip = clip
        self.overlays = overlays
        pitch = make_pitch()
        if ax is None:
            fig, ax = pitch.draw(figsize=(10, 7.6))
            fig.subplots_adjust(bottom=0.16)  # room for the legend and metrics under the pitch
        else:
            pitch.draw(ax=ax)
        self.ax = ax
        self.fig = ax.figure
        self._players_by_frame = dict(tuple(clip.players.groupby("frame")))
        self._ball = clip.ball.set_index("frame")

        if overlays:
            self._setup_overlays()

        self._dots = {
            side: ax.scatter([], [], s=PLAYER_SIZE, color=TEAM_COLOURS[side], edgecolors="black",
                             linewidth=1, zorder=3, label=team_label(clip, side))
            for side in ("home", "away")
        }
        self._numbers = {
            p.player_id: ax.text(0, 0, str(p.jersey), color=NUMBER_COLOURS[p.team], fontsize=8,
                                 fontweight="bold", ha="center", va="center", zorder=4, visible=False)
            for p in clip.players.drop_duplicates("player_id").itertuples()
        }
        self._ball_dot = ax.scatter([], [], s=70, color=BALL_COLOUR, edgecolors="black",
                                    linewidth=1, zorder=5, label="Ball")
        self._ball_out = ax.text(0.5, 0.97, BALL_OUT_TEXT, transform=ax.transAxes, ha="center", va="top",
                                 fontsize=10, color="white", fontweight="bold", visible=False)
        self._title = ax.set_title("", fontsize=12)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False, fontsize=9)
        ax.text(0.99, -0.17 if overlays else -0.07, DATA_CREDIT, transform=ax.transAxes, ha="right",
                fontsize=7, color="grey")

    def attacking_right(self, side: str) -> bool:
        """In a clip the focus team attacks left to right, so its opponent attacks right to left."""
        return side == self.clip.meta["focus_team"]

    def _setup_overlays(self) -> None:
        # Formation lines are decided once per clip (from frames with the ball in play),
        # so the connection lines do not flicker from frame to frame.
        clip = self.clip
        in_play = clip.players[clip.players["frame"].isin(clip.ball.loc[clip.ball["alive"], "frame"])]
        self.detected_formation, self._formation_lines = {}, {}
        self._hulls, self._links = {}, {}
        for side in ("home", "away"):
            result, positions = detect_formation(in_play, side, self.attacking_right(side))
            # Templates have 10 outfield players, so a label for fewer (red card) would mislead.
            self.detected_formation[side] = (
                result.formation if len(positions) == 10 else f"n/a, {len(positions)} outfield players")
            self._formation_lines[side] = dict(zip(positions["player_id"], positions["line"]))
            self._hulls[side] = self.ax.add_patch(Polygon(
                np.zeros((1, 2)), closed=True, facecolor=TEAM_COLOURS[side], edgecolor=TEAM_COLOURS[side],
                alpha=0.18, linewidth=1.5, zorder=2))
            self._links[side] = self.ax.add_collection(LineCollection(
                [], colors=TEAM_COLOURS[side], linewidths=1.8, alpha=0.9, zorder=2.5))
        self._metrics = self.ax.text(0.5, -0.075, "", transform=self.ax.transAxes, ha="center", va="top",
                                     fontsize=8.5, linespacing=1.5)

    def _show_overlays(self, players) -> None:
        texts = []
        for side in ("home", "away"):
            team = outfield(players[players["team"] == side])
            points = team[["x", "y"]].to_numpy()
            vertices = hull_vertices(points)
            self._hulls[side].set_xy(vertices if len(vertices) else np.zeros((1, 2)))
            self._links[side].set_segments(line_links(team, self._formation_lines[side]))
            if len(points) >= 3:
                m = team_shape(points, self.attacking_right(side))
                texts.append(
                    f"{self.clip.meta['teams'][side]['name']} (shape in clip: {self.detected_formation[side]})  "
                    f"width {m.width_m:.0f} m · depth {m.depth_m:.0f} m · area {m.hull_area_m2:.0f} m² · "
                    f"defensive line {m.line_height_m:.0f} m from goal")
        self._metrics.set_text("\n".join(texts))

    def show(self, frame: int) -> None:
        """Move every marker and label to `frame`."""
        if frame not in self._ball.index:
            raise ValueError(f"frame {frame} is not in clip {self.clip.meta['clip_id']!r}")
        players = self._players_by_frame.get(frame, self.clip.players.iloc[0:0])

        for side, dots in self._dots.items():
            dots.set_offsets(players.loc[players["team"] == side, ["x", "y"]].to_numpy())
        on_pitch = set(players["player_id"])
        for player_id, number in self._numbers.items():
            number.set_visible(player_id in on_pitch)
        for p in players.itertuples():
            self._numbers[p.player_id].set_position((p.x, p.y))
        if self.overlays:
            self._show_overlays(players)

        # While the ball is dead the provider freezes its last position, which can be
        # far from the real ball (DECISIONS.md, D11), so we hide it instead.
        ball = self._ball.loc[frame]
        self._ball_dot.set_offsets([[ball["x"], ball["y"]]] if ball["alive"] else [[float("nan")] * 2])
        self._ball_out.set_visible(not ball["alive"])

        meta = self.clip.meta
        focus = meta["teams"][meta["focus_team"]]["name"]
        clock = match_clock(meta["period"], float(ball["time_s"]))
        self._title.set_text(f"{meta['title']}  |  {clock}\n{focus} attacking →")


def draw_frame(clip: Clip, frame: int, ax: Axes | None = None, overlays: bool = True) -> Axes:
    """Draw both teams and the ball at `frame`. Returns the axes it drew on."""
    painter = FramePainter(clip, ax, overlays)
    painter.show(frame)
    return painter.ax


def save_frame(clip: Clip, frame: int, path, overlays: bool = True) -> None:
    """Draw `frame` and save it as an image file."""
    ax = draw_frame(clip, frame, overlays=overlays)
    ax.figure.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(ax.figure)
