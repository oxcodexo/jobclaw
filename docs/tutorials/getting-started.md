# Tutorial: getting started (A to Z)

Follow this page once, top to bottom. It takes roughly 30–45 minutes, most of it waiting on
downloads and dashboard clicks. By the end, job digests arrive in your Telegram every morning.

## 0. What you need before starting

- **Docker** 24+ with the Compose plugin: `docker --version` and `docker compose version`.
- A **Telegram** account.
- A free **Tavily** account (for web search): sign up at `tavily.com`, copy the API key
  from the dashboard (`tvly-...`, free tier is 1,000 credits/month).
- A **resume as RenderCV YAML** (`resume.yaml`). Keep passwords and ID numbers out of it — free
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
git check-ignore .env openclaw-workspace/resume.yaml data && echo "secrets ignored OK"
```

## 2. Start the stack (one command)

Same command on PowerShell, CMD, Git Bash, macOS, Linux (needs Python 3.9+,
Docker 24+ with the Compose plugin). First run pulls images and builds a small
Chromium layer — 5–10 minutes, mostly waiting. The script also creates `.env`
from `.env.example` (random tokens), checks upstream versions, seeds
`gateway.mode` on fresh volumes, waits for `gateway ready`, applies the project
config, and restarts:

```bash
python scripts/setup.py
```

Preview without writes, or check version pins against upstream:

```bash
python scripts/setup.py --check            # drift vs desired keys, no writes
python scripts/setup.py --check-versions   # pinned vs newest 9Router/OpenClaw, no writes
```

It also creates two named volumes (`jobclaw-openclaw-home`,
`jobclaw-browser-profiles`) — runtime home lives there, not in `./data/`.
Expected state afterwards:

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
   (Kiro non-thinking models if OpenCode Free 403s for you — verify each member
   answers a real chat call, not just appears in `/v1/models`; details in the
   [full walkthrough](../how-to/free-models-9router.md#3-build-the-combo-combo-page)).
   Keep `-thinking` variants last — they burn credits fast.
4. **Endpoint / API keys** → create key (e.g. name `openclaw`), copy it into `.env` as
   `NINE_ROUTER_API_KEY` (replacing the `placeholder-change-me...` boot value).
5. Apply and prove inference (listing is not proof — each member must answer):

```bash
docker compose up -d --force-recreate openclaw-gateway   # .env changed: recreate, not restart
python scripts/setup.py --verify
```

## 4. Connect Telegram

Full walkthrough: [Telegram setup](../how-to/telegram-setup.md). Short version:

1. Chat with **@BotFather** → `/newbot` → save the token into `.env` as `TELEGRAM_BOT_TOKEN`.
2. Open `t.me/<your-bot>` → **Start**, send `hi`.
3. Get your numeric chat ID (message **@userinfobot**, or Bot API `getUpdates` on your own
   bot) → `.env` as `TELEGRAM_ALLOWED_CHAT_IDS`.
4. Recreate the gateway (`.env` changed — plain `restart` would keep the old
   environment), message the bot again, approve pairing:

```bash
docker compose up -d --force-recreate openclaw-gateway
# (send any message to the bot first)
docker compose exec openclaw-gateway node openclaw.mjs pairing list telegram
docker compose exec openclaw-gateway node openclaw.mjs pairing approve telegram <CODE>
```

> Run state-changing CLI commands with `docker compose exec` (same container).
> Rule of thumb: `.env` changed → `up -d --force-recreate`; config changed →
> `restart`; neither works → `ps` + `logs --tail 30` first.

## 5. Enable Tavily search

Full walkthrough: [Tavily search](../how-to/tavily-search.md). Short version (key already in
`.env`, plugin entry applied by `python scripts/setup.py`):

```bash
docker compose up -d --force-recreate openclaw-gateway
# wait ~60s for boot, then:
docker compose exec openclaw-gateway node openclaw.mjs plugins install @openclaw/tavily-plugin
docker compose exec openclaw-gateway node openclaw.mjs skills check | grep -i tavily
```

## 6. Drop in your resume and profile

1. Get your resume into `openclaw-workspace/resume.yaml` (gitignored — never
   committed). Three ways, pick one:
   - Copy your RenderCV master (or start from `resume.yaml.example`), or
   - Ask JobClaw in chat: *"here's my resume"* + upload (PDF, DOCX, TXT, MD,
     YAML) — it reads the file and builds `resume.yaml` for you, or
   - Paste your resume text in chat and ask it to structure it.
2. Fill `openclaw-workspace/USER.md` (replace the `YOUR_*` placeholders: roles, skills,
   location, salary floor, links, timezone). The agent also infers from the resume.

## 7. Chat with JobClaw (everything is on demand)

Open the Control UI (`http://127.0.0.1:18789`) or Telegram and talk to the
agent. Start with:

- *"Find new AI Engineer / Full-Stack postings, remote or Morocco, posted
  within 7 days."* — deep search with posting-date evidence, keepers
  (70+) queued to `jobs/queue/` with score, why-fit, tailored cover letter.
- *"Tailor my resume for <job URL>."* — JD analysis, tailored `resume.yaml`
  + PDF beside the queue draft, marked draft until you approve.
- *"Cover letter for <job>"*, *"interview prep for <job>"*,
  *"digest"* (queue summary), *"log applied <job>"*.
- Paste any job URL anytime: *"Score this and draft a cover letter."*

See [daily workflow](../how-to/daily-workflow.md) for all flows.

## 8. Test end-to-end, then go live

Ask for a fresh search in chat, then check the queue:

```bash
ls openclaw-workspace/jobs/queue/
```

You should get drafts in `jobs/queue/` (plus tailored resume PDFs beside
them). Review a draft, apply from your own browser, and tell the bot what
you sent so it stays tracked.

## 9. When something breaks

- `docker compose ps` + `docker compose logs --tail 30 openclaw-gateway` first.
- `python scripts/setup.py --check` (config drift) and `--verify` (inference path).

## Next steps

- [Daily workflow](../how-to/daily-workflow.md) — how to live with the system.
- [Configuration reference](../reference/configuration.md) — every knob.
- [Free-tier limits](../explanation/free-tier-limits.md) — quotas and ban risks you must know.
