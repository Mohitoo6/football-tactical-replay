"""Connection lines between team-mates in the same formation line (e.g. the back four)."""

import pandas as pd

Segment = tuple[tuple[float, float], tuple[float, float]]


def line_links(positions: pd.DataFrame, lines: dict[str, int]) -> list[Segment]:
    """Segments joining neighbouring players across the pitch within each formation line.

    positions: one row per player with columns player_id, x, y (a single frame).
    lines:     player_id -> line index (from formation detection). Players not
               in `lines` (e.g. the goalkeeper) get no links.
    """
    on_lines = positions[positions["player_id"].isin(lines)].assign(
        line=lambda df: df["player_id"].map(lines))
    segments = []
    for _, line in on_lines.groupby("line"):
        ordered = line.sort_values("y")[["x", "y"]].to_numpy()
        for a, b in zip(ordered[:-1], ordered[1:]):
            segments.append(((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    return segments
