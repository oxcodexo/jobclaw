# Documentation map

This documentation follows the [Diátaxis](https://diataxis.fr) framework: each page has one job.
Start with the tutorial; use how-to guides for specific tasks; check reference for exact
syntax; read explanations to understand *why* the system is built this way.

## Tutorials (learn by doing)

- [Getting started](tutorials/getting-started.md) — the full A-to-Z path: clone, configure,
  start the stack, connect Telegram, wire free models, run your first job scan. Follow it once,
  in order.

## How-to guides (specific goals)

- [Set up Telegram](how-to/telegram-setup.md) — BotFather, chat ID, pairing approval.
- [Wire free models via 9Router](how-to/free-models-9router.md) — dashboard: providers, combo,
  endpoint key.
- [Enable Tavily web search](how-to/tavily-search.md) — API key, plugin install, verification.
- [Daily workflow](how-to/daily-workflow.md) — review queue, apply from your browser, track sends,
  paste links on demand.
- [Rotate or revoke secrets](how-to/rotate-secrets.md) — what to do when a token leaks.
- [Update and back up](how-to/update.md) — pull new images, back up state, restore.

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
