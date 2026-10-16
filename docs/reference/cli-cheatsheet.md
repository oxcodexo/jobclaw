# Reference: CLI cheatsheet

Run from the repo root. State-changing commands go through `EXEC` (same container).

```bash
EXE="docker compose exec -T openclaw-gateway node openclaw.mjs"
```

## Stack

```bash
docker compose up -d                          # start (pulls on first run)
docker compose up -d --build openclaw-gateway # rebuild Chromium layer
docker compose up -d --force-recreate <svc>   # reload changed env vars
docker compose ps
docker compose logs -f openclaw-gateway
docker compose stop openclaw-gateway
docker compose down
```

## Config

```bash
python scripts/setup.py            # full guided setup (build, seed, apply, verify)
python scripts/setup.py --check    # diff desired keys vs live, no writes
scripts/check-queue.sh          # pending draft count (JSON, for --command jobs)
```

## Gateway / pairing / channels

```bash
$EXE pairing list telegram
$EXE pairing approve telegram <CODE>     # codes expire after 1h
$EXE channels status --probe
```

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
$EXE plugins install @openclaw/tavily-plugin
```

## Automations (cron)

```bash
$EXE automations add --cron "0 7 * * *" --tz Africa/Casablanca --message "<prompt>" \
  --name "<name>" --agent main --announce --channel telegram --to <CHAT_ID> \
  --model 9router/jobclaw-free
$EXE automations add --at 3m --message "<prompt>" --name "<tmp>" --agent main \
  --announce --channel telegram --to <CHAT_ID> --model 9router/jobclaw-free  # one-shot test
$EXE automations list
$EXE automations show <ID>
$EXE automations runs <ID>                  # run history
$EXE automations run <ID> --wait --wait-timeout 12m --poll-interval 5s
$EXE automations edit <ID> --message "<new prompt>"   # also: --model, --to, --cron, --disable/--enable
$EXE automations disable <ID> | automations enable <ID>
$EXE automations rm <ID>
```

## Sessions and transcripts

```bash
$EXE sessions list --all-agents --json
$EXE sessions tail --session-key "agent:main:cron:<JOB_ID>" --tail 30
$EXE sessions export-trajectory --session-key "<KEY>"   # bundle lands in container .openclaw/
```

## 9Router / Tavily (no OpenClaw involved)

```bash
curl -s -H "Authorization: Bearer $NINE_ROUTER_API_KEY" \
  http://127.0.0.1:20128/v1/models
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
```
