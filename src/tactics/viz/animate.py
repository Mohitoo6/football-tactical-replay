"""Animate a clip and save it as MP4 or GIF."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

from tactics.data.clips import Clip
from tactics.viz.pitch import FramePainter


def animate_clip(clip: Clip, step: int = 1, painter: FramePainter | None = None) -> FuncAnimation:
    """Build an animation of the clip in real time.

    `step` keeps every n-th frame (step=2 halves the file size); the playback
    speed is adjusted so the animation still runs in real time.
    """
    painter = painter or FramePainter(clip)
    frames = clip.ball["frame"].to_numpy()[::step]
    interval_ms = 1000 * step / clip.meta["frame_rate"]
    return FuncAnimation(painter.fig, painter.show, frames=frames, interval=interval_ms, blit=False)


def save_animation(clip: Clip, path: Path, step: int = 1, dpi: int = 100, overlays: bool = True) -> Path:
    """Render the clip to `path`. The format follows the extension: .mp4 (needs ffmpeg) or .gif."""
    path = Path(path)
    fps = clip.meta["frame_rate"] / step
    if path.suffix == ".mp4":
        writer = FFMpegWriter(fps=fps, bitrate=2500)
    elif path.suffix == ".gif":
        writer = PillowWriter(fps=fps)
    else:
        raise ValueError(f"unsupported format {path.suffix!r}; use .mp4 or .gif")

    painter = FramePainter(clip, overlays=overlays)
    animate_clip(clip, step, painter).save(path, writer=writer, dpi=dpi)
    plt.close(painter.fig)
    return path
