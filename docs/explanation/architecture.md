# Explanation: architecture

## The pieces

```text
You (Telegram)  <──►  OpenClaw gateway (:18789)  ──►  9Router (:20128)  ──►  free models
   │                        │                              │
   │                        │ cron (7:00/7:15/7:30, 18:00) │ combo: OC-free first,
   │                        │ skills: tavily, browser      │ Kiro fallback
   │                        ▼                              ▼
   │                   jobs/queue/*.md               Tavily API (search/extract)
   │                   jobs/applied.json
   ▼
You (host Firefox) — the only place Apply/Send is ever clicked
```

- **OpenClaw gateway** is the agent runtime: chat channels, cron scheduler, tool surface
  (57+ tools), skills, SQLite state. It owns all decisions; it never submits applications.
- **9Router** is a local model router, not an LLM. One OpenAI-compatible endpoint, provider
  combos with fallback, per-endpoint API keys. The combo name *is* the model id
  (`jobfinder-free`).
- **Telegram** is the only channel: digests out, links and pairing in, owner commands optional.
- **Tavily** is the discovery backbone: `tavily_search` (basic, ≤5) finds postings,
  `tavily_extract` reads them server-side — including JS-rendered pages the container
  browser cannot reach.

## Why search-first (the key design decision)

Headless Chromium from server IPs is bot-walled on all three target boards (verified:
Indeed Cloudflare 403, LinkedIn login wall, Upwork challenge page). Chasing stealth is an
arms race that burns free-tier credits at ~50k tokens per failed run. So:

1. Discovery via search API + public ATS boards (Greenhouse/Lever/Workable JSON).
2. Snippet/extract-only for hostile boards; full reads happen in the user's own browser.
3. Container Chromium kept as fallback for bot-friendly pages only.

## Cron model

Three morning scan jobs + one evening digest, all `--agent main`, explicit
`--announce --channel telegram --to <CHAT_ID>` delivery (implicit `channel: last` routing
is refused for isolated runs), `--tz` set to the user's zone. Prompts cap scope
(≤3 searches, ≤8 postings, capped text reads) because free models bill attention in tokens.

## Operational lessons baked into this repo

- **State ownership.** OpenClaw attests `state/openclaw.sqlite` to the writer identity.
  Stable container `hostname:` + management exclusively via `docker compose exec` (same
  container) keeps it clean. One-shot CLI containers with random hostnames poison it into
  a crash loop (`could not be verified`); recovery is stop → move `state/` aside → boot
  fresh → re-pair. Details in [configuration](configuration.md).
- **Config migrations.** Doctor rewrites the live config across versions
  (`models` → `modelPolicy.allow`, provider schema `models.providers.*`). Keep the tracked
  base current; read doctor blocks after every update.
- **File mounts vs rewrites.** Never bind-mount `openclaw.json` as a file — atomic
  renames fail with `EBUSY`. Seed via `sync-config.sh` instead.
- **Env needs recreate.** `docker compose restart` does not reload environment; use
  `up -d --force-recreate <service>`.
