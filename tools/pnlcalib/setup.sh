#!/bin/sh
# Install PnLCalib (GPL-2.0) as a separate tool in data/tools/pnlcalib (git-ignored), with its own venv.
# Needed only for broadcast-camera clips. Downloads ~0.5 GB of weights and ~0.7 GB of packages.
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DEST="$ROOT/data/tools/pnlcalib"
COMMIT=8c87391d6f4ea40c5e4d65e61529916c7a49ce62  # the version tested in DECISIONS.md, D28

if [ ! -d "$DEST/.git" ]; then
  git clone -q https://github.com/mguti97/PnLCalib.git "$DEST"
fi
git -C "$DEST" checkout -q "$COMMIT"

# Its requirements pin CUDA packages; on a Mac (or CPU) we skip them and PyQt (only for display).
grep -vE "^(nvidia-|triton|PyQt5)" "$DEST/requirements.txt" > "$DEST/requirements-nocuda.txt"
uv venv -q --python 3.11 "$DEST/.venv"
VIRTUAL_ENV="$DEST/.venv" uv pip install -q -r "$DEST/requirements-nocuda.txt"

mkdir -p "$DEST/weights"
for name in SV_kp SV_lines; do
  if [ ! -s "$DEST/weights/$name" ]; then
    curl -sSL -o "$DEST/weights/$name" "https://github.com/mguti97/PnLCalib/releases/download/v1.0.0/$name"
  fi
done
echo "PnLCalib ready in $DEST"
