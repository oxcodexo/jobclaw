# Reference: configuration

## `.env` variables

| Variable | Required | Purpose |
|---|---|---|
| `OPENCLAW_GATEWAY_TOKEN` | yes | gateway auth token (invent a long random string) |
| `TELEGRAM_BOT_TOKEN` | yes | BotFather token (see [Telegram setup](../how-to/telegram-setup.md)) |
| `TELEGRAM_ALLOWED_CHAT_IDS` | recommended | comma-separated numeric chat IDs |
| `NINE_ROUTER_PASSWORD` | yes | 9Router dashboard login (replaces default `123456`) |
| `NINE_ROUTER_API_KEY` | yes | 9Router endpoint key (see [free models](../how-to/free-models-9router.md)) |
| `TAVILY_API_KEY` | yes | Tavily search key (`tvly-...`, free 1,000 credits/mo) |
| `TZ` | no | cron timezone, default `UTC` (example: `Africa/Casablanca`) |
| `OPENCLAW_PORT` / `NINE_ROUTER_PORT` | no | host ports, defaults `18789` / `20128` |
| `OPENCLAW_BASE` / `NINE_ROUTER_IMAGE` | no | image overrides (base used at gateway build time; 9Router used at pull time). Gateway and `--profile cli` share the locally built image — always `--build` + repull together and check `--version` parity |

Env-only changes need `docker compose up -d --force-recreate <service>` — plain `restart`
does not reload environment.

## Live config keys (volume `openclaw-home`, no tracked file)

Flow: `python scripts/setup.py` applies the project key set (additive, idempotent;
`--check` shows drift, keys defined in `scripts/desired-config.json`) → restart gateway. Single tweaks: `config set <path> <value>`.
The live copy is doctor-managed (not in git; inspect via
`docker compose exec openclaw-gateway cat /home/node/.openclaw/openclaw.json`).
There is intentionally no tracked config file — full-file syncs clobber Doctor keys.

| Key | Purpose |
|---|---|
| `gateway.mode/bind/port` | `local` / `lan` / `18789` (fresh volumes need `gateway.mode local` seeded once — see tutorial step 2) |
| `browser.noSandbox` | required for Chromium in containers |
| `models.providers.9router` | `baseUrl` (inter-container `http://9router:20128/v1`), `apiKey` (SecretRef `${env:NINE_ROUTER_API_KEY}` resolved from container env at runtime — bare `${VAR}` never resolves; `setup.py` writes the ref form, never plaintext), `api: openai-completions`, `request.allowPrivateNetwork: true`, `models: [{id, name}]` (e.g. `jobclaw-free`; empty array is rejected) |
| `agents.defaults.model.primary` | e.g. `9router/jobclaw-free` (combo name is the model id) |
| `agents.defaults.modelPolicy.allow` | refs the gateway may use — job `--model` overrides must be listed |
| `agents.defaults.workspace` | `/home/node/.openclaw/workspace` |
| `channels.telegram` | `enabled: true`, `dmPolicy: pairing` (token via `TELEGRAM_BOT_TOKEN` env fallback) |
| `plugins.entries.tavily.enabled` | search plugin switch (key via `TAVILY_API_KEY` env; install package post-boot — see Tavily how-to) |
| `tools.web.search.provider` | `tavily` |
| `commands.ownerAllowFrom` | e.g. `["telegram:<YOUR_CHAT_ID>"]` for Telegram owner commands |

## Services (`docker-compose.yml`)

| Service | Image / build | Ports | Volumes |
|---|---|---|---|
| `9router` | `decolua/9router:0.5.104`, `DATA_DIR=/app/data` | `20128:20128` | `./data/9router-data:/app/data` |
| `openclaw-gateway` | built from `Dockerfile.gateway` (upstream + Chromium), stable `hostname: jobclaw-openclaw` | `18789:18789` | `openclaw-home` → `/home/node/.openclaw`, `openclaw-workspace` bind → `/home/node/.openclaw/workspace`, `browser-profiles` → `/home/node/.openclaw/browser-profiles` |
| `openclaw-cli` | upstream image, profile `cli`, `network_mode: service:openclaw-gateway`, entrypoint `node openclaw.mjs` | — | same home volume + workspace bind |

Stable hostnames matter: OpenClaw ties state ownership to the writer identity. Recreate-happy
workflows and foreign-hostname CLI writes poison `state/openclaw.sqlite` ("ownership could
not be verified" crash loop). Prefer `docker compose exec` for all state-writing commands —
see [CLI cheatsheet](cli-cheatsheet.md) and [architecture](../explanation/architecture.md).
