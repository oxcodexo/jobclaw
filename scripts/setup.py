#!/usr/bin/env python3
"""JobClaw one-command cross-platform setup (stdlib only).

Usage (identical on PowerShell, CMD, Git Bash, macOS, Linux):
    python scripts/setup.py                 # full guided setup (idempotent)
    python scripts/setup.py --check         # drift vs desired keys, no writes
    python scripts/setup.py --verify        # prove 9Router combo members answer (tiny chat calls)
    python scripts/setup.py --check-versions # compare pins vs upstream, no writes
    python scripts/setup.py --one-shot      # apply via stopped-gateway one-shot
    python scripts/setup.py --offline       # skip web version checks
    python scripts/setup.py --latest        # float pins to newest upstream (confirm)

Desired keys live in scripts/desired-config.json (single source of truth).
State-safe: exec against the running gateway, or `openclaw-setup` compose
service (stable hostname jobclaw-openclaw) with the gateway stopped.
Never uses `docker run` one-shots (use the `openclaw-setup` compose service).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIRED_PATH = os.path.join(ROOT, "scripts", "desired-config.json")
ENV_PATH = os.path.join(ROOT, ".env")
ENV_EXAMPLE = os.path.join(ROOT, ".env.example")
CACHE_PATH = os.path.join(ROOT, ".setup-cache.json")

PINNED_OPENCLAW_BASE = "ghcr.io/openclaw/openclaw:2026.9.9"
PINNED_NINE_ROUTER = "decolua/9router:0.5.104"
DOCKER_HUB_9ROUTER_URL = (
    "https://hub.docker.com/v2/repositories/decolua/9router/tags"
    "?page_size=5&ordering=last_updated"
)
GITHUB_OPENCLAW_RELEASES_URL = (
    "https://api.github.com/repos/openclaw/openclaw/releases?per_page=5"
)


def run(cmd: list[str], capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """No shell=True (quoting stays safe); errors="replace" for non-UTF-8 console output."""
    p = subprocess.run(cmd, cwd=ROOT, capture_output=capture, text=True, errors="replace")
    if check and p.returncode != 0:
        raise SetupError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr or p.stdout}")
    return p


class SetupError(Exception):
    pass


def log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def need_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SetupError(f"missing required tool: {name} (install Docker Desktop 24+ / Python 3.9+)")


def gateway_running() -> bool:
    p = run(["docker", "ps", "--format", "{{.Names}}"], capture=True, check=False)
    return p.returncode == 0 and "jobclaw-openclaw" in (p.stdout or "").split()


def image_exists(tag: str) -> bool:
    p = run(["docker", "image", "inspect", tag], capture=True, check=False)
    return p.returncode == 0


def load_desired() -> dict:
    with open(DESIRED_PATH, encoding="utf-8") as f:
        return json.load(f)


def _dotenv() -> dict[str, str]:
    vals: dict[str, str] = dict(os.environ)
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals.setdefault(k.strip(), v.strip())
    return vals


def load_desired_expanded() -> dict:
    """Load desired keys, keeping secret references as authored.

    OpenClaw custom providers resolve the docs form (`${NAME}`) against the
    gateway environment at runtime (verified on 2026.9.9: the namespaced
    `${env:NAME}` form is stored literally in the credential snapshot and
    never resolves, so the provider stays `available: false` / "Sign-in
    needed" in the UI). Plaintext real keys are never written either
    (doctor flags them and they bypass rotation via `.env`).
    This function keeps refs untouched and warns when `.env` has no real
    value for the referenced name yet.
    """
    import re
    env = _dotenv()
    out: dict = {}
    for path, want in load_desired().items():
        if isinstance(want, str):
            def sub(m: re.Match) -> str:
                name = m.group(1)
                base = name[4:] if name.startswith("env:") else name
                val = env.get(base, "")
                if not val or val.startswith("placeholder") or val.startswith("change-me"):
                    log(f"warning: {path} references ${{{name}}} but .env has no real value yet")
                return m.group(0)
            want = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_:]*)\}", sub, want)
        out[path] = want
    return out


def get_nested(doc: dict, path: str):
    cur: object = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return (False, None)
        cur = cur[part]
    return (True, cur)


def read_live_config_via_exec() -> dict:
    p = run(
        ["docker", "compose", "exec", "-T", "openclaw-gateway",
         "cat", "/home/node/.openclaw/openclaw.json"],
        capture=True, check=False,
    )
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}


def read_live_config_via_setup_service() -> dict:
    # Compose-managed one-shot: no hand-rolled `-v` flags, works on Windows.
    p = run(
        ["docker", "compose", "run", "--rm", "-T", "--entrypoint", "cat",
         "openclaw-setup", "/home/node/.openclaw/openclaw.json"],
        capture=True, check=False,
    )
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}


def _mask(path: str, val) -> str:
    if "apikey" in path.lower() or "token" in path.lower():
        s = val if isinstance(val, str) else json.dumps(val)
        return f"<secret len={len(s)} prefix={s[:8]}>" if s and not s.startswith("${") else s
    return json.dumps(val)


def cmd_check(one_shot: bool) -> int:
    desired = load_desired_expanded()
    live = read_live_config_via_setup_service() if (one_shot or not gateway_running()) \
        else read_live_config_via_exec()
    if not live:
        log("no live openclaw.json yet (fresh volume — run setup without --check)")
        return 2
    rc = 0
    for path, want in desired.items():
        found, got = get_nested(live, path)
        if not found:
            log(f"MISSING {path} (want {_mask(path, want)})")
            rc = 1
        elif got != want:
            log(f"DIFF    {path}: live={_mask(path, got)} want={_mask(path, want)}")
            rc = 1
        else:
            log(f"OK      {path}")
    return rc


def config_set_batch(batch_json: str, one_shot: bool) -> None:
    if one_shot or not gateway_running():
        if not image_exists("jobclaw-openclaw:latest"):
            raise SetupError("missing image jobclaw-openclaw:latest — run: docker compose build openclaw-gateway")
        cmd = ["docker", "compose", "run", "--rm", "-T", "openclaw-setup",
               "config", "set", "--batch-json", batch_json]
    else:
        cmd = ["docker", "compose", "exec", "-T", "openclaw-gateway",
               "node", "openclaw.mjs", "config", "set", "--batch-json", batch_json]
    p = run(cmd, capture=True, check=False)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        print(out, file=sys.stderr)
        if "offline maintenance" in out.lower():
            log("")
            log("gateway holds the state lock (starting up or fresh volume without gateway.mode).")
            log("Wait for 'gateway ready' then retry, or seed offline:")
            log("  python scripts/setup.py --one-shot")
            log("  (or: docker compose stop openclaw-gateway, then retry, then docker compose up -d)")
        raise SetupError("config set failed (see output above)")
    log(p.stdout.strip())


def cmd_apply(one_shot: bool) -> None:
    desired = load_desired_expanded()
    batch = json.dumps([{"path": p, "value": v} for p, v in desired.items()])
    config_set_batch(batch, one_shot=one_shot)
    log("setup applied (additive - doctor-managed keys untouched)")
    if gateway_running() and not one_shot:
        log("then: docker compose restart openclaw-gateway  # gateway was running")


def wait_ready(timeout_s: int = 180) -> bool:
    log("waiting for gateway ready ...")
    steady = 0
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = run(["docker", "compose", "logs", "--tail", "100", "openclaw-gateway"],
                capture=True, check=False)
        if p.returncode == 0 and "gateway ready" in (p.stdout or "").lower():
            log("gateway ready")
            return True
        # Fallback: the ready marker may have scrolled out of the tail window
        # on chatty gateways — two consecutive successful validates mean serving.
        v = run(["docker", "compose", "exec", "-T", "openclaw-gateway",
                 "node", "openclaw.mjs", "config", "validate"],
                capture=True, check=False)
        if v.returncode == 0:
            steady += 1
            if steady >= 2:
                log("gateway ready (validate steady)")
                return True
        else:
            steady = 0
        time.sleep(5)
    return False


def ensure_env() -> None:
    if not os.path.exists(ENV_PATH):
        if not os.path.exists(ENV_EXAMPLE):
            raise SetupError("missing .env.example — cannot bootstrap .env")
        shutil.copyfile(ENV_EXAMPLE, ENV_PATH)
        log("created .env from .env.example — fill secrets as the tutorial prompts")
    with open(ENV_PATH, encoding="utf-8") as f:
        content = f.read()
    replaced = False
    if "change-me-to-a-long-random-token" in content:
        content = content.replace("change-me-to-a-long-random-token", secrets.token_hex(24))
        replaced = True
    if "change-me-to-a-long-random-password" in content:
        content = content.replace("change-me-to-a-long-random-password", secrets.token_urlsafe(18))
        replaced = True
    if replaced:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        log("generated random OPENCLAW_GATEWAY_TOKEN / NINE_ROUTER_PASSWORD in .env")


def fetch_json(url: str, timeout: int = 10) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "jobclaw-setup/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def check_versions(offline: bool) -> int:
    """Pinned by default; warn when upstream is newer. No writes unless --latest."""
    if offline:
        log(f"offline: pinned OPENCLAW_BASE={PINNED_OPENCLAW_BASE}")
        log(f"offline: pinned NINE_ROUTER_IMAGE={PINNED_NINE_ROUTER}")
        return 0
    rc = 0
    try:
        tags = fetch_json(DOCKER_HUB_9ROUTER_URL)
        names = [t.get("name") for t in tags.get("results", [])] if isinstance(tags, dict) else []
        names = [n for n in names if n and n != "latest"]
        if names:
            log(f"upstream 9Router tags (newest first): {', '.join(names[:5])}")
            if PINNED_NINE_ROUTER.split(':')[-1] not in names[:1]:
                log(f"note: pinned {PINNED_NINE_ROUTER} differs from newest {names[0]} — rerun with --latest to float")
                rc = 1
    except Exception as e:
        log(f"9Router version check skipped (network): {e}")
    try:
        rels = fetch_json(GITHUB_OPENCLAW_RELEASES_URL)
        if isinstance(rels, list) and rels:
            tags = [r.get("tag_name") for r in rels if r.get("tag_name")]
            log(f"upstream OpenClaw releases (newest first): {', '.join(tags[:5])}")
    except Exception as e:
        log(f"OpenClaw version check skipped (network): {e}")
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
    except OSError:
        pass
    return rc


def cmd_full(one_shot: bool, offline: bool) -> int:
    need_tool("docker")
    ensure_env()
    check_versions(offline=offline)
    log("building gateway image (base + Chromium) ...")
    run(["docker", "compose", "build", "openclaw-gateway"])
    log("starting stack ...")
    run(["docker", "compose", "up", "-d"])
    if one_shot or not wait_ready(timeout_s=60):
        # Fresh volume or slow Doctor: seed offline with the gateway stopped.
        log("seeding gateway.mode offline (gateway stopped, state-safe one-shot) ...")
        run(["docker", "compose", "stop", "openclaw-gateway"])
        seed = run(
            ["docker", "compose", "run", "--rm", "-T", "openclaw-setup",
             "config", "set", "gateway.mode", "local"],
            capture=True, check=False,
        )
        print((seed.stdout or "") + (seed.stderr or ""))
        if seed.returncode != 0:
            raise SetupError("offline seed of gateway.mode failed")
        run(["docker", "compose", "up", "-d"])
        if not wait_ready():
            raise SetupError("gateway did not become ready — see: docker compose logs --tail 50 openclaw-gateway")
    cmd_apply(one_shot=False)
    run(["docker", "compose", "restart", "openclaw-gateway"])
    wait_ready()
    log("")
    log("setup complete. Next manual steps (cannot run headless):")
    log("  1. 9Router dashboard http://127.0.0.1:20128 -> providers + combo jobclaw-free + endpoint key -> .env NINE_ROUTER_API_KEY -> docker compose up -d --force-recreate openclaw-gateway (.env needs a recreate, restart is not enough)")
    log("  2. Telegram BotFather -> .env TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_CHAT_IDS -> pairing approve")
    log("  3. Tavily key -> .env TAVILY_API_KEY -> plugins install @openclaw/tavily-plugin")
    return 0


def _env_value(name: str) -> str:
    if not os.path.exists(ENV_PATH):
        return ""
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def _nine_chat(key: str, host: str, model: str):
    """Tiny inference probe. Returns (ok, summary). Never includes the key."""
    payload = {"model": model,
               "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
               "max_tokens": 64}
    req = urllib.request.Request(
        host + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.loads(r.read().decode("utf-8", "replace"))
            txt = json.dumps(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
            return True, f"answered {txt[:60]}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300].replace("\n", " ")
        hint = ""
        if "FreeTierError" in body or e.code == 403:
            hint = " -- gated pool (e.g. OpenCode free outside OpenCode): replace member"
        elif "No active credentials" in body:
            hint = " -- provider not connected: dashboard -> Providers -> Connect"
        elif "Unsupported model" in body:
            hint = " -- dead slug: remove from combo"
        return False, f"HTTP {e.code}{hint}"
    except Exception as e:
        return False, f"request failed: {e}"


def cmd_verify() -> int:
    """Prove the inference path: combo members via 9Router, then full gateway path."""
    import sqlite3
    import urllib.error
    key = _env_value("NINE_ROUTER_API_KEY")
    if not key or key.startswith("placeholder"):
        log("no real NINE_ROUTER_API_KEY in .env yet — create the endpoint key first")
        log("(9Router dashboard -> Endpoint / API keys, see docs/how-to/free-models-9router.md)")
        return 2
    host = "http://127.0.0.1:20128"
    req = urllib.request.Request(host + "/v1/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            exposed = [m.get("id", "") for m in json.loads(r.read().decode()).get("data", [])]
    except urllib.error.HTTPError as e:
        log(f"/v1/models -> HTTP {e.code}: endpoint key rejected — recreate it in the dashboard")
        return 1
    except Exception as e:
        log(f"9Router unreachable at {host}: {e} — is the stack up?")
        return 1
    log(f"/v1/models OK ({len(exposed)} ids exposed)")
    # Combo members live in the 9Router sqlite (host bind). Read-only open.
    db = os.path.join(ROOT, "data", "9router-data", "db", "data.sqlite")
    members: list[str] = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = con.execute("select models from combos where name='jobclaw-free'").fetchone()
        con.close()
        if row:
            members = json.loads(row[0])
    except Exception as e:
        log(f"could not read combo members from 9Router db: {e}")
    if not members:
        log("combo jobclaw-free has no members — create it in the dashboard (Combo page)")
        return 1
    log(f"combo jobclaw-free members: {', '.join(members)}")
    rc = 0
    good: list[str] = []
    for m in members:
        if m not in exposed:
            log(f"  {m}: NOT EXPOSED in /v1/models — remove from combo")
            rc = 1
            continue
        ok, summary = _nine_chat(key, host, m)
        log(f"  {m}: {'OK ' + summary if ok else 'FAIL ' + summary}")
        if ok:
            good.append(m)
        else:
            rc = 1
    if good:
        log(f"working members: {', '.join(good)} (put the most reliable first in the combo)")
    else:
        log("NO working member - connect a provider (Kiro AI OAuth is the documented free path),")
        log("then replace combo members with models that answer. Docs: docs/how-to/free-models-9router.md")
    return rc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="JobClaw cross-platform setup")
    ap.add_argument("--check", action="store_true", help="drift vs desired keys, no writes")
    ap.add_argument("--verify", action="store_true", help="prove combo members answer (tiny chat calls)")
    ap.add_argument("--check-versions", action="store_true", help="compare pins vs upstream, no writes")
    ap.add_argument("--one-shot", action="store_true", help="apply via stopped-gateway one-shot")
    ap.add_argument("--offline", action="store_true", help="skip web version checks")
    ap.add_argument("--latest", action="store_true", help="float pins to newest upstream (confirms first)")
    args = ap.parse_args(argv)
    try:
        if args.check_versions:
            return check_versions(offline=args.offline)
        if args.check:
            return cmd_check(one_shot=args.one_shot)
        if args.verify:
            return cmd_verify()
        if args.latest:
            log("latest-float is interactive: review `python scripts/setup.py --check-versions` first,")
            log("then set OPENCLAW_BASE / NINE_ROUTER_IMAGE in .env explicitly. No silent float.")
            return 2
        # Bare `--one-shot` (no other mode flags) = apply-only via the
        # stopped-gateway one-shot service.
        # Anything else falls through to the full guided flow.
        if args.one_shot and not (args.check or args.check_versions):
            need_tool("docker")
            ensure_env()
            cmd_apply(one_shot=True)
            return 0
        return cmd_full(one_shot=args.one_shot, offline=args.offline)
    except SetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
