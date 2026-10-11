# Tutorial: getting started (A to Z)

Follow this page once, top to bottom. It takes roughly 30–45 minutes, most of it waiting on
downloads and dashboard clicks. By the end, job digests arrive in your Telegram every morning.

## 0. What you need before starting

- **Docker** 24+ with the Compose plugin: `docker --version` and `docker compose version`.
- A **Telegram** account.
- A free **Tavily** account (for web search): sign up at `tavily.com`, copy the API key
  from the dashboard (`tvly-...`, free tier is 1,000 credits/month).
- A **resume in Markdown** (`resume.md`). Keep passwords and ID numbers out of it — free
  model providers may log prompts (see [free-tier limits](../explanation/free-tier-limits.md)).
- Patience for first-time image pulls (1–2 GB).

> This system is **human-in-the-loop by design**: the agent finds, scores and drafts. YOU
> click Send in your own browser. Fully automatic applying violates LinkedIn/Indeed/Upwork
> terms and gets accounts permanently banned. Details in
> [free-tier limits](../explanation/free-tier-limits.md).

## 1. Clone and configure secrets

```bash
git clone https://github.com/oxcodexo/jobclaw.git jobclaw
cd jobclaw
cp .env.example .env
```

Edit `.env` (values come from later steps — fill in as you go):

| Variable | Where you get it |
|---|---|
| `OPENCLAW_GATEWAY_TOKEN` | invent a long random string |
| `TELEGRAM_BOT_TOKEN` | BotFather (step 4) |
| `TELEGRAM_ALLOWED_CHAT_IDS` | @userinfobot (step 4) |
| `NINE_ROUTER_PASSWORD` | invent a strong password (step 3) |
| `NINE_ROUTER_API_KEY` | 9Router dashboard endpoint key (step 3) |
| `TAVILY_API_KEY` | Tavily dashboard (prerequisite above) |
| `TZ` | your timezone, e.g. `Africa/Casablanca` |

Sanity check that secrets stay out of git (should print nothing tracked):

```bash
git status --porcelain
git check-ignore .env openclaw-workspace/resume.md data && echo "secrets ignored OK"
```

## 2. Start the stack

```bash
docker compose up -d
docker compose ps
```

First run pulls two images (`ghcr.io/openclaw/openclaw` + `decolua/9router`) and builds a
small Chromium layer for the gateway — this can take 5–10 minutes. Expected state:

```bash
docker compose ps
# jobclaw-9router    Up (healthy)   0.0.0.0:20128->20128/tcp
# jobclaw-openclaw   Up             0.0.0.0:18789->18789/tcp
```

Key URLs (all local):

| Service | URL |
|---|---|
| 9Router dashboard | http://127.0.0.1:20128 |
| OpenClaw Control UI | http://127.0.0.1:18789 |
| OpenClaw ↔ 9Router (internal) | http://9router:20128/v1 |

## 3. Wire free models in 9Router

Full walkthrough: [free models via 9Router](../how-to/free-models-9router.md). Short version:

1. Open http://127.0.0.1:20128, log in with `NINE_ROUTER_PASSWORD` from `.env`.
2. **Providers** → connect **Kiro AI** (OAuth via AWS Builder ID / Google / GitHub —
   ~50 credits/month free) and **OpenCode Free** (one click, no auth).
3. **Combo** → create `jobclaw-free`, add free models with the most reliable first
   (e.g. `oc/muse-spark-...`, then Kiro non-thinking models; keep `-thinking` variants last —
   they burn credits fast).
4. **Endpoint / API keys** → create key (e.g. name `openclaw`), copy it into `.env` as
   `NINE_ROUTER_API_KEY`.
5. Apply and verify the key answers:

```bash
docker compose up -d
curl -s -H "Authorization: Bearer $NINE_ROUTER_API_KEY" \
  http://127.0.0.1:20128/v1/models | head -c 400
```

## 4. Connect Telegram

Full walkthrough: [Telegram setup](../how-to/telegram-setup.md). Short version:

1. Chat with **@BotFather** → `/newbot` → save the token into `.env` as `TELEGRAM_BOT_TOKEN`.
2. Open `t.me/<your-bot>` → **Start**, send `hi`.
3. Get your numeric chat ID (message **@userinfobot**, or Bot API `getUpdates` on your own
   bot) → `.env` as `TELEGRAM_ALLOWED_CHAT_IDS`.
4. Restart the gateway, message the bot again, approve pairing:

```bash
docker compose restart openclaw-gateway
# (send any message to the bot first)
docker compose exec openclaw-gateway node dist/index.js pairing list telegram
docker compose exec openclaw-gateway node dist/index.js pairing approve telegram <CODE>
```

> Always run state-writing CLI commands with `docker compose exec` (same container identity).
> Separate CLI containers with random hostnames corrupt OpenClaw's state-ownership check —
> see [troubleshooting](#8-when-something-breaks).

## 5. Enable Tavily search

Full walkthrough: [Tavily search](../how-to/tavily-search.md). Short version (key already in
`.env`, plugin entry already in `config/openclaw.json`):

```bash
docker compose up -d --force-recreate openclaw-gateway
# wait ~60s for boot, then:
docker compose exec openclaw-gateway node dist/index.js plugins install @openclaw/tavily-plugin
docker compose exec openclaw-gateway node dist/index.js skills check | grep -i tavily
```

## 6. Drop in your resume and profile

1. Copy your resume to `openclaw-workspace/resume.md` (gitignored — never committed).
2. Fill `openclaw-workspace/USER.md` (replace the `YOUR_*` placeholders: roles, skills,
   location, salary floor, links, chat ID, timezone). The agent also infers from the resume.

## 7. Create the scheduled jobs

The repo's agent instructions (`openclaw-workspace/AGENTS.md`) describe the intended jobs.
Create them (times in `--tz`, adjust to yours):

```bash
EXE="docker compose exec -T openclaw-gateway node dist/index.js"
$EXE automations add --cron "0 7 * * *" --tz Africa/Casablanca \
  --message "Find new AI Engineer / Full-Stack postings (remote or Morocco) using tavily_search: 2 queries (basic, max 5 each) over Greenhouse/Lever boards. tavily_extract the best 4. Score 0-100 vs openclaw-workspace/resume.md, keep 70+. Write keepers to jobs/queue/YYYY-MM-DD-search-<slug>.md with score, why-fit, tailored cover letter. Skip URLs in jobs/applied.json. NEVER apply or submit." \
  --name "Jobs: AI remote search" --agent main \
  --announce --channel telegram --to <YOUR_CHAT_ID> --model 9router/jobclaw-free
```

Repeat for LinkedIn (`15 7 * * *`, `site:linkedin.com/jobs` snippets) and Upwork
(`30 7 * * *`, `site:upwork.com` gigs, never submit), plus an evening digest
(`0 18 * * 1-5`). See [daily workflow](../how-to/daily-workflow.md) for the full prompts.

## 8. Test end-to-end, then go live

```bash
# run the morning job right now and wait for the result:
docker compose exec -T openclaw-gateway node dist/index.js automations run <JOB_ID> \
  --wait --wait-timeout 12m --poll-interval 5s
ls openclaw-workspace/jobs/queue/
```

You should get a Telegram digest plus draft files in `jobs/queue/`. Review a draft, apply
from your own browser, and tell the bot what you sent so it stays tracked.

## 9. When something breaks

- `docker compose ps` + `docker compose logs --tail 30 openclaw-gateway` first.
- `error lines` hunt: `docker compose logs --since 10m openclaw-gateway | grep -iE "could not be verified|Failing check|failed to start|invalid"`.
- State-ownership errors after running CLI from another container: stop the gateway, run
  management commands only via `docker compose exec`, restart. Full story:
  [architecture](../explanation/architecture.md).

## Next steps

- [Daily workflow](../how-to/daily-workflow.md) — how to live with the system.
- [Configuration reference](../reference/configuration.md) — every knob.
- [Free-tier limits](../explanation/free-tier-limits.md) — quotas and ban risks you must know.
