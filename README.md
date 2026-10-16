# JobClaw

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A self-hosted AI career expert: **OpenClaw** agent + **9Router** free-model routing + **Tavily**
search + **RenderCV** resume builds + **Telegram** chat, all in Docker. It finds new postings,
scores them against your resume, tailors your resume per job as PDF, and drafts cover
letters — and it **never applies on your behalf**
(human-in-the-loop; auto-applying gets accounts banned — see
[free-tier limits](docs/explanation/free-tier-limits.md)).

## How it works (30 seconds)

Chat with JobClaw from the web UI or Telegram: it finds new postings
(Greenhouse/Lever boards, LinkedIn and Upwork snippets — always with
posting-date evidence), extracts descriptions, scores 0–100 vs your
`resume.yaml`, tailors your resume per job (RenderCV PDF), and drafts cover
letters. Digests come on demand (`digest`). You review, you click Send
in your own browser, you tell the bot what went out.

## Quickstart

```bash
git clone https://github.com/oxcodexo/jobclaw.git jobclaw && cd jobclaw
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
- Your resume as RenderCV YAML (`openclaw-workspace/resume.yaml`, gitignored, never committed —
  copy your master or start from `resume.yaml.example`)

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

1. `.env`, `data/`, `resume.yaml`, queue drafts and `applied.json` are gitignored — verify
   with `git status` before every commit.
2. The agent drafts only. (See [platform risks](docs/explanation/free-tier-limits.md).)
3. Free models may log prompts — keep IDs/passwords out of `resume.yaml`.

## Contributing

Issues and PRs welcome. Keep docs in their Diátaxis lane (tutorials/how-to/reference/
explanation), keep secrets out of examples, and update the cheatsheet when you add a
command.

## License

MIT — see [LICENSE](LICENSE).
