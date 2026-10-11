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
| `OPENCLAW_IMAGE` / `NINE_ROUTER_IMAGE` | no | image overrides |

Env-only changes need `docker compose up -d --force-recreate <service>` — plain `restart`
does not reload environment.

## `config/openclaw.json` (tracked base config)

One-way flow: edit this file → `scripts/sync-config.sh` → restart gateway. The live copy at
`data/openclaw-home/openclaw.json` is doctor-managed (gitignored).

| Key | Purpose |
|---|---|
| `gateway.mode/bind/port` | `local` / `lan` / `18789` |
| `browser.noSandbox` | required for Chromium in containers |
| `models.providers.9router` | `baseUrl` (inter-container `http://9router:20128/v1`), `apiKey: ${NINE_ROUTER_API_KEY}`, `api: openai-completions`, `request.allowPrivateNetwork: true`, `models: []` (discovery) |
| `agents.defaults.model.primary` | e.g. `9router/jobclaw-free` (combo name is the model id) |
| `agents.defaults.modelPolicy.allow` | refs the gateway may use — job `--model` overrides must be listed |
| `agents.defaults.workspace` | `/home/node/.openclaw/workspace` |
| `channels.telegram` | `enabled: true`, `dmPolicy: pairing` (token via `TELEGRAM_BOT_TOKEN` env fallback) |
| `plugins.entries.tavily.enabled` | search plugin switch |
| `tools.web.search.provider` | `tavily` |
| `commands.ownerAllowFrom` | e.g. `["telegram:<YOUR_CHAT_ID>"]` for Telegram owner commands |

## Services (`docker-compose.yml`)

| Service | Image / build | Ports | Volumes |
|---|---|---|---|
| `9router` | `decolua/9router:latest`, `DATA_DIR=/app/data` | `20128:20128` | `./data/9router-data:/app/data` |
| `openclaw-gateway` | built from `Dockerfile.gateway` (upstream + Chromium), stable `hostname: jobclaw-openclaw` | `18789:18789` | `data/openclaw-home`, `openclaw-workspace`, `browser-profiles` → `/home/node/.openclaw[/workspace]` |
| `openclaw-cli` | upstream image, profile `cli`, `network_mode: service:openclaw-gateway` | — | same home + workspace mounts |

Stable hostnames matter: OpenClaw ties state ownership to the writer identity. Recreate-happy
workflows and foreign-hostname CLI writes poison `state/openclaw.sqlite` ("ownership could
not be verified" crash loop). Prefer `docker compose exec` for all state-writing commands —
see [CLI cheatsheet](cli-cheatsheet.md) and [architecture](../explanation/architecture.md).
