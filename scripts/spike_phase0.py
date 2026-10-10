"""Phase 0 spike: can kloppy load our datasets, how fast, and how much memory?

Throwaway script (not product code). Run one dataset per process so the peak
memory number belongs to that dataset only:

    uv run python scripts/spike_phase0.py metrica
    uv run python scripts/spike_phase0.py dfl
"""

import resource
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from kloppy import metrica, sportec
from mplsoccer import Pitch

ROOT = Path(__file__).resolve().parents[1]
DFL_DIR = ROOT / "data" / "raw" / "dfl"
OUT_DIR = ROOT / "outputs"


def peak_memory_mb() -> float:
    # macOS reports ru_maxrss in bytes (Linux uses kilobytes).
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def load(name: str):
    # "secondspectrum" = metres, origin at the pitch centre (our target system, D3).
    if name == "metrica":
        return metrica.load_open_data(match_id=1, coordinates="secondspectrum")
    if name == "dfl":
        meta = next(DFL_DIR.glob("*matchinformation*J03WMX.xml"))
        raw = next(DFL_DIR.glob("*positions_raw*J03WMX.xml"))
        return sportec.load_tracking(meta_data=meta, raw_data=raw, coordinates="secondspectrum")
    raise SystemExit(f"unknown dataset: {name}")


def main(name: str) -> None:
    start = time.perf_counter()
    dataset = load(name)
    load_s = time.perf_counter() - start
    print(f"== {name}: loaded {len(dataset.records):,} frames in {load_s:.1f}s, "
          f"peak memory {peak_memory_mb():,.0f} MB")

    meta = dataset.metadata
    print(f"frame rate: {meta.frame_rate} fps")
    print(f"coordinate system: {type(meta.coordinate_system).__name__}, "
          f"origin={meta.coordinate_system.origin}, "
          f"pitch={meta.pitch_dimensions.x_dim} x {meta.pitch_dimensions.y_dim}")
    for team in meta.teams:
        named = [p.name for p in team.players if p.name][:3]
        print(f"team: {team.name} ({team.ground}), {len(team.players)} players, "
              f"formation={team.starting_formation}, e.g. {named}")

    start = time.perf_counter()
    df = dataset.to_df()
    print(f"to_df: {df.shape[0]:,} rows x {df.shape[1]} cols in "
          f"{time.perf_counter() - start:.1f}s, peak memory {peak_memory_mb():,.0f} MB")

    # One mid-game frame: how many players have a position, per team?
    row = df.iloc[len(df) // 4]
    print(f"sample frame {row['frame_id']} (period {row['period_id']}, "
          f"t={row['timestamp']}), ball=({row['ball_x']:.2f}, {row['ball_y']:.2f})")
    for team in meta.teams:
        ids = [p.player_id for p in team.players]
        on_pitch = [pid for pid in ids if f"{pid}_x" in row and row[f"{pid}_x"] == row[f"{pid}_x"]]
        print(f"  {team.name}: {len(on_pitch)} players with x/y in this frame")

    x_cols = [c for c in df.columns if c.endswith("_x")]
    y_cols = [c for c in df.columns if c.endswith("_y")]
    print(f"x range: {df[x_cols].min().min():.2f} .. {df[x_cols].max().max():.2f}")
    print(f"y range: {df[y_cols].min().min():.2f} .. {df[y_cols].max().max():.2f}")
    print(f"ball missing in {df['ball_x'].isna().mean():.1%} of frames")

    # Compatibility check: can mplsoccer draw this frame with pandas 3?
    dims = meta.pitch_dimensions
    pitch = Pitch(pitch_type="secondspectrum",
                  pitch_length=dims.x_dim.max - dims.x_dim.min,
                  pitch_width=dims.y_dim.max - dims.y_dim.min)
    fig, ax = pitch.draw(figsize=(8, 5.5))
    for team, colour in zip(meta.teams, ["tab:red", "tab:blue"]):
        xs = [row[f"{p.player_id}_x"] for p in team.players if f"{p.player_id}_x" in row]
        ys = [row[f"{p.player_id}_y"] for p in team.players if f"{p.player_id}_y" in row]
        pitch.scatter(xs, ys, ax=ax, color=colour, s=80, label=team.name)
    pitch.scatter(row["ball_x"], row["ball_y"], ax=ax, color="black", s=30)
    ax.legend(loc="upper center", ncol=2, fontsize=8)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"spike_{name}.png"
    fig.savefig(out, dpi=100)
    plt.close(fig)
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "metrica")
