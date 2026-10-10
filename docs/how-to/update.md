# How-to: update and back up

## Update images

```bash
docker pull ghcr.io/openclaw/openclaw:latest
docker pull decolua/9router:latest
docker compose up -d --build openclaw-gateway
docker compose up -d
docker compose ps
docker compose logs --tail 20 openclaw-gateway
```

> Security note: OpenClaw has had critical CVEs (e.g. CVE-2026-25253). Update promptly and
> re-check `docker compose logs` for doctor errors after every update — config schemas
> migrate between versions (we tracked `models` → `modelPolicy.allow` this way).

Rebuild the gateway after pulling so the Chromium layer sits on the new base. If the
gateway crash-loops after an update, read the doctor block in the logs before anything else.

## Back up (what matters)

| What | Where | How |
|---|---|---|
| Secrets + workspace config | `.env`, `openclaw-workspace/` (incl. `resume.md`) | encrypted backup of your choice, never git |
| Gateway state (pairing, cron, sessions) | `data/openclaw-home/` | `tar -czf openclaw-backup-$(date +%F).tar.gz data/openclaw-home` |
| Tracked repo | everything else | git (see below) |

Restore: stop the stack, extract over `data/openclaw-home/`, fix ownership if needed
(`docker run --rm --entrypoint sh -v "$PWD/data:/data" <gateway-image> -c "chown -R
1000:1000 /data/openclaw-home"` — mount-point dirs themselves may refuse, which is harmless),
`up -d`.

## Git hygiene for this repo

- Commit tracked config/workspace/docs changes normally.
- Before every commit: `git status --porcelain` — `.env`, `data/`, `resume.md`, queue
  drafts and `applied.json` must never appear. If one does, stop and fix `.gitignore`.
- Config edits flow one way: edit `config/openclaw.json` → `scripts/sync-config.sh` →
  restart gateway. Never hand-edit `data/openclaw-home/openclaw.json` (doctor rewrites it).
