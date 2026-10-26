# How-to: free models via 9Router

9Router is a local model router (dashboard at http://127.0.0.1:20128). It sits between
OpenClaw and free providers so one OpenAI-compatible endpoint serves many models with
fallback. 9Router itself never bills you.

`python scripts/setup.py` provisions the whole default lane automatically:

1. starts 9Router on the named volume `jobclaw-9router-data` (`/app/data`),
2. logs in with `NINE_ROUTER_PASSWORD` using a cookie session,
3. creates or reuses an active API key named `jobclaw` and writes it to `.env` as
   `NINE_ROUTER_API_KEY`,
4. probes the current no-auth OpenCode candidates and creates the `jobclaw-free` combo with
   up to three candidates that answer, most reliable first.

You do **not** need to create an endpoint key or combo by hand, and you should never paste a
key into a tracked file.

## Persistence model

The named volume `jobclaw-9router-data` keeps:

- `db/data.sqlite` — provider connections, combos, keys, settings, usage;
- `machine-id`, `jwt-secret`, `auth/cli-secret`;
- `runtime/` — the `wreq-js` module used by OpenCode Free (installed by setup as a
  workaround for the 0.5.111 image);
- provider OAuth credentials (including Kiro, if connected).

Container restarts, recreates, and host reboots keep all of it. The gateway reconnects on
startup; no dashboard login is needed after a restart.

## Default pool and optional Kiro

The `oc/*` OpenCode Free models need no provider account. Setup tries, in order:

1. `oc/deepseek-v4.1-flash-free`
2. `oc/big-pickle`

The older `muse-spark-*` slugs were deprecated upstream (HTTP 410/400) and are no longer
probed. Setup sends a tiny chat request to each candidate and includes up to three that
actually answer. If none answer, it still creates the combo with the first candidate and
prints a loud warning. That is a soft failure: connect a provider once, then repair the combo.

The 9Router 0.5.111 Docker image omits the optional `wreq-js` module that its OpenCode
provider lazy-loads, so requests fail with `502 ... wreq-js unavailable` even though the
model is otherwise reachable. Setup installs the pinned module into the persisted `runtime/`
directory and links it into `/app/node_modules`; the link is recreated on the next setup run
after a 9Router container recreate. This is an upstream packaging bug
([#5245](https://github.com/decolua/9router/issues/5245)), not a JobClaw configuration issue.

Kiro is optional:

1. Open the dashboard and log in with `NINE_ROUTER_PASSWORD`.
2. **Providers** → **Kiro AI** → OAuth with AWS Builder ID (free), Google, or GitHub
   (≈50 credits/month).
3. If you add Kiro models to `jobclaw-free`, run `--verify` and keep only members that answer.
   Put non-thinking models first; `-thinking` variants burn credits fast.

OAuth is intentionally manual and credentials stay in the 9Router database.

## Verify the route

```bash
python scripts/setup.py --verify
```

This is the authoritative check: it reads the combo from the 9Router management API and sends
a real chat request to every member. It also reads `/v1/models`, but treats that listing as
advisory because the catalog can lag newly added OpenCode slugs; a model listing alone is not
proof. It exits non-zero if any member fails and prints a suggested order (setup candidate
priority first, then any other members).

End-to-end through the same path the agent uses:

```bash
docker compose exec -T openclaw-gateway node openclaw.mjs infer model run --gateway \
  --model 9router/jobclaw-free --prompt "Reply with exactly: GATEWAY_OK" --json
# expect: "outputs": [{"text": "GATEWAY_OK", ...}]
```

`--gateway` matters. Bare `infer model run` uses a different local auth path and can return
401 on a healthy stack.

Repair after a provider change, a dead free model, or a lost volume:

```bash
python scripts/setup.py
python scripts/setup.py --verify
```

Setup is idempotent: it reuses the `.env` key when it matches an active key, reuses the active
key named `jobclaw`, and leaves a non-empty `jobclaw-free` combo unchanged. It only fills a
missing or empty combo, and it re-creates the `wreq-js` link when the 9Router container was
recreated. Deleting the 9Router volume or a key is an explicit manual action.

## When it fails

| Symptom | Cause | Fix |
|---|---|---|
| Setup cannot log in; `401` / remaining attempts | `NINE_ROUTER_PASSWORD` no longer matches the stored hash | Change the password in the dashboard, or reset it. `INITIAL_PASSWORD` only seeds a volume with no stored hash. See [rotate secrets](rotate-secrets.md). Never loop bad passwords — login locks after 5 failures (30s → 2m → 10m → 30m). |
| Setup cannot log in; reset `curl` returns `403 Local only: CLI token required` | 9Router middleware blocks the plain local reset route | Use the dashboard. If the password is truly lost, the only fallback is removing `jobclaw-9router-data` — destructive, never automatic. See [rotate secrets](rotate-secrets.md). |
| Combo was created with the first candidate but no model answered | No no-auth OpenCode model was available when setup ran | Connect a provider (Kiro is the documented fallback), delete `jobclaw-free` in the dashboard, and rerun `python scripts/setup.py`; `--verify` does not rewrite a non-empty combo. |
| `404 No active credentials for provider: X` | That combo member needs a provider connection | Connect X in the dashboard, then `--verify` and drop members that still fail. |
| `403 FreeTierError` on `oc/*` | Free pool is gated or the 9Router version is too old | Check `python scripts/setup.py --check-versions`; rerun setup with Validated or Latest. |
| `400 Unsupported model <slug>` or `410 ModelDeprecated` | Dead model slug in the combo (the `muse-spark-*` slugs are retired) | Remove it from `jobclaw-free` in the dashboard, or delete the combo and rerun setup to rebuild it from the current candidate list. |
| `502 ... wreq-js unavailable` | 9Router 0.5.111 image omitted the OpenCode TLS module (upstream #5245) | Rerun `python scripts/setup.py`; it installs/relinks `wreq-js` in the named volume. If it persists, check `docker compose logs --tail 100 9router`. |
| `/v1/models` returns `401` | Gateway key is stale, or the named volume was replaced | `python scripts/setup.py` recreates/reuses the key and rewrites `.env`; recreate the gateway if it was already running. |
| `--verify` all FAIL | No working provider or all candidates gated | Connect Kiro (or another provider), keep only verified members. |

## Advanced: manual key or combo edits

The dashboard remains available for deliberate overrides. If you create a different key,
put it in `.env` as `NINE_ROUTER_API_KEY` and recreate the gateway. If you edit the combo,
rerun `--verify`. Manual edits are outside the supported setup path; rerunning setup will
only add missing setup-owned state, not undo your combo edits.
