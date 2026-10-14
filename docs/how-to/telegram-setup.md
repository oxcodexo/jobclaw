# How-to: set up Telegram

Connect your bot so digests and approvals reach you. Time needed: ~10 minutes.

## 1. Create the bot (BotFather)

1. In Telegram open **@BotFather** (verify the exact handle).
2. Send `/newbot`, follow the prompts. Usernames must end in `bot` and be globally unique.
3. Save the token (`123456:AA...`) into `.env` as `TELEGRAM_BOT_TOKEN`.
4. Optional: `/setprivacy` → your bot → **Disable** (only matters if you add the bot to groups).

## 2. Start a chat with your bot

Open `t.me/<your-bot-username>` → **Start** (or send `/start`). Bots cannot message you
first — without this step nothing arrives.

## 3. Get your numeric chat ID (official way)

Send any message to **your own bot first**, then within a minute:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
```

Read `result[0].message.chat.id` — that number is your chat ID. Put it in `.env` as
`TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated, no spaces, for several people).

Shortcuts and caveats:

- **@userinfobot** also reports your ID — fine as a cross-check, but `getUpdates` on your
  own bot is the authoritative proof (it also proves the token works).
- `getUpdates` returns `[]` if you messaged a *different* bot, if another poller already
  consumed the update, or if the message is older than ~24h. Send a fresh message and retry.
- End-to-end proof (works even while the gateway polls):

```bash
curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d chat_id=<YOUR_ID> -d text="ping"
```

- `404 Not Found` on sendMessage means the `chat_id` is wrong. Common mistake: using the
  number before the `:` in the token — that is the **bot's** ID, not yours. A bot cannot
  message itself.

## 4. Pair the bot with the gateway

Restart so the gateway picks up `.env`, message the bot, then approve (codes expire in 1h):

```bash
docker compose restart openclaw-gateway
# send any message to the bot, then:
docker compose exec openclaw-gateway node openclaw.mjs pairing list telegram
docker compose exec openclaw-gateway node openclaw.mjs pairing approve telegram <CODE>
```

Verify with a real reply: message the bot (e.g. *"introduce yourself briefly"*). Silent bot
after pairing → check `docker compose logs --tail 20 openclaw-gateway` for `[telegram]`
lines and `pairing list` for pending requests.

## 5. Owner commands (optional)

```bash
docker compose exec -T openclaw-gateway node openclaw.mjs config set \
  commands.ownerAllowFrom '["telegram:<YOUR_CHAT_ID>"]'
docker compose restart openclaw-gateway
```
This lets your Telegram account run privileged commands. Without it you can still
manage everything via `docker compose exec openclaw-gateway node openclaw.mjs ...` (see
[CLI cheatsheet](../reference/cli-cheatsheet.md)).

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| `getUpdates` → `result: []` | messaged wrong bot / stale message / consumed elsewhere | message **your** bot fresh, retry within seconds |
| sendMessage → `404` | chat_id is the bot's own ID | use the @userinfobot / getUpdates user ID |
| Bot never replies, logs show pairing prompt loop | pairing not approved | approve (step 4), check `pairing list` |
| Token was pasted anywhere public | anyone can control the bot | BotFather → `/revoke` → update `.env` (see [rotate secrets](rotate-secrets.md)) |
