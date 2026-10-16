# Reference: project structure

```text
jobclaw/
├── docker-compose.yml        # 9router + openclaw-gateway (+ cli profile); all mounts
├── Dockerfile.gateway        # upstream OpenClaw + headless Chromium layer
├── .env                      # YOUR secrets (gitignored — copy from .env.example)
├── .env.example              # placeholder vars for new clones
├── scripts/
│   ├── setup.py              # cross-platform setup (build, seed, apply, verify; --check/--verify/--check-versions)
│   ├── desired-config.json   # desired live keys -> openclaw-home volume (additive, idempotent)
│   └── check-queue.sh        # queue-depth probe for --command cron jobs
├── openclaw-workspace/       # bind-mounted as the agent workspace
│   ├── AGENTS.md             # agent operating instructions (injected every session)
│   ├── SOUL.md / IDENTITY.md # persona
│   ├── USER.md               # YOUR profile (placeholders in template)
│   ├── MEMORY.md             # long-term memory seed
│   ├── resume.md             # YOUR resume (gitignored — you create it)
│   ├── resume.example.md     # shape reference
│   └── jobs/
│       ├── queue/            # drafts (gitignored runtime state)
│       ├── applied.json      # sent URLs (gitignored runtime state)
│       └── logs/             # run logs (gitignored)
├── data/                     # gitignored runtime state
│   ├── 9router-data/         # 9Router db, live bind (combos, keys, quota)
│   ├── openclaw-home/        # LEGACY pre-volume copy (unused since volume migration — see update.md)
│   └── browser-profiles/     # LEGACY pre-volume copy (unused since volume migration)
└── docs/                     # this documentation (Diátaxis layout)
```

## Mount logic (why it looks like this)

- **Live config, no tracked copy.** The gateway only reads `openclaw.json` inside the
  `openclaw-home` named volume, which OpenClaw's doctor rewrites (migrations, backups).
  Project keys are applied additively via `python scripts/setup.py` (desired key set in
  `scripts/desired-config.json`, `--check` shows drift); single tweaks go through `config set`. There is intentionally no tracked
  config file — full-file syncs clobber Doctor-managed keys (`wizard/meta/skills/owner`).
  Never edit the live copy by hand.
- **Why `openclaw.json` is never mounted in.** Only named volume + `config set`
  keeps the live file consistent. Never edit it by hand.
- **Named volumes for state.** `openclaw-home` (`jobclaw-openclaw-home`) and
  `browser-profiles` are named volumes. Inspect with
  `docker compose exec openclaw-gateway sh -c 'ls -la /home/node/.openclaw'`.
  Back up with `docker run --volumes-from` (see [update](../how-to/update.md)).
- **Workspace is live *and* tracked.** `openclaw-workspace/` holds both versioned prompt
  files (`AGENTS.md`, …) and your private runtime (`resume.md`, queue, applied log).
  `.gitignore` draws the line — check it after any change.
- **`data/` is entirely gitignored.** It contains credentials, sessions, and SQLite state.
  Back it up encrypted, never commit it.
- **Runtime names match the repo**: containers `jobclaw-9router` / `jobclaw-openclaw`,
  network `jobclaw-net`, image `jobclaw-openclaw:latest`, hostnames likewise. Stable
  hostnames matter — OpenClaw attests state to writer identity (see
  [architecture](architecture.md)).
