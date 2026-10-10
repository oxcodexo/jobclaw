#!/usr/bin/env bash
# Deterministic --command job example: queue depth probe (no LLM call).
# Used as: openclaw automations create "*/30 * * * *" --command "scripts/check-queue.sh" ...
set -euo pipefail
QDIR="$(dirname "$0")/../openclaw-workspace/jobs/queue"
count=$(ls -1 "$QDIR" 2>/dev/null | wc -l | tr -d ' ')
echo "{\"queue_dir\": \"$QDIR\", \"pending_drafts\": $count}"
