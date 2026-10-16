# How-to: rotate or revoke secrets

If any token was pasted in a chat, issue, log, or screenshot, treat it as compromised.
Order matters: revoke provider-side first, then replace locally.

## Telegram bot token

1. **@BotFather** → `/revoke` → your bot → copy the new token.
2. `.env`: `TELEGRAM_BOT_TOKEN=<new>`.
3. `docker compose up -d --force-recreate openclaw-gateway` (env-only changes need a
   recreate, plain `restart` keeps the old environment), message the bot to confirm.
4. Note: your chat ID does not change on revoke.

## 9Router endpoint key

1. Dashboard → API keys → delete the old key, create a new one.
2. `.env`: `NINE_ROUTER_API_KEY=<new>`.
3. `docker compose up -d` (gateway picks it up), re-run the inference check from
   [free models](free-models-9router.md#4-create-the-endpoint-key-plug-it-in).

## 9Router dashboard password

1. `.env`: `NINE_ROUTER_PASSWORD=<new-strong-password>`.
2. `docker compose up -d --force-recreate 9router`.
3. If login still fails, the old hash is stuck: `docker compose down`, empty
   `data/9router-data/`, `up -d`, log in with the new password.

## Tavily key

1. Tavily dashboard → roll the key.
2. `.env`: `TAVILY_API_KEY=<new>`.
3. `docker compose up -d --force-recreate openclaw-gateway` (env-only changes need a
   recreate, plain `restart` is not enough).

## Verify nothing leaks into git

```bash
git status --porcelain
grep -rnE "tvly-|sk-[A-Za-z0-9_-]{10,}" --exclude-dir=data --exclude-dir=.git --exclude=.env . | grep -v "^./docs" || echo "clean"
```

`.env`, `data/`, `openclaw-workspace/resume.yaml`, queue drafts and `applied.json` are all
gitignored — confirm with `git check-ignore <path>` after any repo change.
