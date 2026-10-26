# How-to: enable Tavily web search (optional)

Job-board scraping is bot-walled, so discovery works best with Tavily search + extraction
(free tier: 1,000 credits/month). Search is optional: choose **DuckDuckGo** (key-free,
experimental) or **Disabled** during setup.

## 1. Run setup and choose Tavily

Rerun guided setup:

```bash
python scripts/setup.py
```

Choose **Tavily (recommended if you have a key)** and paste a key starting with `tvly-`
(input is hidden). Setup writes:

```dotenv
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-...
```

and applies the matching live keys (`plugins.entries.tavily.enabled`,
`tools.web.search.enabled`, `tools.web.search.provider: "tavily"`). It also installs
`@openclaw/tavily-plugin` while the gateway is stopped, then recreates the gateway.

You do not need to install the plugin or edit `openclaw.json` by hand.

### If the plugin install failed

Plugin failure does not roll back the stack, but setup exits non-zero and prints this exact
retry path:

```bash
docker compose stop openclaw-gateway
docker compose run --rm -T openclaw-setup plugins install @openclaw/tavily-plugin
docker compose up -d --force-recreate openclaw-gateway
```

If the bare package fails, setup also tries the explicit `npm:@openclaw/tavily-plugin` form.
After a successful retry, rerun `python scripts/setup.py --check`.

## 2. Verify

```bash
docker compose exec openclaw-gateway node openclaw.mjs skills check | grep -i tavily
# expected: tavily (ready and visible)

docker compose exec openclaw-gateway sh -c 'echo "key len: ${#TAVILY_API_KEY}"'
# non-zero length; never prints the key
```

Smoke-test a search (costs one small agent run). Ask in chat:

> Use tavily_search with query `AI engineer remote jobs greenhouse.io`, max_results 5,
> search_depth basic. Reply with titles+URLs only, under 80 words.

## 3. How agents should use it (token discipline)

- `tavily_search`, `basic` depth, `max_results 5` for discovery.
- `tavily_extract` for the 3–4 best URLs (handles JS-rendered pages).
- Never screenshot or full-snapshot job pages; cap text reads.
- Free-tier math: each job run costs roughly 2 searches + 4 extracts — well within
  1,000/month.

## Alternatives

| Choice | `.env` markers | Plugin | Notes |
|---|---|---|---|
| Tavily | `WEB_SEARCH_PROVIDER=tavily`, `TAVILY_API_KEY=tvly-...` | `@openclaw/tavily-plugin` | Reliable; recommended |
| DuckDuckGo | `WEB_SEARCH_PROVIDER=duckduckgo` | `@openclaw/duckduckgo-plugin` | Key-free; scrapes HTML and can break |
| Disabled | `WEB_SEARCH_PROVIDER=disabled` | none | Explicit `tools.web.search.enabled: false`; no search |

Switch by rerunning setup. Choosing Disabled does not delete an existing Tavily key from
`.env`; it only turns search off.

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| `tavily_search failed. Missing TAVILY_API_KEY` | gateway started before the key existed, or provider is Tavily with an empty key | rerun `python scripts/setup.py`; it disables search or installs the key, then recreates the gateway |
| `plugins install` → state locked | gateway mid-boot | use the plain `stop` / `run` / `up --force-recreate` retry above; setup already stops the gateway during install |
| Setup says search is disabled after choosing Tavily | key was empty or did not start with `tvly-` | rerun setup with a valid key |
| `skills check` shows no Tavily | plugin not installed | run the retry block, then `--check` |
| Results are aggregators, not postings | query too broad | constrain with `site:greenhouse.io OR site:lever.co` |
