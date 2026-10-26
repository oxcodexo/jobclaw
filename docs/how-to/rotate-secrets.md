# How-to: rotate or revoke secrets

If any token was pasted in a chat, issue, log, or screenshot, treat it as compromised.
Order matters: revoke provider-side first, then replace locally. Never print a secret while
diagnosing; `.env` is gitignored.

## Telegram bot token

1. **@BotFather** → `/revoke` → your bot → copy the new token.
2. Replace `TELEGRAM_BOT_TOKEN` in `.env` directly (or blank its value and rerun
   `python scripts/setup.py` to be prompted). Setup never re-prompts for an existing real
   token, because that would make reruns noisy.
3. Recreate the gateway so the new environment is loaded
   (`docker compose up -d --force-recreate openclaw-gateway`), or rerun setup.
4. Message the bot to confirm. Your user ID does not change on revoke.

## OpenClaw gateway token

1. Generate a new long random value.
2. Update `OPENCLAW_GATEWAY_TOKEN` in `.env` (setup does not rotate a working token silently).
3. Run `python scripts/setup.py` or `docker compose up -d --force-recreate openclaw-gateway`.
4. Update any client that used the old token.

Setup warns when this value is shorter than 12 characters but deliberately does not rotate it.

## 9Router endpoint key

Preferred: let setup repair the key.

1. Dashboard → **Endpoint / API keys** → delete the old key (or create a replacement and
   delete the old one).
2. Run `python scripts/setup.py`. If `.env` still points at a deleted key, setup looks for an
   active key named `jobclaw`, creates one if needed, and rewrites `NINE_ROUTER_API_KEY`.
3. Run `python scripts/setup.py --verify`.

Manual alternative: create the new key in the dashboard, put it in `.env`, then recreate the
gateway:

```bash
docker compose up -d --force-recreate openclaw-gateway
python scripts/setup.py --verify
```

Setup never logs the 9Router `GET /api/keys` response because it contains full key values.

## 9Router dashboard password

A stored password hash in `jobclaw-9router-data` wins over `NINE_ROUTER_PASSWORD`.
`INITIAL_PASSWORD` only seeds a volume that has no stored hash, so changing `.env` and
recreating does **not** rotate an existing password.

### Supported path: change it in the dashboard

1. Log in at http://127.0.0.1:20128 with the current password.
2. Change the password in the dashboard.
3. Set `NINE_ROUTER_PASSWORD` in `.env` to the same new value.
4. Run `python scripts/setup.py` to confirm login, reapply state, and recreate the gateway
   automatically.

### Local reset route (may be middleware-blocked)

9Router's reset route clears the stored hash so `INITIAL_PASSWORD` can seed a new one on
recreate, while keeping keys/combos/providers:

```bash
curl -s -X POST http://127.0.0.1:20128/api/auth/reset-password
docker compose up -d --force-recreate 9router
python scripts/setup.py
```

If the reset returns `403 {"error":"Local only: CLI token required"}`, the route is blocked by
9Router middleware for a plain localhost call. Do not loop retries. Use the dashboard path
above; a CLI-token reset is not automated by this repo.

### Destructive fallback: remove the 9Router volume

Only when the password is truly lost. This deletes **all** 9Router state: providers, combos,
API keys, settings, and OAuth credentials (including Kiro). It is never automatic.

1. Back up the volume if the state matters (see [update](update.md)); the SQLite database may
   not be readable without the password, but the backup still preserves it.
2. Stop the stack:
   ```bash
   docker compose down
   ```
3. Remove only the 9Router volume — **not** `docker compose down -v`, which also removes
   `jobclaw-openclaw-home` and `jobclaw-browser-profiles`:
   ```bash
   docker volume rm jobclaw-9router-data
   ```
4. Recreate 9Router and rerun setup. The empty volume seeds login from
   `NINE_ROUTER_PASSWORD`, and setup creates a new `jobclaw` key and `jobclaw-free` combo:
   ```bash
   docker compose up -d 9router
   python scripts/setup.py
   ```
5. Reconnect optional Kiro OAuth if you used it.

## Tavily key

1. Tavily dashboard → roll the key.
2. Replace `TAVILY_API_KEY` in `.env` directly (or blank its value and rerun
   `python scripts/setup.py` to be prompted; setup keeps an existing real key otherwise).
3. Recreate the gateway (`docker compose up -d --force-recreate openclaw-gateway`) and verify
   `python scripts/setup.py --check`.

## Verify nothing leaks into git

```bash
git status --porcelain
grep -rnE "tvly-|sk-[A-Za-z0-9_-]{10,}" --exclude-dir=.git \
  --exclude='.env*' . | grep -v "^./docs" || echo "clean"
```

`.env` (and its atomic temp files, `.env.*`), `openclaw-workspace/resume.yaml`,
queue drafts and `applied.json` are all gitignored — confirm with `git check-ignore <path>`
after any repo change.
