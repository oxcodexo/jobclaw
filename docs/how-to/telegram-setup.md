# How-to: set up Telegram (optional)

Telegram is optional. JobClaw works in the local Control UI without it. When enabled, setup
writes the channel config for you; you never edit `openclaw.json`.

## 1. Create the bot (BotFather)

1. In Telegram open **@BotFather** (verify the exact handle).
2. Send `/newbot`, follow the prompts. Usernames must end in `bot` and be globally unique.
3. Keep the token (`123456:AA...`) for setup. Do not paste it into a tracked file.
4. Optional: `/setprivacy` → your bot → **Disable** (only matters if you add the bot to groups).

## 2. Start a chat with your bot

Open `t.me/<your-bot-username>` → **Start** (or send `/start`). Bots cannot message you
first — without this step nothing arrives.

## 3. Get your numeric user ID

Send any message to **your own bot first**, then within a minute:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
```

Read `result[0].message.from.id` for your **user ID** (or `chat.id` for a DM; they match in a
private chat). This is what `TELEGRAM_ALLOWED_CHAT_IDS` expects — comma-separated numeric
**user IDs**, not group IDs.

Shortcuts and caveats:

- **@userinfobot** also reports your ID — fine as a cross-check, but `getUpdates` on your own
  bot is authoritative (it also proves the token works).
- `getUpdates` returns `[]` if you messaged a *different* bot, if another poller already
  consumed the update, or if the message is older than ~24h. Send a fresh message and retry.
- End-to-end proof (works even while the gateway polls):

```bash
curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d chat_id=<YOUR_USER_ID> -d text="ping"
```

- `404 Not Found` on sendMessage means the ID is wrong. Common mistake: using the number
  before the `:` in the token — that is the **bot's** ID, not yours.
- Negative IDs are group/chat IDs. Setup rejects them for `allowFrom`; group chat IDs belong
  in `channels.telegram.groups`, which setup does not automate.

## 4. Choose a mode during setup

Rerun guided setup:

```bash
python scripts/setup.py
```

It asks:

1. **Allowlist: only these Telegram users may DM the bot (recommended)** — setup prompts for
   the bot token from @BotFather (if missing) and one or more numeric **user IDs** of the
   people allowed to DM the bot, then writes:
   - `TELEGRAM_ENABLED=true`
   - `TELEGRAM_DM_POLICY=allowlist`
   - `TELEGRAM_BOT_TOKEN=<token>`
   - `TELEGRAM_ALLOWED_CHAT_IDS=<ids>`
2. **Pairing** — setup prompts for the token and writes `TELEGRAM_ENABLED=true`,
   `TELEGRAM_DM_POLICY=pairing`. Existing IDs stay in `.env` but the live config leaves
   `allowFrom` empty.
3. **Disabled** — writes `TELEGRAM_ENABLED=false` and keeps existing token/ID values so you
   can re-enable later.

Setup applies the config with the gateway stopped and recreates it automatically. You do not
need a manual `--force-recreate`.

### Allowlist mode

After setup, message the bot from an allowed account. There is no pairing approval step.

### Pairing mode

Message the bot once, then approve the request (codes expire after 1h):

```bash
docker compose exec openclaw-gateway node openclaw.mjs pairing list telegram
docker compose exec openclaw-gateway node openclaw.mjs pairing approve telegram <CODE>
```

Verify with a real reply: message the bot (for example *"introduce yourself briefly"*).
Silent bot after pairing → check `docker compose logs --tail 20 openclaw-gateway` for
`[telegram]` lines and `pairing list` for pending requests.

### Disabled mode

`channels.telegram.enabled` is `false`; no bot token is required. Search and the Control UI
continue to work.

## 5. Owner commands (optional)

Config writes require the gateway stopped:

```bash
docker compose stop openclaw-gateway
docker compose run --rm -T openclaw-setup config set \
  commands.ownerAllowFrom '["telegram:<YOUR_USER_ID>"]'
docker compose up -d openclaw-gateway
```

This lets your Telegram account run privileged commands. Without it you can still manage
everything through `docker compose exec` (see [CLI cheatsheet](../reference/cli-cheatsheet.md)).
Setup never sets `ownerAllowFrom` automatically.

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| `getUpdates` → `result: []` | messaged wrong bot / stale message / consumed elsewhere | message **your** bot fresh, retry within seconds |
| sendMessage → `404` | using the bot's own ID | use the numeric user ID from @userinfobot or `getUpdates` |
| Setup rejects an ID starting with `-` | group/chat ID used as an allowlist user ID | use your numeric user ID; groups need `channels.telegram.groups` |
| Bot never replies, logs show pairing prompt loop | pairing not approved | approve (step 4), check `pairing list` |
| Bot never replies with allowlist enabled | sender ID not in `allowFrom` | rerun setup and add that numeric user ID |
| Token was pasted anywhere public | anyone can control the bot | BotFather → `/revoke` → rerun setup (see [rotate secrets](rotate-secrets.md)) |
