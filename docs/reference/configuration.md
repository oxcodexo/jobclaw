# Reference: configuration

## Stack presets

`scripts/setup.py` supports two presets only:

| Preset | OpenClaw | 9Router | When |
|---|---|---|---|
| **Validated** (default) | `2026.9.9` | `0.5.104` | Recommended; the tested pair |
| **Latest** | newest stable upstream | newest stable upstream | Opt-in after checking release notes |

`python scripts/setup.py --check-versions` prints current, Validated, Latest, and image
availability without writing anything. Set Latest deliberately with
`python scripts/setup.py --latest`; add `--yes` for no prompt. `--offline` skips all version
metadata calls and uses the Validated pair.

There is no “previous” or custom menu entry. Editing `OPENCLAW_BASE` or `NINE_ROUTER_IMAGE`
in `.env` still works as an escape hatch, but setup and `--check-versions` flag the pair as
outside the supported presets. Downgrades may not be schema-compatible — back up volumes
first (see [update](../how-to/update.md)).

## `.env` variables

Setup owns the keys below. It preserves comments and ordering, updates active `KEY=` lines
only (commented examples stay untouched), appends missing keys, quotes values safely, and
writes atomically. Secrets are never printed.

| Variable | Required | Purpose |
|---|---|---|
| `TZ` | no | container timezone, default `UTC` (example: `Europe/London`) |
| `OPENCLAW_PORT` / `NINE_ROUTER_PORT` | no | host ports, defaults `18789` / `20128` |
| `OPENCLAW_BASE` | yes | gateway base image, e.g. `ghcr.io/openclaw/openclaw:2026.9.9`. Written by setup; there is no Dockerfile or Compose default |
| `OPENCLAW_GATEWAY_TOKEN` | yes | gateway auth token. Setup generates one if missing/placeholder |
| `NINE_ROUTER_IMAGE` | yes | 9Router image, e.g. `decolua/9router:0.5.104`. No Compose default |
| `NINE_ROUTER_PASSWORD` | yes | dashboard login password. Setup generates one if missing/placeholder. **A stored hash in the volume wins** — changing this alone does not rotate an existing password |
| `NINE_ROUTER_API_KEY` | yes in practice | endpoint key for the gateway. Setup creates/reuses the `jobclaw` key and writes it here. A placeholder boots a fresh gateway until setup finishes |
| `TELEGRAM_ENABLED` | no | `true` / `false`; default `false` |
| `TELEGRAM_DM_POLICY` | no | `allowlist` (default) or `pairing` |
| `TELEGRAM_BOT_TOKEN` | no | bot token from @BotFather; required only when Telegram is enabled |
| `TELEGRAM_ALLOWED_CHAT_IDS` | no | comma-separated **numeric Telegram user IDs** of people allowed to DM the bot; not the bot's own ID and not group/chat IDs. Required for allowlist mode |
| `WEB_SEARCH_PROVIDER` | no | `tavily`, `duckduckgo`, or `disabled` (default). Disabled stays explicit |
| `TAVILY_API_KEY` | no | `tvly-...`; required only when provider is `tavily` |

> Telegram and Tavily are optional. On upgrade from an older `.env`, setup infers the new
> markers from existing tokens and the live config: token present → Telegram enabled; live
> `dmPolicy` preserved when available (otherwise allowlist if IDs exist, else pairing);
> Tavily key present → Tavily. Explicit markers always win.

## Live config keys (volume `openclaw-home`, no tracked file)

Flow: `python scripts/setup.py` builds the desired key set, stops the gateway, applies the
keys offline with the stable-hostname `openclaw-setup` service, then recreates the gateway.
`--check` compares the same conditional key set against the live config and never prompts or
writes. Single tweaks: `config set <path> <value>`.

The live copy is doctor-managed (not in git; inspect via
`docker compose exec openclaw-gateway cat /home/node/.openclaw/openclaw.json`). There is
intentionally no tracked full config file — full-file syncs clobber Doctor keys.

Always-on keys (`scripts/desired-config.json`):

| Key | Purpose |
|---|---|
| `gateway.mode/bind/port` | `local` / `lan` / `18789`. Fresh volumes get `gateway.mode local` seeded once by setup |
| `browser.noSandbox` | required for Chromium in containers |
| `models.providers.9router` | `baseUrl` (`http://9router:20128/v1`), `apiKey` (`${NINE_ROUTER_API_KEY}` — bare `${VAR}` **is** supported and is what setup writes; it resolves from the container environment), `api: openai-completions`, `request.allowPrivateNetwork: true`, `models: [{id, name}]` for `jobclaw-free` |
| `agents.defaults.workspace` | `/home/node/.openclaw/workspace` |
| `agents.defaults.model.primary` | `9router/jobclaw-free` (combo name is the model id) |
| `agents.defaults.modelPolicy.allow` | refs the gateway may use — job `--model` overrides must be listed |

Conditional keys, derived from `.env` by `desired_config_for_env()`:

| Condition | Keys |
|---|---|
| Telegram enabled + allowlist | `channels.telegram.enabled: true`, `dmPolicy: "allowlist"`, `allowFrom: [<numeric user IDs>]` |
| Telegram enabled + pairing | `channels.telegram.enabled: true`, `dmPolicy: "pairing"`, `allowFrom: []` |
| Telegram disabled | `channels.telegram.enabled: false`, `allowFrom: []` |
| Tavily | `plugins.entries.tavily.enabled: true`, `tools.web.search.enabled: true`, `tools.web.search.provider: "tavily"` |
| DuckDuckGo | `plugins.entries.tavily.enabled: false`, `tools.web.search.enabled: true`, `tools.web.search.provider: "duckduckgo"` |
| Search disabled | `plugins.entries.tavily.enabled: false`, `tools.web.search.enabled: false` |

`commands.ownerAllowFrom` is **not** set automatically. Owners can opt in manually with the
gateway stopped (config writes require the offline setup service):

```bash
docker compose stop openclaw-gateway
docker compose run --rm -T openclaw-setup config set \
  commands.ownerAllowFrom '["telegram:<YOUR_USER_ID>"]'
docker compose up -d openclaw-gateway
```

## Services (`docker-compose.yml`)

| Service | Image / build | Ports | Volumes |
|---|---|---|---|
| `9router` | `${NINE_ROUTER_IMAGE}` (required), `DATA_DIR=/app/data`; healthcheck `GET /api/health` | `20128:20128` | named `9router-data` → `/app/data` |
| `openclaw-gateway` | built from `Dockerfile.gateway` with required build arg `OPENCLAW_BASE` (upstream + Chromium + RenderCV), stable `hostname: jobclaw-openclaw`; local tag `jobclaw-openclaw:latest` | `18789:18789` | `openclaw-home` → `/home/node/.openclaw`, `openclaw-workspace` bind → `/home/node/.openclaw/workspace`, `browser-profiles` → `/home/node/.openclaw/browser-profiles` |
| `openclaw-cli` | same locally built image, profile `cli`, `network_mode: service:openclaw-gateway`, entrypoint `node openclaw.mjs` | — | same home volume + workspace bind |
| `openclaw-setup` | same locally built image, profile `setup`, stable hostname; used by setup with the gateway stopped | — | same home volume + workspace bind |

Named volumes:

| Volume | Name | Contents |
|---|---|---|
| 9Router data | `jobclaw-9router-data` | providers, combos, API keys, settings, machine id, CLI secret, OAuth credentials, runtime module |
| OpenClaw home | `jobclaw-openclaw-home` | live config, sessions, pairing, state DB |
| Browser profiles | `jobclaw-browser-profiles` | persistent Chromium profiles |

Stable hostnames matter: OpenClaw ties state ownership to the writer identity. Recreate-happy
workflows and foreign-hostname CLI writes poison `state/openclaw.sqlite` ("ownership could not
be verified" crash loop). Prefer `docker compose exec` for runtime commands and the
stopped-gateway `openclaw-setup` service for config writes — see
[CLI cheatsheet](cli-cheatsheet.md) and [architecture](../explanation/architecture.md).

## Recreate vs restart

| Change | Action |
|---|---|
| Normal setup / repair | Run `python scripts/setup.py`; it stops the gateway, applies config, and recreates it automatically once |
| Config-only, gateway running | `python scripts/setup.py --one-shot` (stops, applies, starts again) |
| `.env` value changed outside setup | `docker compose up -d --force-recreate <service>` — `restart` does **not** reload environment |
| No config or env change | `docker compose restart <service>` is enough (9Router state is in its volume) |

Do not use manual `--force-recreate` as a substitute for setup. In particular, setup never
asks you to recreate the gateway by hand; the recreate is part of the flow.

## 9Router password and reset caveat

`INITIAL_PASSWORD` seeds login only when the volume has no stored password hash. On an
existing volume, change the password in the dashboard first, then update
`NINE_ROUTER_PASSWORD`. A plain `curl -X POST .../api/auth/reset-password` may be rejected by
9Router middleware (`403 Local only: CLI token required`); the supported recovery paths and
the destructive volume-removal fallback are documented in
[rotate secrets](../how-to/rotate-secrets.md). Setup never removes the volume.
