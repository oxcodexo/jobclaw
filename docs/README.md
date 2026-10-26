# Documentation map

This documentation follows the [Diátaxis](https://diataxis.fr) framework: each page has one job.
Start with the tutorial; use how-to guides for specific tasks; check reference for exact
syntax; read explanations to understand *why* the system is built this way.

## Tutorials (learn by doing)

- [Getting started](tutorials/getting-started.md) — the full A-to-Z path: clone, run guided
  setup, optionally connect Telegram and web search, run your first job scan. Follow it once,
  in order.

## How-to guides (specific goals)

- [Set up Telegram](how-to/telegram-setup.md) — optional; BotFather, numeric user IDs,
  allowlist vs pairing.
- [Wire free models via 9Router](how-to/free-models-9router.md) — automatic key/combo
  provisioning, named-volume persistence, verification, troubleshooting.
- [Enable Tavily web search](how-to/tavily-search.md) — optional; API key, automatic plugin
  install, verification, DuckDuckGo/disabled alternatives.
- [Daily workflow](how-to/daily-workflow.md) — review queue, apply from your browser, track sends,
  paste links on demand.
- [Rotate or revoke secrets](how-to/rotate-secrets.md) — what to do when a token leaks.
- [Update and back up](how-to/update.md) — choose a preset, back up volumes, restore.

## Reference (exact facts)

- [Configuration](reference/configuration.md) — `.env` variables, live config keys,
  services, volumes, ports.
- [CLI cheatsheet](reference/cli-cheatsheet.md) — every command used to operate the stack.
- [Project structure](reference/project-structure.md) — what each file and folder is for.

## Explanation (understanding)

- [Architecture](explanation/architecture.md) — how OpenClaw, 9Router, models, chat channels
  and skills fit together, and why discovery is search-first.
- [Free-tier limits and platform risks](explanation/free-tier-limits.md) — quotas, token burn,
  logging caveats, and why auto-applying gets accounts banned.

## Conventions used in these docs

- Commands run from the repo root unless stated otherwise.
- `<PLACEHOLDERS>` in angle brackets are values you supply.
- `your-bot` means your Telegram bot username.
- Secrets go in `.env` (never committed) — never paste tokens in chats, issues, or logs.
