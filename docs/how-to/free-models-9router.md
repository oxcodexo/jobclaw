# How-to: wire free models via 9Router

9Router is a local model router (dashboard at http://127.0.0.1:20128). It sits between
OpenClaw and free providers so one OpenAI-compatible endpoint serves many models with
fallback. 9Router itself never bills you.

## 1. Log in to the dashboard

- URL: http://127.0.0.1:20128
- Password: `NINE_ROUTER_PASSWORD` from `.env` (set via `INITIAL_PASSWORD` in compose —
  the default `123456` is rejected for browser access because the dashboard sees Docker
  bridge traffic as "remote").

## 2. Connect providers (Providers page)

- **Kiro AI** → **Connect** → OAuth with AWS Builder ID (free), Google, or GitHub.
  Free tier ≈ 50 credits/month (new accounts also get trial credits). Tokens auto-refresh.
- **OpenCode Free** → **Connect** (one click, no auth; model list varies over time).

> Known limitation (verified): tool calls routed through Kiro can corrupt
> (`Kiro tool input must be valid object JSON`) and free-tier prompts can time out. Chat
> works; agentic work is unreliable on `kr/*`. Prefer OpenCode Free models first in the
> combo and keep Kiro as fallback. See [free-tier limits](../explanation/free-tier-limits.md).

## 3. Build the combo (Combo page)

Create `jobclaw-free`, add models highest-priority first. Proven order:

1. `oc/muse-spark-...` (OpenCode Free — tool calls verified working)
2. Other `oc/*` / `mmf/*` free models
3. `kr/*` non-thinking models (fallback)
4. `kr/*-thinking*` last (accurate but burns credits fast)

## 4. Create the endpoint key, plug it in

Endpoint / API keys → new key (e.g. name `openclaw`) → copy into `.env`:

```bash
NINE_ROUTER_API_KEY=<key-from-dashboard>
```

Apply + verify (key stays in `.env`, never in git):

```bash
docker compose up -d
curl -s -H "Authorization: Bearer $NINE_ROUTER_API_KEY" \
  http://127.0.0.1:20128/v1/models | python3 -c \
  "import json,sys; [print('-',m['id']) for m in json.load(sys.stdin).get('data',[])]"
```

You should see `jobclaw-free` plus provider models. Then prove inference end-to-end
through OpenClaw (not just 9Router):

```bash
docker compose exec openclaw-gateway node dist/index.js infer model run \
  --model 9router/jobclaw-free --prompt "Reply with exactly: GATEWAY_OK" --json
```

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard rejects `123456` | bridge-network access requires custom password | set `NINE_ROUTER_PASSWORD`, `docker compose up -d --force-recreate 9router` |
| New password rejected too | `INITIAL_PASSWORD` only seeds fresh DBs | `docker compose down`, delete `data/9router-data/*` contents, `up -d` |
| `/v1/models` → `API key required` | expected without key | create endpoint key (step 4) |
| `kr/*` tool timeouts / integrity errors | Kiro bridge limits | reorder combo OC-first (step 3) |
| `oc/*` models missing from list | provider not synced | dashboard → Providers → refresh/reconnect OpenCode Free |
