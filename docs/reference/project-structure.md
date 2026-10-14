# Reference: project structure

```text
jobclaw/
├── docker-compose.yml        # 9router + openclaw-gateway (+ cli profile); all mounts
├── Dockerfile.gateway        # upstream OpenClaw + headless Chromium layer
├── .env                      # YOUR secrets (gitignored — copy from .env.example)
├── .env.example              # placeholder vars for new clones
├── config/
│   └── openclaw.json         # TRACKED base config (no secrets); seeds the live copy
├── scripts/
│   ├── sync-config.sh        # config/openclaw.json -> openclaw-home volume
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
├── data/                     # gitignored runtime state (9Router DB; legacy openclaw-home binds)
│   ├── 9router-data/         # 9Router db (combos, keys, quota)
│   └── browser-profiles/     # legacy bind path (now named volume `jobclaw-browser-profiles`)
└── docs/                     # this documentation (Diátaxis layout)
```

## Mount logic (why it looks like this)

- **Tracked vs live config split.** `config/openclaw.json` is the reproducible base.
  The gateway only reads `openclaw.json` inside the `openclaw-home` named volume, which
  OpenClaw's doctor rewrites (migrations, backups). `sync-config.sh` copies base → volume
  (via `docker cp` when running, else `docker run -v`). Never edit the live copy by hand.
  Never file-mount the base over it either: atomic rewrites fail with `EBUSY` on file binds.
- **Named volumes for state.** `openclaw-home` (`jobclaw-openclaw-home`) and
  `browser-profiles` are named volumes so Doctor's `fchmod`/atomic staged publishes work
  on Windows Docker Desktop (binds crash-loop with `EPERM`/`FsSafeError`, exit 78).
  Volumes live in the Linux VM on native ext4. Inspect with
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
