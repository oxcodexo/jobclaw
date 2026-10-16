# How-to: wire free models via 9Router

9Router is a local model router (dashboard at http://127.0.0.1:20128). It sits between
OpenClaw and free providers so one OpenAI-compatible endpoint serves many models with
fallback. 9Router itself never bills you. Requires 9Router 0.5.104+ (OpenCode-pool
fixes); check with `python scripts/setup.py --check-versions`.

## 1. Log in to the dashboard

- URL: http://127.0.0.1:20128
- Password: `NINE_ROUTER_PASSWORD` from `.env`.

## 2. Connect providers (Providers page)

- **OpenCode Free** → **Connect** (one click, no auth; model list varies over time).
- **Kiro AI** → **Connect** → OAuth with AWS Builder ID (free), Google, or GitHub
  (≈ 50 credits/month free). Fallback pool; tool calls through Kiro can be flaky.

## 3. Build the combo (Combo page)

Create `jobclaw-free`, most reliable first:

1. `oc/muse-spark-1.3-contributor-free`
2. `oc/muse-spark-1.2-contributor-free`
3. `kr/*` non-thinking models (needs Kiro connected)
4. `kr/*-thinking*` last (burns credits fast)

Only add a member after it answers a real chat call — appearing in `/v1/models`
does not mean it works.

## 4. Create the endpoint key, plug it in

Endpoint / API keys → new key (e.g. name `openclaw`) → copy into `.env`:

```bash
NINE_ROUTER_API_KEY=<key-from-dashboard>
```

Apply + verify (key stays in `.env`, never in git):

```bash
docker compose up -d --force-recreate openclaw-gateway   # .env changed: recreate, not restart
python scripts/setup.py --verify   # per-member OK/FAIL, exits non-zero until one answers
docker compose exec openclaw-gateway node openclaw.mjs infer model run --gateway \
  --model 9router/jobclaw-free --prompt "Reply with exactly: GATEWAY_OK" --json
# expect: "outputs": [{"text": "GATEWAY_OK", ...}]
```

Always verify with `--gateway` (same path the agent uses). Bare `infer model run`
takes the local path and 401s even on a healthy stack — ignore that 401.

## When it fails

| Symptom | Fix |
|---|---|
| Dashboard rejects login | set `NINE_ROUTER_PASSWORD`, `docker compose up -d --force-recreate 9router` (default `123456` is rejected over the Docker bridge; `INITIAL_PASSWORD` only seeds fresh DBs, otherwise wipe `data/9router-data/` and `up -d`) |
| `404 No active credentials for provider: X` | Providers → Connect X, then retry |
| `403 FreeTierError` on `oc/*` | upgrade 9Router (`--check-versions`, then bump `NINE_ROUTER_IMAGE`) |
| `400 Unsupported model <slug>` | remove that member from the combo |
| `--verify` all FAIL | connect a provider first, then use only members that answer |
