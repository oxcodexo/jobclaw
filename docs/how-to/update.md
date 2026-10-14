# How-to: update and back up

## Update images

# Pinned tags (validated combo — OpenClaw 2026.9.9 + 9Router 0.5.95).
# Bump deliberately, never float on :latest (surprise schema breaks).
# To bump: update the tags in .env.example + .env + Dockerfile.gateway +
# docker-compose.yml defaults, then follow this same procedure.

```bash
docker pull ghcr.io/openclaw/openclaw:2026.9.9
docker pull decolua/9router:0.5.95
docker compose up -d --build openclaw-gateway
docker compose up -d
docker compose ps
docker compose logs --tail 20 openclaw-gateway
```

> Security note: OpenClaw has had critical CVEs (e.g. CVE-2026-25253). Update promptly and
> re-check `docker compose logs` for doctor errors after every update — config schemas
> migrate between versions (custom providers need `models[].id`, new `meta.migrations.*`
> keys appear; `agents.defaults.modelPolicy.allow` is still the allowlist).

Rebuild the gateway after pulling so the Chromium layer sits on the new base. If the
gateway crash-loops after an update, read the doctor block in the logs before anything else.

## Back up (what matters)

| What | Where | How |
|---|---|---|
| Secrets + workspace config | `.env`, `openclaw-workspace/` (incl. `resume.md`) | encrypted backup of your choice, never git |
| Gateway state (pairing, cron, sessions) | `openclaw-home` named volume (`jobclaw-openclaw-home`) | `docker run --rm -v jobclaw-openclaw-home:/source:ro -v "$PWD:/backup" alpine tar -czf /backup/openclaw-backup-$(date +%F).tar.gz -C /source .` |
| Tracked repo | everything else | git (see below) |

Restore: stop the stack, extract into the volume, `up -d`:

```bash
docker compose stop openclaw-gateway
docker run --rm -v jobclaw-openclaw-home:/target -v "$PWD:/backup" alpine \
  sh -c "rm -rf /target/* && tar -xzf /backup/openclaw-backup-YYYY-MM-DD.tar.gz -C /target"
docker compose up -d
```

Legacy note: older versions used `./data/openclaw-home/` binds. If migrating, copy once:
`docker run --rm -v jobclaw-openclaw-home:/target -v "$PWD/data/openclaw-home:/src:ro" alpine cp -a /src/. /target/`.

## Git hygiene for this repo

- Commit tracked config/workspace/docs changes normally.
- Before every commit: `git status --porcelain` — `.env`, `data/`, `resume.md`, queue
  drafts and `applied.json` must never appear. If one does, stop and fix `.gitignore`.
- Config edits flow one way: edit `config/openclaw.json` → `scripts/sync-config.sh` →
  restart gateway. Never hand-edit the live copy in the volume (doctor rewrites it).
