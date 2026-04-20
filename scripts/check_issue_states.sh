#!/bin/bash
# Batch-query GitHub for the state of each issue/PR referenced in TRIAGE.md.
# Input:  $OUT_DIR/refs.txt — one issue/PR number per line
# Output: $OUT_DIR/states.jsonl — JSONL {n, s, c, pr, t}

set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(basename "$REPO_DIR")" == "zarr-python-planning" ]] \
  || { echo "unexpected REPO_DIR: $REPO_DIR (expected basename 'zarr-python-planning')"; exit 1; }

SCRIPT_DIR="$REPO_DIR/scripts"
OUT_DIR="$REPO_DIR/outputs"
IN="$OUT_DIR/refs.txt"
OUT="$OUT_DIR/states.jsonl"

mkdir -p "$OUT_DIR"
: > "$OUT"
while read -r n; do
  gh api "repos/zarr-developers/zarr-python/issues/$n" \
    --jq "{n: .number, s: .state, c: .closed_at, pr: (.pull_request != null), t: .title[:70]}" \
    2>/dev/null >> "$OUT"
done < "$IN"
echo "Wrote $(wc -l < "$OUT") entries to $OUT"
