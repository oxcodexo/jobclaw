# How-to: daily workflow

JobClaw is interactive. You chat from the web UI or Telegram.

## Find new jobs

Ask in chat: *"Find new AI Engineer postings, remote or Morocco, posted
within 7 days."* Every suggestion carries posting-date evidence; anything
without a date is reported, never queued. Keepers (score 70+) land in
`openclaw-workspace/jobs/queue/` with score, why-fit, tailored cover letter,
and resume tweaks.

Apply **from your own browser** (where you're logged in), never through the agent.

## Log what you sent (keeps tracking honest)

Tell the bot, e.g.: *"Applied to M3 AI Engineer and Eterna Full-Stack today."* It appends
the URLs to `openclaw-workspace/jobs/applied.json` so future searches dedupe. Or edit the file
by hand — it's a JSON array of URLs (gitignored).

## Tailor the resume for a posting

*"Tailor my resume for <job URL or pasted description>."* The agent analyses
the JD, selects facts from `resume.yaml` (never invents), writes a
self-contained build beside the queue draft (`resume.yaml` + PDF +
`manifest.yaml`), and marks it draft until you approve.

## Other expert flows

- *"Cover letter for <job>"* — drafted with the queue item.
- *"Interview prep for <job>"* — role-specific prep pack in chat.
- *"Digest"* / *"summarize my queue"* — ranked summary of drafts,
  approvals/skips pending (replaces the old scheduled digest). Prune stale
  drafts (posting older than ~2 weeks or filled: delete).
- *"Add skill|project|experience <fact>"* — staged as unverified until you confirm.

## Anytime: paste links for instant scoring

Send any job URL to the bot: *"Score this against my resume and draft a cover letter:
<URL>"*. This manual-link flow works even when board scraping is blocked, because
`tavily_extract` reads the page server-side.

## Approve / edit / skip convention

Reply in chat with one of:

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
