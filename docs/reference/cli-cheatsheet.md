# Reference: CLI cheatsheet

Run from the repo root. State-changing commands go through `EXEC` (same container).

```bash
EXE="docker compose exec -T openclaw-gateway node openclaw.mjs"
```

## Setup (preferred entry point)

```bash
python scripts/setup.py                 # guided setup (idempotent; builds, provisions, applies, recreates)
python scripts/setup.py --check         # drift vs desired keys, no writes
python scripts/setup.py --verify        # per-member 9Router chat probe
python scripts/setup.py --check-versions # current / validated / latest + image availability, no writes
python scripts/setup.py --one-shot      # apply current .env config via the stopped-gateway setup service
python scripts/setup.py --latest        # preselect Latest (confirms unless --yes)
python scripts/setup.py --offline       # skip version metadata network calls
python scripts/setup.py --yes           # accept defaults, keep integrations, no prompts
```

Setup installs the selected search plugin and provisions the 9Router `jobclaw` key and
`jobclaw-free` combo. It stops the gateway, applies config with the stable-hostname
`openclaw-setup` service, and recreates the gateway once. You normally never need a manual
`--force-recreate` after setup.

## Stack

```bash
docker compose up -d                          # start (pulls on first run)
docker compose up -d --build openclaw-gateway # rebuild Chromium/RenderCV layer
docker compose up -d --force-recreate <svc>   # reload changed env vars (manual .env edits only)
docker compose ps
docker compose logs -f openclaw-gateway
docker compose stop openclaw-gateway
docker compose down
```

Do **not** use `docker compose down -v` casually: it removes all named volumes, including
OpenClaw home and 9Router state. The 9Router destructive reset uses only
`docker volume rm jobclaw-9router-data` — see [rotate secrets](../how-to/rotate-secrets.md).

## Config

```bash
python scripts/setup.py --one-shot   # stop gateway, apply conditional desired config, start again
$EXE config get <path>               # inspect one live key
# config set requires the gateway stopped:
docker compose stop openclaw-gateway
docker compose run --rm -T openclaw-setup config set <path> <value>
docker compose up -d openclaw-gateway
```

`--one-shot` does not change versions, provision 9Router, or install plugins. It uses the
current `.env`.

## Gateway / pairing / channels

```bash
$EXE pairing list telegram
$EXE pairing approve telegram <CODE>     # pairing mode only; codes expire after 1h
$EXE channels status --probe
```

Allowlist mode has no pairing approval step.

## Models

```bash
$EXE infer model run --gateway --model 9router/jobclaw-free \
  --prompt "Reply with exactly: GATEWAY_OK" --json
# --gateway = same path the agent uses. Bare `infer` runs local and 401s on
# healthy stacks (different auth resolution) — that 401 means nothing.
```

## Browser

```bash
$EXE browser status
$EXE browser start            # needs browser.noSandbox in containers
$EXE browser open <URL>       # + snapshot/click/fill/tabs/... (see browser --help)
$EXE browser doctor
```

## Skills and plugins

```bash
$EXE skills list
$EXE skills check | grep -i tavily
# Advanced manual install if setup warned about a plugin failure:
docker compose stop openclaw-gateway
docker compose run --rm -T openclaw-setup plugins install @openclaw/tavily-plugin
docker compose up -d --force-recreate openclaw-gateway
```

Setup already installs `@openclaw/tavily-plugin` or `@openclaw/duckduckgo-plugin` when the
matching search provider is selected.

## Automations (manual probes only)

JobClaw runs everything on demand from chat.
The commands below are kept for manual one-shot probes only:

```bash
$EXE automations add --at 3m --message "<prompt>" --name "<tmp>" --agent main \
  --announce --channel telegram --to <USER_ID> --model 9router/jobclaw-free  # one-shot test
$EXE automations list
$EXE automations show <ID>
$EXE automations runs <ID>                  # run history
$EXE automations run <ID> --wait --wait-timeout 12m --poll-interval 5s
$EXE automations rm <ID>
```

## Sessions and transcripts

```bash
$EXE sessions list --all-agents --json
$EXE sessions tail --session-key "agent:main:<SESSION_KEY>" --tail 30
$EXE sessions export-trajectory --session-key "<KEY>"   # bundle lands in container .openclaw/
```

## 9Router / volumes (no OpenClaw involved)

```bash
docker compose exec 9router wget -qO- http://127.0.0.1:20128/api/health
curl -s -H "Authorization: Bearer $NINE_ROUTER_API_KEY" \
  http://127.0.0.1:20128/v1/models
docker compose exec 9router sh -c 'ls -la /app/data'
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
```

`$NINE_ROUTER_API_KEY` must be exported in your shell for the curl form. Never call and print
`GET /api/keys` — its response contains full key values. Use `python scripts/setup.py
--verify` instead.
