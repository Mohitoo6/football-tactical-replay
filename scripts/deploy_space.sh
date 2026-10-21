#!/usr/bin/env bash
# Deploy the online demo to a Hugging Face static Space (D38). Needs `hf auth login` as the Space's owner.
#   scripts/deploy_space.sh [owner/space]          default: Mohitrks/vyuh
# Builds from the last commit only (git archive), so .env, data/ and local footage never leave the machine.
# The demo is static: the six bundled clips with their cached explanations; uploads need a local run.
set -euo pipefail
SPACE="${1:-Mohitrks/vyuh}"
ROOT="$(git rev-parse --show-toplevel)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

git -C "$ROOT" archive HEAD | tar -x -C "$STAGE"
ln -s "$ROOT/web/node_modules" "$STAGE/web/node_modules"     # reuse the installed packages
(cd "$STAGE/web" && VITE_STATIC=1 npm run build)
(cd "$ROOT" && uv run python scripts/build_static_site.py "$STAGE/web/dist")

hf repos create "$SPACE" --repo-type space --space-sdk static --exist-ok >/dev/null
hf upload "$SPACE" "$STAGE/web/dist" . --repo-type space --delete "*" \
  --commit-message "Deploy $(git -C "$ROOT" rev-parse --short HEAD): $(git -C "$ROOT" log -1 --format=%s)"
echo "https://huggingface.co/spaces/$SPACE"
