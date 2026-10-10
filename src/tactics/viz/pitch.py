"""Draw a single frame of a clip on a pitch."""

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from mplsoccer import Pitch

from tactics.data.clips import Clip, match_clock

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


def draw_frame(clip: Clip, frame: int, ax: Axes | None = None) -> Axes:
    """Draw both teams and the ball at `frame`, with a title and legend.

    Creates a new figure when `ax` is None and returns the axes it drew on.
    """
    pitch = make_pitch()
    if ax is None:
        _, ax = pitch.draw(figsize=(10, 7))
    else:
        pitch.draw(ax=ax)

    players = clip.players[clip.players["frame"] == frame]
    ball = clip.ball[clip.ball["frame"] == frame]
    if ball.empty:
        raise ValueError(f"frame {frame} is not in clip {clip.meta['clip_id']!r}")

    for side in ("home", "away"):
        team = players[players["team"] == side]
        info = clip.meta["teams"][side]
        pitch.scatter(team["x"], team["y"], ax=ax, s=PLAYER_SIZE, color=TEAM_COLOURS[side],
                      edgecolors="black", linewidth=1, zorder=3, label=f"{info['name']} ({info['formation']})")
        for row in team.itertuples():
            pitch.annotate(str(row.jersey), (row.x, row.y), ax=ax, color=NUMBER_COLOURS[side],
                           fontsize=8, fontweight="bold", ha="center", va="center", zorder=4)

    pitch.scatter(ball["x"], ball["y"], ax=ax, s=70, color=BALL_COLOUR, edgecolors="black",
                  linewidth=1, zorder=5, label="Ball")

    meta = clip.meta
    focus = meta["teams"][meta["focus_team"]]["name"]
    clock = match_clock(meta["period"], float(ball["time_s"].iloc[0]))
    ax.set_title(f"{meta['title']}  |  {clock}\n{focus} attacking →", fontsize=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False, fontsize=9)
    ax.text(0.99, -0.07, DATA_CREDIT, transform=ax.transAxes, ha="right", fontsize=7, color="grey")
    return ax


def save_frame(clip: Clip, frame: int, path) -> None:
    """Draw `frame` and save it as an image file."""
    ax = draw_frame(clip, frame)
    ax.figure.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(ax.figure)
