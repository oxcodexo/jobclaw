# Reference: project structure

```text
jobclaw/
├── docker-compose.yml        # 9router + openclaw-gateway (+ cli/setup profiles); all mounts
├── Dockerfile.gateway        # upstream OpenClaw + headless Chromium + RenderCV layer
├── .env                      # YOUR secrets and setup markers (gitignored — created by setup)
├── .env.example              # safe template and Validated version pair
├── scripts/
│   ├── setup.py              # guided setup: versions, integrations, 9Router bootstrap,
│   │                         # config apply/recreate, --check/--verify/--check-versions
│   └── desired-config.json   # always-on live keys (conditional keys come from .env)
├── openclaw-workspace/       # bind-mounted as the agent workspace
│   ├── AGENTS.md             # agent operating instructions (injected every session)
│   ├── SOUL.md / IDENTITY.md # persona
│   ├── USER.md               # YOUR profile (placeholders in template)
│   ├── MEMORY.md             # long-term memory seed
│   ├── resume.yaml           # YOUR working master, RenderCV (gitignored — copy from resume.yaml.example)
│   ├── resume.yaml.example   # sanitized shape reference
│   ├── skills/               # agent skills (rendercv + career suite, versioned)
│   └── jobs/
│       ├── queue/            # drafts (gitignored runtime state)
│       ├── applied.json      # sent URLs (gitignored runtime state)
│       └── logs/             # run logs (gitignored)
└── docs/                     # this documentation (Diátaxis layout)
```

## Named volumes (runtime state lives here, not in the repo)

| Volume | Mount | Contents |
|---|---|---|
| `jobclaw-openclaw-home` | `/home/node/.openclaw` | live `openclaw.json`, sessions, pairing, state DB, OpenClaw skills state |
| `jobclaw-browser-profiles` | `/home/node/.openclaw/browser-profiles` | persistent Chromium profiles |
| `jobclaw-9router-data` | `/app/data` | 9Router database: providers, combos, endpoint keys, settings, machine id, CLI secret, OAuth credentials, runtime module |

Inspect the 9Router volume:

```bash
docker compose exec 9router sh -c 'ls -la /app/data'
```

Back up volumes with the commands in [update](../how-to/update.md).

## Mount logic (why it looks like this)

- **Live config, no tracked copy.** The gateway reads `openclaw.json` from the
  `openclaw-home` volume, and OpenClaw's doctor rewrites it (migrations, backups). Project
  keys are applied additively through `python scripts/setup.py` (always-on keys in
  `scripts/desired-config.json`; Telegram/search keys derived from `.env`); `--check` shows
  drift. Single tweaks go through `config set`. Never edit the live copy by hand.
- **Why `openclaw.json` is never mounted in.** Only the named volume plus `config set` keeps
  the live file consistent with Doctor state.
- **Named volumes for runtime state.** This is required on Windows, where bind-mounted state
  breaks Doctor, and it keeps SQLite/OAuth state off the tracked tree.
- **Workspace is live *and* tracked.** `openclaw-workspace/` holds both versioned prompt files
  (`AGENTS.md`, …) and your private runtime (`resume.yaml`, queue, applied log). `.gitignore`
  draws the line — check it after any change.
- **Runtime names match the repo**: containers `jobclaw-9router` / `jobclaw-openclaw`, network
  `jobclaw-net`, image `jobclaw-openclaw:latest`, hostnames likewise. Stable hostnames matter
  — OpenClaw attests state to writer identity (see [architecture](architecture.md)).
