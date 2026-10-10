# How-to: daily workflow

## Mornings: review the digests

Three jobs run on weekdays (times `--tz`, default Africa/Casablanca): AI-remote search 07:00,
LinkedIn 07:15, Upwork 07:30. Each announces to Telegram. For every keeper open the draft in
`openclaw-workspace/jobs/queue/` — it has score, why-fit, a tailored cover letter/proposal,
and resume tweaks.

Apply **from your own browser** (where you're logged in), never through the agent.

## Log what you sent (keeps tracking honest)

Tell the bot, e.g.: *"Applied to M3 AI Engineer and Eterna Full-Stack today."* It appends
the URLs to `openclaw-workspace/jobs/applied.json` so future runs dedupe. Or edit the file
by hand — it's a JSON array of URLs (gitignored).

## Evenings: read the digest

The 18:00 weekday job summarizes queue vs sent vs skipped and caps used. Use it to spot
stale drafts (older than ~2 weeks: delete or re-check the posting).

## Anytime: paste links for instant scoring

Send any job URL to the bot: *"Score this against my resume and draft a cover letter:
<URL>"*. This manual-link flow works even when board scraping is blocked, because
`tavily_extract` reads the page server-side.

## Approve / edit / skip convention

Reply in Telegram with one of:

- `Approve <slug>` — you will apply yourself; bot marks it in `applied.json` on confirmation.
- `Edit <slug>: <instruction>` — bot rewrites the draft.
- `Skip <slug>: <reason>` — bot records the reason in `MEMORY.md` so future scoring learns
  (e.g. "below salary floor", "requires US citizenship").

## Prune the queue weekly

```bash
ls -lt openclaw-workspace/jobs/queue/
# delete stale drafts; keep .gitkeep
```

Queue contents are gitignored runtime state — safe to delete any time.
