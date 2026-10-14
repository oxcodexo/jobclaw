#!/usr/bin/env bash
# Bootstrap live OpenClaw config in the named volume via additive `config set`.
# Replaces the old full-file sync: every key is set individually, so Doctor-managed
# keys (wizard.*, meta.*, skills.*, owner identity) are never touched.
#
# Usage:
#   scripts/bootstrap.sh           apply desired keys to the running gateway
#   scripts/bootstrap.sh --check   diff desired keys vs live config, no writes
#   scripts/bootstrap.sh --one-shot  use a one-shot container (gateway stopped,
#                                    e.g. fresh volume that won't boot without gateway.mode)
#
# Prerequisites: NINE_ROUTER_API_KEY non-empty in .env (placeholder boots, real key
# for inference); image jobclaw-openclaw:latest built (docker compose build).
# Owner chat ID is deliberately NOT set here — see docs/how-to/telegram-setup.md.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="apply"
if [ "${1:-}" = "--check" ]; then MODE="check"; shift; fi
if [ "${1:-}" = "--one-shot" ]; then MODE_ONESHOT=1; shift; fi
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "Usage: scripts/bootstrap.sh [--check] [--one-shot]"; exit 0
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "jobclaw-openclaw" && [ -z "${MODE_ONESHOT:-}" ]; then
  # shellcheck disable=SC2086
  CLI="docker compose exec -T openclaw-gateway node openclaw.mjs"
  LIVE_SRC="container"
else
  if ! docker image inspect jobclaw-openclaw:latest >/dev/null 2>&1; then
    echo "missing image jobclaw-openclaw:latest — run: docker compose build openclaw-gateway" >&2
    exit 1
  fi
  # shellcheck disable=SC2086
  CLI="docker run --rm --hostname jobclaw-openclaw -v jobclaw-openclaw-home:/home/node/.openclaw jobclaw-openclaw:latest node openclaw.mjs"
  LIVE_SRC="volume"
fi

# Desired state: path -> JSON value. Scalar/array leaves only (additive, idempotent).
DESIRED=$(cat <<'JSON'
{
  "gateway.mode": "local",
  "gateway.bind": "lan",
  "gateway.port": 18789,
  "browser.noSandbox": true,
  "models.providers.9router.baseUrl": "http://9router:20128/v1",
  "models.providers.9router.apiKey": "${NINE_ROUTER_API_KEY}",
  "models.providers.9router.api": "openai-completions",
  "models.providers.9router.request.allowPrivateNetwork": true,
  "models.providers.9router.models": [{"id": "jobclaw-free", "name": "jobclaw-free"}],
  "agents.defaults.workspace": "/home/node/.openclaw/workspace",
  "agents.defaults.model.primary": "9router/jobclaw-free",
  "agents.defaults.modelPolicy.allow": ["9router/jobclaw-free", "9router/kr/claude-haiku-4.5", "9router/kr/claude-sonnet-4.5"],
  "channels.telegram.enabled": true,
  "channels.telegram.dmPolicy": "pairing",
  "plugins.entries.tavily.enabled": true,
  "tools.web.search.provider": "tavily"
}
JSON
)

if [ "$MODE" = "check" ]; then
  live_tmp="$(mktemp)"; trap 'rm -f "$live_tmp"' EXIT
  if [ "$LIVE_SRC" = "container" ]; then
    docker cp jobclaw-openclaw:/home/node/.openclaw/openclaw.json "$live_tmp" 2>/dev/null || {
      echo "no live openclaw.json yet (fresh volume — run bootstrap without --check)"; exit 2; }
  else
    docker run --rm -v jobclaw-openclaw-home:/target:ro alpine cat /target/openclaw.json >"$live_tmp" 2>/dev/null || {
      echo "no live openclaw.json yet (fresh volume — run bootstrap without --check)"; exit 2; }
  fi
  DESIRED="$DESIRED" LIVE="$live_tmp" python3 - <<'PY'
import json, os
desired = json.loads(os.environ["DESIRED"])
try:
    live = json.load(open(os.environ["LIVE"]))
except Exception:
    live = {}
def get(d, path):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return (False, None)
        cur = cur[part]
    return (True, cur)
rc = 0
for path, want in desired.items():
    found, got = get(live, path)
    if not found:
        print(f"MISSING {path} (want {json.dumps(want)})"); rc = 1
    elif got != want:
        print(f"DIFF    {path}: live={json.dumps(got)} want={json.dumps(want)}"); rc = 1
    else:
        print(f"OK      {path}")
raise SystemExit(rc)
PY
  exit $?
fi

BATCH="$(DESIRED="$DESIRED" python3 -c 'import json,os; print(json.dumps([{"path":p,"value":v} for p,v in json.loads(os.environ["DESIRED"]).items()]))')"
# shellcheck disable=SC2086
$CLI config set --batch-json "$BATCH"
echo "bootstrap applied (additive — doctor-managed keys untouched)"
echo "then: docker compose restart openclaw-gateway  # if the gateway was already running"
