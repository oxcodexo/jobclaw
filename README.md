# Work Agent Finder

A self-hosted AI job finder: **OpenClaw** agent + **9Router** free-model routing + **Tavily**
search + **Telegram** digests, all in Docker. It finds postings, scores them against your
resume, and drafts tailored cover letters — and it **never applies on your behalf**
(human-in-the-loop; auto-applying gets accounts banned — see
[free-tier limits](docs/explanation/free-tier-limits.md)).

## How it works (30 seconds)

Morning cron jobs search AI/full-stack postings (Greenhouse/Lever boards, LinkedIn and
Upwork snippets), extract descriptions, score 0–100 vs your `resume.md`, and queue drafts
to `jobs/queue/` with why-fit notes. Digests land in Telegram. You review, you click Send
in your own browser, you tell the bot what went out.

## Quickstart

```bash
git clone <YOUR-REPO-URL> work-agent-finder && cd work-agent-finder
cp .env.example .env   # then fill secrets (see below)
docker compose up -d
```

Full A-to-Z path: **[docs/tutorials/getting-started.md](docs/tutorials/getting-started.md)**.
Start there — this README is the map, the tutorial is the road.

## What you need (free tiers)

- Docker 24+ with Compose
- Telegram account (bot via BotFather — free)
- 9Router free providers: Kiro AI (~50 credits/mo) + OpenCode Free (see
  [free models](docs/how-to/free-models-9router.md))
- Tavily key (1,000 free credits/mo — see [Tavily setup](docs/how-to/tavily-search.md))
- Your resume as `resume.md` (gitignored, never committed)

## Docs

| | |
|---|---|
| [Documentation map](docs/README.md) | Diátaxis-structured index |
| [Getting started](docs/tutorials/getting-started.md) | complete first-run tutorial |
| [Configuration](docs/reference/configuration.md) | every knob |
| [CLI cheatsheet](docs/reference/cli-cheatsheet.md) | every command |
| [Architecture](docs/explanation/architecture.md) | why it's built this way |
| [Daily workflow](docs/how-to/daily-workflow.md) | living with the system |

## Safety rules (non-negotiable)

1. `.env`, `data/`, `resume.md`, queue drafts and `applied.json` are gitignored — verify
   with `git status` before every commit.
2. The agent drafts only. (See [platform risks](docs/explanation/free-tier-limits.md).)
3. Free models may log prompts — keep IDs/passwords out of `resume.md`.

## Contributing

Issues and PRs welcome. Keep docs in their Diátaxis lane (tutorials/how-to/reference/
explanation), keep secrets out of examples, and update the cheatsheet when you add a
command. License: TBD by the maintainer (no license file yet — all rights reserved by
default until one is added).
