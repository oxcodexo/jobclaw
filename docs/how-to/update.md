# How-to: update and back up

## Choose and apply a version

Two supported presets only:

- **Validated** (default): OpenClaw `2026.9.9` + 9Router `0.5.104`.
- **Latest**: newest stable upstream pair with published images.

Check what is current before changing anything:

```bash
python scripts/setup.py --check-versions
```

This prints the current pair, Validated, Latest, and image availability. It does not write.
Then update through setup — do not hand-edit the Dockerfile, Compose defaults, or setup
constants:

```bash
python scripts/setup.py                 # choose Validated or Latest interactively
python scripts/setup.py --latest        # preselect Latest (confirms unless --yes)
python scripts/setup.py --latest --yes  # non-interactive Latest
```

Setup pulls/builds the selected images, reuses the existing 9Router volume (keys, combo,
providers), applies the conditional OpenClaw config, recreates the gateway once, and reruns
the smoke test.

If you deliberately use an unsupported `.env` override, rebuild and recreate manually:

```bash
# .env already contains OPENCLAW_BASE / NINE_ROUTER_IMAGE
docker compose pull 9router
docker compose build openclaw-gateway
docker compose up -d --force-recreate 9router openclaw-gateway
```

Setup and `--check-versions` will flag that pair as outside the supported presets. Manual
overrides are an escape hatch, not a supported combination.

Manual 9Router recreation also drops the setup-owned `wreq-js` link; rerun
`python scripts/setup.py` after a manual recreate if OpenCode free models return 502.

## Post-update checks

```bash
python scripts/setup.py --check      # drift
python scripts/setup.py --verify     # each combo member must answer
docker compose ps
docker compose logs --tail 20 openclaw-gateway
# parity: gateway and CLI must report the same version
docker compose exec -T openclaw-gateway node openclaw.mjs --version
docker compose --profile cli run --rm openclaw-cli --version
```

> Security note: OpenClaw has had critical CVEs (for example CVE-2026-25253). Update
> promptly and re-check `docker compose logs` for doctor errors after every update. Config
> schemas migrate between versions; custom providers need `models[].id`, and new
> `meta.migrations.*` keys appear.

Rebuild the gateway after changing the base image so the Chromium/RenderCV layer sits on the
new base. If the gateway crash-loops, read the doctor block in the logs before changing
anything else.

## Downgrades

Downgrades are not guaranteed to work:

- 9Router runs database migrations; an older binary may not understand a newer database.
- OpenClaw config schemas migrate in the named volume.
- The setup presets are forward-tested pairs, not a downgrade mechanism.

Back up both runtime volumes before changing versions (below). If a downgrade fails, restore
the matching backups rather than deleting volumes.

## Back up (what matters)

| What | Where | How |
|---|---|---|
| Secrets + workspace config | `.env`, `openclaw-workspace/` (including `resume.yaml`) | encrypted backup of your choice, never git |
| Gateway state | `jobclaw-openclaw-home` volume | `docker compose stop openclaw-gateway` then `docker run --rm -v jobclaw-openclaw-home:/source:ro -v "$PWD:/backup" alpine tar -czf /backup/openclaw-backup-$(date +%F).tar.gz -C /source .` |
| 9Router state | `jobclaw-9router-data` volume | `docker compose stop 9router` then `docker run --rm -v jobclaw-9router-data:/source:ro -v "$PWD:/backup" alpine tar -czf /backup/9router-backup-$(date +%F).tar.gz -C /source .` |
| Browser profiles (optional) | `jobclaw-browser-profiles` volume | same pattern if you care about persisted logins |
| Tracked repo | everything else | git |

Stop the service before copying its SQLite-backed volume so the database is consistent.

Restore a volume into an existing empty volume:

```bash
docker compose stop openclaw-gateway 9router
docker run --rm -v jobclaw-9router-data:/target -v "$PWD:/backup" alpine \
  sh -c "rm -rf /target/* && tar -xzf /backup/9router-backup-YYYY-MM-DD.tar.gz -C /target"
docker run --rm -v jobclaw-openclaw-home:/target -v "$PWD:/backup" alpine \
  sh -c "rm -rf /target/* && tar -xzf /backup/openclaw-backup-YYYY-MM-DD.tar.gz -C /target"
docker compose up -d
python scripts/setup.py --check
```

Restoring replaces the target volume contents. That is destructive; make a fresh backup first
if the current state matters.

## Git hygiene for this repo

- Commit tracked config/workspace/docs changes normally.
- Before every commit: `git status --porcelain` — `.env`, `resume.yaml`, `USER.md`, `MEMORY.md`,
  queue drafts and `applied.json` must never appear. If one does, stop and fix `.gitignore`.
- Config edits flow one way into the volume: `python scripts/setup.py` for the project key
  set, `config set` for single tweaks, then apply with `python scripts/setup.py --one-shot`.
  Never hand-edit the live copy in the volume (doctor rewrites it).
