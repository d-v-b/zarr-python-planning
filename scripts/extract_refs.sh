#!/bin/bash
# Extract unique zarr-python issue/PR numbers referenced in TRIAGE.md.
# Matches both bare `#NNNN` mentions and GitHub URL forms
# (zarr-python/issues/NNNN and zarr-python/pull/NNNN).
# Output: $OUT_DIR/refs.txt — one issue/PR number per line, sorted ascending.

set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(basename "$REPO_DIR")" == "zarr-python-planning" ]] \
  || { echo "unexpected REPO_DIR: $REPO_DIR (expected basename 'zarr-python-planning')"; exit 1; }

SRC="$REPO_DIR/TRIAGE.md"
OUT_DIR="$REPO_DIR/outputs"
OUT="$OUT_DIR/refs.txt"

mkdir -p "$OUT_DIR"
grep -oE '#[0-9]{3,}|zarr-python/(issues|pull)/[0-9]+' "$SRC" \
  | grep -oE '[0-9]+' \
  | sort -un > "$OUT"
echo "Wrote $(wc -l < "$OUT") refs to $OUT"
