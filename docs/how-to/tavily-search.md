# How-to: enable Tavily web search

Job-board scraping is bot-walled, so discovery runs on Tavily search + extraction
(free tier: 1,000 credits/month). The repo is pre-wired; you only supply the key.

## 1. Key into `.env`

```bash
TAVILY_API_KEY=<key-from-tavily.com-dashboard>
```

`docker-compose.yml` already passes it to the gateway, and `python scripts/setup.py`
already sets the plugin + provider keys (key comes from env, never from tracked files):

```json
{ "plugins": { "entries": { "tavily": { "enabled": true } } },
  "tools": { "web": { "search": { "provider": "tavily" } } } }
```

Recreate the gateway so the new env lands, then install the plugin:

```bash
docker compose up -d --force-recreate openclaw-gateway
# wait ~60s for boot, then:
docker compose exec openclaw-gateway node openclaw.mjs plugins install @openclaw/tavily-plugin
docker compose exec openclaw-gateway node openclaw.mjs skills check | grep -i tavily
# expected: 🔍 tavily (ready and visible)
```

Verify the gateway actually sees the key (should print a non-zero length, never the key):

```bash
docker compose exec openclaw-gateway sh -c 'echo "key len: ${#TAVILY_API_KEY}"'
```

## 2. Smoke-test a search (costs one agent run)

Ask in chat: *"Use tavily_search with query 'AI engineer remote jobs
greenhouse.io', max_results 5, search_depth basic. Reply with titles+URLs
only, under 80 words."*

## 3. How agents should use it (token discipline)

- `tavily_search`, `basic` depth, `max_results 5` for discovery.
- `tavily_extract` for the 3–4 best URLs (handles JS-rendered pages).
- Never screenshot or full-snapshot job pages; cap text reads.
- Free-tier math: each job run costs ~2 searches + ~4 extracts — well within 1,000/month.

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| `tavily_search failed. Missing TAVILY_API_KEY` | gateway started before key existed in `.env` | add key, `--force-recreate openclaw-gateway`, verify key len |
| `plugins install` → state locked | gateway mid-boot | wait 60s, retry |
| results are aggregators, not postings | query too broad | constrain with `site:greenhouse.io OR site:lever.co` |
