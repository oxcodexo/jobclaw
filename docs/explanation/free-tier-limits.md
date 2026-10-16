# Explanation: free-tier limits and platform risks

## Model quotas (observed, changes often — recheck dashboards)

| Source | Free budget | Notes |
|---|---|---|
| Kiro AI (via 9Router) | ~50 credits/month (+ trial credits for new accounts) | `kr/*` tool calls can corrupt (`tool input must be valid object JSON`); large prompts can time out. Chat OK, agentic work unreliable — keep as fallback, `-thinking` variants last (credit-hungry). |
| OpenCode Free (via 9Router) | varies (promo models rotate) | `oc/*` tool calls verified working. Model list fluctuates without notice. |
| Tavily | 1,000 credits/month | one job run ≈ 2 searches + 4 extracts. Comfortable. |
| OpenRouter `:free` (alternative) | rate-limited | not wired here; fallback option with its own logging caveats. |

Measured burn: a capped scan run costs ~30–55k LLM input tokens; the combo's first pick
(Muse Spark class) handled full tool loops (search → describe → browser) successfully.

## Privacy: free means logged

Free inference endpoints generally log prompts and may train on them (OpenRouter states
this for free models; assume it everywhere free). Rules:

- `resume.yaml` must contain no passwords, ID numbers, or full street address.
- Secrets live only in `.env` / gateway env — never in prompts, drafts, issues, or logs.
- This tradeoff was explicitly accepted for this project; re-decide for yours.

## Platform risk: why the agent never applies

- **Upwork**: API & MCP terms ban bulk access, scraping/automation and spam patterns.
  Auto-bidders get permanent suspensions plus device-fingerprint bans, forfeiting earnings
  and review history. AI *drafting* is fine; automated *sending* is not. (An official
  Upwork API path exists and is the only legit automation route.)
- **LinkedIn**: the user agreement bans bots/crawlers/automation. Enforcement escalates
  24h limits → 3–14 day locks with ID verification → permanent bans (<15% recovery).
- **Indeed**: aggressive bot/Cloudflare challenges against headless browsers and datacenter IPs.

Hence the architecture: **human-in-the-loop always** — agent drafts to `jobs/queue/`, human
clicks Send in their own logged-in browser. Any fork enabling auto-apply owns its bans.
