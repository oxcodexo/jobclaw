# Tutorial: getting started (A to Z)

Follow this page once, top to bottom. It takes roughly 30–45 minutes, most of it waiting on
downloads. By the end, JobClaw answers in the OpenClaw Control UI and, if you enabled it,
Telegram.

## 0. What you need before starting

- **Docker** 24+ with the Compose plugin: `docker --version` and `docker compose version`.
- **Python** 3.9+ (`python --version`; on some systems the command is `python3`).
- A **resume as RenderCV YAML** (`resume.yaml`). Keep passwords and ID numbers out of it — free
  model providers may log prompts (see [free-tier limits](../explanation/free-tier-limits.md)).
- Optional: a **Telegram** account and a **Tavily** key (`tvly-...`, 1,000 free credits/month).
  Setup can leave either or both disabled; you can enable them later by rerunning setup.
- Patience for first-time image pulls (1–2 GB).

> This system is **human-in-the-loop by design**: the agent finds, scores and drafts. YOU
> click Send in your own browser. Fully automatic applying violates LinkedIn/Indeed/Upwork
> terms and gets accounts permanently banned. Details in
> [free-tier limits](../explanation/free-tier-limits.md).

## 1. Clone and run guided setup

```bash
git clone https://github.com/oxcodexo/jobclaw.git jobclaw
cd jobclaw
python scripts/setup.py
```

You do **not** need to copy or hand-edit `.env` first. Setup creates it from `.env.example`,
generates the gateway token and 9Router password when they are placeholders, and preserves
comments and existing values on later runs.

Setup walks you through:

1. **Stack version.** Two supported presets only:
   - **Validated** (default, recommended): OpenClaw `2026.9.9` + 9Router `0.5.104`.
   - **Latest**: the newest stable upstream pair with published images.
2. **Telegram (optional).** Allowlist with numeric user IDs (recommended), pairing, or
   disabled. Setup writes the channel config; you never edit `openclaw.json`.
3. **Web search (optional).** Tavily, key-free DuckDuckGo (experimental), or disabled. Setup
   installs the matching plugin when needed.

Then it performs the rest automatically:

- builds the gateway image (upstream OpenClaw + Chromium + RenderCV),
- starts 9Router on the named volume `jobclaw-9router-data`,
- logs in to 9Router, creates or reuses the `jobclaw` API key, and writes it to `.env`,
- probes the no-auth OpenCode models and creates the `jobclaw-free` combo,
- stops the gateway, seeds/applies the OpenClaw config, installs the selected search plugin,
- recreates the gateway once and waits for `gateway ready`,
- runs a real `9router/jobclaw-free` inference smoke test.

Same commands work on PowerShell, CMD, Git Bash, macOS, and Linux. Useful variants:

```bash
python scripts/setup.py --check            # drift vs desired keys, no writes
python scripts/setup.py --check-versions   # current / validated / latest + image availability
python scripts/setup.py --verify           # per-member chat probe of the 9Router combo
python scripts/setup.py --latest           # preselect Latest (confirms interactively)
python scripts/setup.py --yes              # accept defaults, keep integrations, no prompts
python scripts/setup.py --offline          # skip version metadata network calls
```

Expected state afterwards:

```bash
docker compose ps
# jobclaw-9router    Up (healthy)   0.0.0.0:20128->20128/tcp
# jobclaw-openclaw   Up             0.0.0.0:18789->18789/tcp
```

| Storage | What lives there |
|---|---|
| `jobclaw-openclaw-home` | OpenClaw state, live config, sessions, pairing |
| `jobclaw-browser-profiles` | persistent Chromium profiles |
| `jobclaw-9router-data` | 9Router DB: providers, combos, API keys, settings |
| `openclaw-workspace/` (bind) | tracked prompts plus your resume, queue and applied log |

Key URLs (all local):

| Service | URL |
|---|---|
| 9Router dashboard | http://127.0.0.1:20128 |
| OpenClaw Control UI | http://127.0.0.1:18789 |
| OpenClaw ↔ 9Router (internal) | http://9router:20128/v1 |

## 2. Prove the install

```bash
python scripts/setup.py --check      # every desired key should say OK
python scripts/setup.py --verify     # each combo member must answer a tiny chat call
```

`--check` compares `.env`-derived desired config against the live volume. `--verify` logs in to
9Router, reads the `jobclaw-free` combo, and sends a real chat request to each member. It also
reads `/v1/models`, but that listing is advisory because it can lag new OpenCode slugs; a model
that merely appears there is not proof.

## 3. Optional: Kiro fallback

The default free lane needs no provider account. If you want a second pool:

1. Open http://127.0.0.1:20128 and log in with `NINE_ROUTER_PASSWORD` from `.env`.
2. **Providers** → **Kiro AI** → OAuth with AWS Builder ID (free), Google, or GitHub
   (≈50 credits/month). Tool calls through Kiro can be flaky.
3. If you add Kiro models to `jobclaw-free`, verify each one and put the most reliable first.
   Keep `-thinking` variants last; they burn credits fast.

Credentials persist in `jobclaw-9router-data`: restarts and recreates never require OAuth
again.

## 4. Optional: Telegram

Setup already wrote the Telegram config if you chose allowlist or pairing. If you skipped it,
rerun `python scripts/setup.py` and keep the defaults you want.

1. **@BotFather** → `/newbot` → save the token.
2. Open `t.me/<your-bot>` → **Start**, send `hi`.
3. Get your **numeric user ID** (message **@userinfobot**, or Bot API `getUpdates` on your own
   bot). That is the ID of a person allowed to DM the bot; setup asks for user IDs, not group/chat
   IDs.
4. Rerun setup. For allowlist mode, message the bot from an allowed account. For pairing mode,
   approve the first DM:

```bash
docker compose exec openclaw-gateway node openclaw.mjs pairing list telegram
docker compose exec openclaw-gateway node openclaw.mjs pairing approve telegram <CODE>
```

Full walkthrough, including failure modes: [Telegram setup](../how-to/telegram-setup.md).

## 5. Optional: web search

Tavily is the reliable discovery path; DuckDuckGo is experimental, and disabled search stays
explicit. Rerun `python scripts/setup.py` to change the choice. Setup installs the plugin and
applies the conditional search keys; if the plugin install fails, setup prints the exact retry
command and exits non-zero without rolling back the stack.

Verify the plugin is visible:

```bash
docker compose exec openclaw-gateway node openclaw.mjs skills check | grep -i tavily
```

More: [Tavily search](../how-to/tavily-search.md).

## 6. Drop in your resume and profile

1. Get your resume into `openclaw-workspace/resume.yaml` (gitignored — never committed). Three
   ways, pick one:
   - Copy your RenderCV master (or start from `resume.yaml.example`), or
   - Ask JobClaw in chat: *"here's my resume"* + upload (PDF, DOCX, TXT, MD, YAML) — it reads
     the file and builds `resume.yaml` for you, or
   - Paste your resume text in chat and ask it to structure it.
2. Fill `openclaw-workspace/USER.md` (replace the `YOUR_*` placeholders: roles, skills,
   location, salary floor, links, timezone). The agent also infers from the resume.

## 7. Chat with JobClaw (everything is on demand)

Open the Control UI (`http://127.0.0.1:18789`) or Telegram and talk to the agent. Start with:

- *"Find new AI Engineer / Full-Stack postings, remote or Morocco, posted within 7 days."* —
  deep search with posting-date evidence, keepers (70+) queued to `jobs/queue/` with score,
  why-fit, tailored cover letter.
- *"Tailor my resume for <job URL>."* — JD analysis, tailored `resume.yaml` + PDF beside the
  queue draft, marked draft until you approve.
- *"Cover letter for <job>"*, *"interview prep for <job>"*, *"digest"* (queue summary),
  *"log applied <job>"*.
- Paste any job URL anytime: *"Score this and draft a cover letter."*

See [daily workflow](../how-to/daily-workflow.md) for all flows.

## 8. Test end-to-end, then go live

Ask for a fresh search in chat, then check the queue:

```bash
ls openclaw-workspace/jobs/queue/
```

You should get drafts in `jobs/queue/` (plus tailored resume PDFs beside them). Review a draft,
apply from your own browser, and tell the bot what you sent so it stays tracked.

## 9. When something breaks

- `docker compose ps` + `docker compose logs --tail 30 openclaw-gateway` first.
- `python scripts/setup.py --check` (config drift) and `--verify` (inference path).
- `python scripts/setup.py` repairs setup-owned state idempotently: it reuses an existing
  `jobclaw` key/combo and only fills a missing or empty combo.
- 9Router login reset and destructive fallbacks: [rotate secrets](../how-to/rotate-secrets.md).
- Do not run `--force-recreate` by hand as a first response. Setup handles the gateway
  recreate automatically; see [configuration](../reference/configuration.md) for when a
  manual recreate is actually needed.

## Next steps

- [Daily workflow](../how-to/daily-workflow.md) — how to live with the system.
- [Configuration reference](../reference/configuration.md) — every knob.
- [Update and back up](../how-to/update.md) — presets, volume backups, downgrade caveats.
- [Free-tier limits](../explanation/free-tier-limits.md) — quotas and ban risks you must know.
