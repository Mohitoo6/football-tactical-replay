#!/usr/bin/env bash
# Deploy the committed code to the Hugging Face Space (D38). Needs `hf auth login` as the Space's owner.
#   scripts/deploy_space.sh [owner/space]          default: Mohitrks/vyuh
# Only files in the last commit are uploaded (git archive), so .env, data/ and local footage never leave the machine.
set -euo pipefail
SPACE="${1:-Mohitrks/vyuh}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

git archive HEAD | tar -x -C "$STAGE"
cp deploy/space/README.md "$STAGE/README.md"   # the Space's card (YAML header), not the GitHub README

hf repos create "$SPACE" --repo-type space --space-sdk docker --exist-ok >/dev/null
hf upload "$SPACE" "$STAGE" . --repo-type space --delete "*" \
  --commit-message "Deploy $(git rev-parse --short HEAD): $(git log -1 --format=%s)"
echo "https://huggingface.co/spaces/$SPACE"
