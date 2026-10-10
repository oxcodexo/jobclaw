#!/usr/bin/env bash
# Sync tracked base config into the gitignored runtime copy.
# Usage: scripts/sync-config.sh [--force]
# The gateway only reads data/openclaw-home/openclaw.json (file mounts break
# OpenClaw's atomic rewrites with EBUSY), so edit config/openclaw.json then run this.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="config/openclaw.json"
DST="data/openclaw-home/openclaw.json"
if [ ! -f "$SRC" ]; then echo "missing $SRC"; exit 1; fi
if [ "${1:-}" = "--force" ] || [ ! -f "$DST" ] || ! cmp -s "$SRC" "$DST"; then
  cp "$SRC" "$DST"
  echo "synced $SRC -> $DST"
else
  echo "already in sync"
fi
