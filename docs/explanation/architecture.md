# Explanation: architecture

## The pieces

```text
You (webchat/Telegram)  <──►  OpenClaw gateway (:18789)  ──►  9Router (:20128)  ──►  free models
   │                        │                              │
   │                        │ chat-first                     │ combo: OC-free first,
   │                        │ skills: tavily, browser,     │ fallback second
   │                        ▼                              ▼
   │                   jobs/queue/*.md               Tavily API (search/extract)
   │                   jobs/applied.json
   ▼
You (host Firefox) — the only place Apply/Send is ever clicked
```

- **OpenClaw gateway** is the agent runtime: chat channels, tool surface
  (57+ tools), skills, SQLite state. It owns all decisions; it never submits applications.
- **9Router** is a local model router, not an LLM. One OpenAI-compatible endpoint, provider
  combos with fallback, per-endpoint API keys. The combo name *is* the model id
  (`jobclaw-free`).
- **Webchat + Telegram** are the channels: you chat, JobClaw answers.
- **Tavily** is the discovery backbone: `tavily_search` (basic, ≤5) finds postings,
  `tavily_extract` reads them server-side — including JS-rendered pages the container
  browser cannot reach.
- **RenderCV** (baked into the gateway image) renders tailored resume PDFs from YAML.

## Why search-first (the key design decision)

Headless Chromium from server IPs is bot-walled on all three target boards (verified:
Indeed Cloudflare 403, LinkedIn login wall, Upwork challenge page). Chasing stealth is an
arms race that burns free-tier credits at ~50k tokens per failed run. So:

1. Discovery via search API + public ATS boards (Greenhouse/Lever/Workable JSON).
2. Snippet/extract-only for hostile boards; full reads happen in the user's own browser.
3. Container Chromium kept as fallback for bot-friendly pages only.

## Interaction model

Chat-first: every task starts from a user message in webchat or
Telegram. Scopes stay small per turn (≤3 searches, ≤8 postings, capped text
reads) because free models bill attention in tokens. Tracking files
(`jobs/queue/`, `jobs/applied.json`) are the persistent memory across
ephemeral chat sessions.

## Rules baked into this repo

- **State ownership.** Manage the gateway only via `docker compose exec` (same
  container) or the `openclaw-setup` one-shot service (stable hostname) —
  random-hostname writers corrupt the state check.
- **Config.** Doctor owns the live copy (migrations, `meta.*`, skills state).
  Project keys go in via `python scripts/setup.py`, single tweaks via
  `config set`. Never edit the live copy by hand, never mount `openclaw.json`
  as a file.
- **Volumes.** `/home/node/.openclaw` and browser profiles are named volumes
  (Windows binds break Doctor); workspace stays bind-mounted (plain markdown).
- **Env needs recreate.** `docker compose restart` does not reload environment;
  use `up -d --force-recreate <service>`.
