#!/usr/bin/env bash
# Sync tracked base config into the live named volume.
# Usage: scripts/sync-config.sh [--force] [--volume NAME] [--container NAME]
# The gateway only reads /home/node/.openclaw/openclaw.json inside the
# `openclaw-home` named volume (bind mounts fail Doctor's fchmod/atomic
# publishes on Windows; file mounts break atomic rewrites with EBUSY),
# so edit config/openclaw.json then run this, then restart the gateway.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="config/openclaw.json"
VOLUME="jobclaw-openclaw-home"
CONTAINER="jobclaw-openclaw"
FORCE=""

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --volume=*) VOLUME="${arg#--volume=}" ;;
    --container=*) CONTAINER="${arg#--container=}" ;;
    --volume) shift; VOLUME="${1:-$VOLUME}" ;;
    --container) shift; CONTAINER="${1:-$CONTAINER}" ;;
    -h|--help)
      echo "Usage: scripts/sync-config.sh [--force] [--volume NAME] [--container NAME]"
      exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 1 ;;
  esac
done

if [ ! -f "$SRC" ]; then echo "missing $SRC" >&2; exit 1; fi
if ! python3 -m json.tool "$SRC" >/dev/null 2>&1; then
  echo "invalid JSON in $SRC" >&2; exit 1
fi

live_tmp="$(mktemp)"
trap 'rm -f "$live_tmp"' EXIT
got_live=""

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  if docker cp "$CONTAINER:/home/node/.openclaw/openclaw.json" "$live_tmp" 2>/dev/null; then
    got_live=1
  fi
elif docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  if docker run --rm -v "$VOLUME:/target:ro" alpine cat /target/openclaw.json >"$live_tmp" 2>/dev/null; then
    got_live=1
  fi
fi

if [ -z "$FORCE" ] && [ -n "$got_live" ] && cmp -s "$SRC" "$live_tmp"; then
  echo "already in sync ($SRC -> $VOLUME/openclaw.json)"
  exit 0
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  # Backup doctor-managed live file first: full overwrite drops wizard/meta/skills/owner keys.
  docker cp "$CONTAINER:/home/node/.openclaw/openclaw.json" "$live_tmp" 2>/dev/null || true
  if [ -s "$live_tmp" ]; then
    backup="config/openclaw.live-backup-$(date +%F-%H%M%S).json"
    cp "$live_tmp" "$backup"
    echo "backed up live config -> $backup"
  fi
  docker cp "$SRC" "$CONTAINER:/home/node/.openclaw/openclaw.json"
  echo "synced $SRC -> $CONTAINER:/home/node/.openclaw/openclaw.json (volume $VOLUME)"
  echo "NOTE: full sync overwrites doctor-managed keys (wizard/meta/skills/owner). Prefer"
  echo "  'docker compose exec openclaw-gateway node openclaw.mjs config set <path> <value>'"
  echo "  for additive changes on live systems."
else
  docker volume inspect "$VOLUME" >/dev/null 2>&1 || docker volume create "$VOLUME" >/dev/null
  docker run --rm -v "$VOLUME:/target" -v "$PWD/config:/src:ro" alpine cp /src/openclaw.json /target/openclaw.json
  echo "synced $SRC -> volume $VOLUME/openclaw.json (gateway stopped; start with: docker compose up -d)"
fi
echo "then: docker compose restart openclaw-gateway"
