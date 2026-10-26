#!/usr/bin/env python3
"""JobClaw one-command cross-platform setup (stdlib only, Python 3.9+).

Usage (identical on PowerShell, CMD, Git Bash, macOS, Linux):
    python scripts/setup.py                 # full guided setup (idempotent)
    python scripts/setup.py --check         # drift vs the conditional desired config, no writes
    python scripts/setup.py --verify        # prove 9Router combo members answer (tiny chat calls)
    python scripts/setup.py --check-versions # current / validated / latest + image availability
    python scripts/setup.py --one-shot      # apply config via the stopped-gateway setup service
    python scripts/setup.py --offline       # skip all version metadata network calls
    python scripts/setup.py --latest        # choose the Latest preset (confirms unless --yes)
    python scripts/setup.py --yes           # accept defaults, keep integrations, no prompts

Two supported stack presets only: Validated (default) and Latest. Manual `.env`
edits remain possible but are outside the supported presets.

9Router state lives in the named volume `jobclaw-9router-data` mounted at
`/app/data`; setup provisions the `jobclaw` API key and `jobclaw-free` combo, so
normal restarts/recreates need no dashboard work.

Desired always-on keys live in `scripts/desired-config.json`; Telegram and web
search keys are added conditionally from `.env` markers by
`desired_config_for_env()`. The gateway is stopped before config writes and
recreated automatically once afterwards. Never prints secrets; never logs the
`GET /api/keys` response.
"""
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIRED_PATH = os.path.join(ROOT, "scripts", "desired-config.json")
ENV_PATH = os.path.join(ROOT, ".env")
ENV_EXAMPLE = os.path.join(ROOT, ".env.example")
WORKSPACE_DIR = os.path.join(ROOT, "openclaw-workspace")

VALIDATED_OPENCLAW_TAG = "2026.9.9"
VALIDATED_NINE_ROUTER_TAG = "0.5.104"
OPENCLAW_IMAGE_REPO = "ghcr.io/openclaw/openclaw"
NINE_ROUTER_IMAGE_REPO = "decolua/9router"
VALIDATED_OPENCLAW_IMAGE = f"{OPENCLAW_IMAGE_REPO}:{VALIDATED_OPENCLAW_TAG}"
VALIDATED_NINE_ROUTER_IMAGE = f"{NINE_ROUTER_IMAGE_REPO}:{VALIDATED_NINE_ROUTER_TAG}"
VALIDATED_PAIR = (VALIDATED_OPENCLAW_IMAGE, VALIDATED_NINE_ROUTER_IMAGE)

COMBO_NAME = "jobclaw-free"
# OpenCode free-tier slugs move fast. The muse-spark slugs were deprecated
# upstream in 2026-10 (HTTP 410/400), so only keep candidates that answer a
# real probe. Re-probe with `--verify` when this list is updated.
COMBO_CANDIDATES = [
    "oc/deepseek-v4.1-flash-free",
    "oc/big-pickle",
]
NINE_ROUTER_KEY_NAME = "jobclaw"
# 9Router <= 0.5.111 lazy-loads this for the OpenCode free tier but omits it
# from the Docker image; the loader's fallback is broken (upstream #5245).
WREQ_JS_VERSION = "3.2.0"

# Keys this script owns as setup-time state. Secrets are only ever written to
# .env, and only key names (never values) are logged.
MANAGED_ENV_KEYS = [
    "OPENCLAW_BASE",
    "OPENCLAW_GATEWAY_TOKEN",
    "TELEGRAM_ENABLED",
    "TELEGRAM_DM_POLICY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "NINE_ROUTER_IMAGE",
    "NINE_ROUTER_PASSWORD",
    "NINE_ROUTER_API_KEY",
    "WEB_SEARCH_PROVIDER",
    "TAVILY_API_KEY",
]

_GITHUB_RELEASES_URL = "https://api.github.com/repos/openclaw/openclaw/releases?per_page=30"
_DOCKER_HUB_TAGS_URL = (
    "https://hub.docker.com/v2/repositories/decolua/9router/tags"
    "?page_size=100&ordering=last_updated"
)
_GHCR_TOKEN_URL = "https://ghcr.io/token?scope=repository:openclaw/openclaw:pull&service=ghcr.io"

_ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)+)$")
_SAFE_ENV_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@+,=%\-]+$")
_TELEGRAM_ID_RE = re.compile(r"^\d+$")
_TELEGRAM_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")


def run(
    cmd: Sequence[str],
    capture: bool = False,
    check: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """No shell=True (quoting stays safe); errors="replace" for non-UTF-8 console output."""
    try:
        p = subprocess.run(
            list(cmd),
            cwd=ROOT,
            capture_output=capture,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        raise SetupError(f"missing required tool: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise SetupError(f"command timed out: {' '.join(cmd)}")
    if check and p.returncode != 0:
        raise SetupError(
            f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr or p.stdout}"
        )
    return p


class SetupError(Exception):
    pass


def log(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def need_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SetupError(f"missing required tool: {name} (install Docker Desktop 24+ / Python 3.9+)")


def interactive_mode(yes: bool) -> bool:
    return (not yes) and sys.stdin.isatty() and sys.stdout.isatty()


# ---------------------------------------------------------------------------
# .env parsing / writing
# ---------------------------------------------------------------------------


def _extract_inline_comment(raw: str) -> str:
    quote = ""
    escaped = False
    for i, ch in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if quote == '"' and ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or raw[i - 1].isspace()):
            return raw[i:].rstrip()
    return ""


def _strip_inline_comment(raw: str) -> str:
    quote = ""
    escaped = False
    for i, ch in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if quote == '"' and ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or raw[i - 1].isspace()):
            return raw[:i].rstrip()
    return raw.rstrip()


def _parse_env_value(raw: str) -> str:
    val = _strip_inline_comment(raw.strip())
    if not val:
        return ""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        inner = val[1:-1]
        if val[0] == "'":
            return inner
        out: List[str] = []
        i = 0
        escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "$": "$"}
        while i < len(inner):
            ch = inner[i]
            if ch == "\\" and i + 1 < len(inner) and inner[i + 1] in escapes:
                out.append(escapes[inner[i + 1]])
                i += 2
                continue
            out.append(ch)
            i += 1
        return "".join(out)
    return val


def _format_env_value(value: object) -> str:
    val = str(value)
    if val == "":
        return ""
    if _SAFE_ENV_VALUE_RE.match(val) and "$" not in val and "#" not in val:
        return val
    # Single quotes keep `$` literal for Docker Compose interpolation.
    if ("$" in val or "#" in val) and "'" not in val:
        return "'" + val + "'"
    escaped = (
        val.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return '"' + escaped + '"'


def read_env_file(path: Optional[str] = None) -> Tuple[List[str], Dict[str, str]]:
    path = ENV_PATH if path is None else path
    lines: List[str] = []
    values: Dict[str, str] = {}
    if not os.path.exists(path):
        return lines, values
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines()
    for line in lines:
        m = _ENV_LINE_RE.match(line)
        if m:
            values[m.group(1)] = _parse_env_value(m.group(2))
    return lines, values


def read_env_values(path: Optional[str] = None) -> Dict[str, str]:
    return read_env_file(path)[1]


def write_env_updates(updates: Dict[str, str]) -> List[str]:
    """Update active KEY= lines only, preserve comments/order, append missing keys.

    Writes atomically (same-directory temp file + os.replace). Never logs values.
    """
    if not updates:
        return []
    lines, values = read_env_file()
    changed: List[str] = []
    seen = set()
    out: List[str] = []
    for line in lines:
        m = _ENV_LINE_RE.match(line)
        if not m:
            out.append(line)
            continue
        key = m.group(1)
        if key not in updates:
            out.append(line)
            continue
        seen.add(key)
        new_val = str(updates[key])
        if values.get(key) != new_val:
            changed.append(key)
            raw = line.split("=", 1)[1] if "=" in line else ""
            comment = _extract_inline_comment(raw)
            suffix = f"  {comment}" if comment else ""
            prefix_match = re.match(r"^(\s*(?:export\s+)?)", line, re.IGNORECASE)
            prefix = prefix_match.group(1) if prefix_match else ""
            out.append(f"{prefix}{key}={_format_env_value(new_val)}{suffix}")
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={_format_env_value(val)}")
            changed.append(key)
    if not changed:
        return []
    content = "\n".join(out).rstrip("\n") + "\n"
    mode = None
    if os.path.exists(ENV_PATH):
        try:
            mode = os.stat(ENV_PATH).st_mode & 0o777
        except OSError:
            mode = None
    fd, tmp = tempfile.mkstemp(prefix=".env.", dir=ROOT, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, ENV_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return changed


def is_real_secret(value: object) -> bool:
    if value is None:
        return False
    v = str(value).strip()
    if not v:
        return False
    if v.startswith("${") and v.endswith("}"):
        return False
    low = v.lower()
    for marker in (
        "placeholder",
        "change-me",
        "changeme",
        "replace-me",
        "your-",
        "your_",
        "<",
        ">",
    ):
        if marker in low[:32]:
            return False
    return True


def is_tavily_key(value: object) -> bool:
    v = str(value or "").strip()
    return is_real_secret(v) and v.startswith("tvly-") and len(v) > len("tvly-")


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def parse_telegram_ids(raw: str, strict: bool = True) -> List[int]:
    ids: List[int] = []
    for part in re.split(r"[,\s]+", str(raw or "").strip()):
        if not part:
            continue
        if not _TELEGRAM_ID_RE.match(part):
            if strict:
                if part.startswith("-"):
                    raise SetupError(
                        f"invalid Telegram user ID {part!r}: negative IDs are group/chat IDs, "
                        "not user IDs. Group chat IDs belong in channels.telegram.groups, "
                        "not allowFrom."
                    )
                raise SetupError(
                    f"invalid Telegram user ID {part!r}: use one or more numeric Telegram user IDs."
                )
            continue
        ids.append(int(part))
    return ids


def _valid_ids(env: Dict[str, str]) -> List[int]:
    try:
        return parse_telegram_ids(env.get("TELEGRAM_ALLOWED_CHAT_IDS", ""), strict=False)
    except Exception:
        return []


def _ids_text(ids: Sequence[int]) -> str:
    return ",".join(str(i) for i in ids)


# ---------------------------------------------------------------------------
# Desired config
# ---------------------------------------------------------------------------


def load_desired_base() -> dict:
    with open(DESIRED_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_nested(doc: dict, path: str):
    cur: object = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return (False, None)
        cur = cur[part]
    return (True, cur)


def desired_config_for_env(env: Dict[str, str]) -> dict:
    """Always-on keys plus conditional Telegram/search keys.

    The base JSON holds only keys that are always applied. This function is
    shared by the full setup, --one-shot, and --check so all three compare the
    same effective config.
    """
    cfg = json.loads(json.dumps(load_desired_base()))

    token = env.get("TELEGRAM_BOT_TOKEN", "")
    enabled = truthy(env.get("TELEGRAM_ENABLED")) and is_real_secret(token)
    policy = env.get("TELEGRAM_DM_POLICY", "allowlist")
    if policy not in ("allowlist", "pairing"):
        policy = "allowlist"
    if enabled:
        cfg["channels.telegram.enabled"] = True
        if policy == "allowlist":
            cfg["channels.telegram.dmPolicy"] = "allowlist"
            cfg["channels.telegram.allowFrom"] = _valid_ids(env)
        else:
            cfg["channels.telegram.dmPolicy"] = "pairing"
            cfg["channels.telegram.allowFrom"] = []
    else:
        cfg["channels.telegram.enabled"] = False
        cfg["channels.telegram.allowFrom"] = []

    provider = env.get("WEB_SEARCH_PROVIDER", "disabled")
    if provider == "tavily":
        cfg["plugins.entries.tavily.enabled"] = True
        cfg["tools.web.search.enabled"] = True
        cfg["tools.web.search.provider"] = "tavily"
    elif provider == "duckduckgo":
        cfg["plugins.entries.tavily.enabled"] = False
        cfg["tools.web.search.enabled"] = True
        cfg["tools.web.search.provider"] = "duckduckgo"
    else:
        cfg["plugins.entries.tavily.enabled"] = False
        cfg["tools.web.search.enabled"] = False

    return cfg


def _warn_missing_env_refs(cfg: dict, env: Dict[str, str]) -> None:
    for path, want in cfg.items():
        if not isinstance(want, str):
            continue
        for m in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_:]*)\}", want):
            name = m.group(1)
            base = name[4:] if name.startswith("env:") else name
            if not is_real_secret(env.get(base, "")):
                log(
                    f"warning: {path} references ${{{name}}} but .env has no real value yet"
                )


# ---------------------------------------------------------------------------
# Live config / drift check
# ---------------------------------------------------------------------------


def gateway_running() -> bool:
    p = run(["docker", "ps", "--format", "{{.Names}}"], capture=True, check=False)
    return p.returncode == 0 and "jobclaw-openclaw" in (p.stdout or "").split()


def image_exists(tag: str) -> bool:
    p = run(["docker", "image", "inspect", tag], capture=True, check=False)
    return p.returncode == 0


def read_live_config_via_exec() -> dict:
    p = run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "openclaw-gateway",
            "cat",
            "/home/node/.openclaw/openclaw.json",
        ],
        capture=True,
        check=False,
    )
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}


def read_live_config_via_setup_service() -> dict:
    if not image_exists("jobclaw-openclaw:latest"):
        return {}
    # Compose-managed one-shot: no hand-rolled `-v` flags, works on Windows.
    p = run(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "-T",
            "--entrypoint",
            "cat",
            "openclaw-setup",
            "/home/node/.openclaw/openclaw.json",
        ],
        capture=True,
        check=False,
    )
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}


def read_live_config_for_inference() -> dict:
    if gateway_running():
        live = read_live_config_via_exec()
        if live:
            return live
    return read_live_config_via_setup_service()


def _mask(path: str, val) -> str:
    if "apikey" in path.lower() or "token" in path.lower():
        s = val if isinstance(val, str) else json.dumps(val)
        return f"<secret len={len(s)}>" if s and not s.startswith("${") else s
    return json.dumps(val)


# ---------------------------------------------------------------------------
# Environment state / inference
# ---------------------------------------------------------------------------


def load_env_state(generate: bool = False) -> Dict[str, str]:
    if not os.path.exists(ENV_PATH):
        if generate:
            if not os.path.exists(ENV_EXAMPLE):
                raise SetupError("missing .env.example - cannot bootstrap .env")
            shutil.copyfile(ENV_EXAMPLE, ENV_PATH)
            try:
                os.chmod(ENV_PATH, 0o600)
            except OSError:
                pass
            log("created .env from .env.example")
        else:
            raise SetupError("missing .env - run: python scripts/setup.py")
    _, env = read_env_file()
    before = dict(env)

    if not env.get("OPENCLAW_BASE"):
        env["OPENCLAW_BASE"] = VALIDATED_OPENCLAW_IMAGE
    if not env.get("NINE_ROUTER_IMAGE"):
        env["NINE_ROUTER_IMAGE"] = VALIDATED_NINE_ROUTER_IMAGE
    if not env.get("NINE_ROUTER_PORT"):
        env["NINE_ROUTER_PORT"] = "20128"
    if not env.get("OPENCLAW_PORT"):
        env["OPENCLAW_PORT"] = "18789"
    env.setdefault("TELEGRAM_BOT_TOKEN", "")
    env.setdefault("TELEGRAM_ALLOWED_CHAT_IDS", "")
    env.setdefault("TAVILY_API_KEY", "")
    env.setdefault("NINE_ROUTER_API_KEY", "placeholder-change-me-in-9router-dashboard")
    # Do NOT default TELEGRAM_ENABLED / TELEGRAM_DM_POLICY / WEB_SEARCH_PROVIDER
    # here: their absence is the signal infer_markers() uses to migrate an
    # existing .env from tokens and the live config on first upgrade.

    if generate:
        generated: List[str] = []
        if not is_real_secret(env.get("OPENCLAW_GATEWAY_TOKEN")):
            env["OPENCLAW_GATEWAY_TOKEN"] = secrets.token_hex(24)
            generated.append("OPENCLAW_GATEWAY_TOKEN")
        if not is_real_secret(env.get("NINE_ROUTER_PASSWORD")):
            env["NINE_ROUTER_PASSWORD"] = secrets.token_urlsafe(18)
            generated.append("NINE_ROUTER_PASSWORD")
        if generated:
            log("generated random value(s) in .env: " + ", ".join(generated))

    # Keep a copy for callers that want to know what changed.
    env["__original__"] = json.dumps(before)
    return env


def ensure_workspace_files() -> None:
    """Seed local-only workspace files from tracked examples (never overwrite)."""
    for name in ("USER.md", "MEMORY.md"):
        live = os.path.join(WORKSPACE_DIR, name)
        example = live + ".example"
        if os.path.exists(live):
            continue
        if not os.path.exists(example):
            raise SetupError(
                f"missing openclaw-workspace/{name}.example - cannot seed {name}"
            )
        shutil.copyfile(example, live)
        log(f"created openclaw-workspace/{name} from {name}.example")


def infer_markers(env: Dict[str, str], live: Optional[dict] = None) -> Dict[str, str]:
    out = dict(env)
    token = out.get("TELEGRAM_BOT_TOKEN", "")
    if not str(out.get("TELEGRAM_ENABLED", "")).strip():
        out["TELEGRAM_ENABLED"] = "true" if is_real_secret(token) else "false"

    if out.get("TELEGRAM_DM_POLICY") not in ("allowlist", "pairing"):
        live_policy = None
        if live:
            found, value = get_nested(live, "channels.telegram.dmPolicy")
            if found and value in ("allowlist", "pairing"):
                live_policy = value
        if live_policy:
            out["TELEGRAM_DM_POLICY"] = live_policy
        elif _valid_ids(out):
            out["TELEGRAM_DM_POLICY"] = "allowlist"
        else:
            out["TELEGRAM_DM_POLICY"] = "pairing"

    if out.get("WEB_SEARCH_PROVIDER") not in ("tavily", "duckduckgo", "disabled"):
        out["WEB_SEARCH_PROVIDER"] = (
            "tavily" if is_tavily_key(out.get("TAVILY_API_KEY")) else "disabled"
        )
    return out


def warn_weak_secrets(env: Dict[str, str]) -> None:
    for name in ("OPENCLAW_GATEWAY_TOKEN", "NINE_ROUTER_PASSWORD"):
        val = env.get(name, "")
        if is_real_secret(val) and len(val) < 12:
            log(
                f"warning: {name} is shorter than 12 characters; setup will not rotate it. "
                "Rotate it deliberately when convenient."
            )


def _managed_updates(env: Dict[str, str]) -> Dict[str, str]:
    updates = {}
    for key in MANAGED_ENV_KEYS:
        if key in env:
            updates[key] = env[key]
    return updates


# ---------------------------------------------------------------------------
# Version catalog
# ---------------------------------------------------------------------------


def fetch_json(url: str, timeout: int = 15) -> object:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "jobclaw-setup/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _version_tuple(text: str) -> Optional[Tuple[int, ...]]:
    m = _VERSION_RE.match(str(text or "").strip())
    if not m:
        return None
    return tuple(int(part) for part in m.group(1).split("."))


def _image_tag(image: str) -> str:
    return image.rsplit(":", 1)[-1] if ":" in image else ""


def _tag_with_repo(repo: str, tag: str) -> str:
    return f"{repo}:{tag}"


def _ghcr_manifest_exists(tag: str) -> Optional[bool]:
    """True/False when the manifest can be checked; None on network/registry errors."""
    try:
        token_doc = fetch_json(_GHCR_TOKEN_URL)
        token = token_doc.get("token") if isinstance(token_doc, dict) else None
        if not token:
            return None
        req = urllib.request.Request(
            f"https://ghcr.io/v2/openclaw/openclaw/manifests/{tag}",
            method="HEAD",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": (
                    "application/vnd.oci.image.index.v1+json, "
                    "application/vnd.docker.distribution.manifest.list.v2+json, "
                    "application/vnd.oci.image.manifest.v1+json, "
                    "application/vnd.docker.distribution.manifest.v2+json"
                ),
                "User-Agent": "jobclaw-setup/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None


def latest_openclaw_tag() -> Optional[str]:
    try:
        rels = fetch_json(_GITHUB_RELEASES_URL)
    except Exception as e:
        log(f"warning: OpenClaw release lookup failed ({e}); using Validated.")
        return None
    if not isinstance(rels, list):
        return None
    candidates = set()
    for rel in rels:
        if not isinstance(rel, dict):
            continue
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = _version_tuple(str(rel.get("tag_name", "")))
        if tag:
            candidates.add(tag)
    ordered = sorted(candidates, reverse=True)
    for tag_tuple in ordered:
        tag = ".".join(str(p) for p in tag_tuple)
        exists = _ghcr_manifest_exists(tag)
        if exists:
            return tag
        if exists is None:
            log("warning: GHCR manifest check failed; using Validated for OpenClaw.")
            return None
    return None


def _dockerhub_tags() -> List[str]:
    data = fetch_json(_DOCKER_HUB_TAGS_URL)
    names: List[str] = []
    if isinstance(data, dict):
        for item in data.get("results", []):
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
    return names


def latest_nine_router_tag() -> Optional[str]:
    try:
        names = _dockerhub_tags()
    except Exception as e:
        log(f"warning: 9Router tag lookup failed ({e}); using Validated.")
        return None
    valid = []
    for name in names:
        tag_tuple = _version_tuple(name)
        if tag_tuple:
            valid.append(tag_tuple)
    if not valid:
        return None
    return ".".join(str(p) for p in sorted(set(valid), reverse=True)[0])


def resolve_latest_pair(offline: bool) -> Tuple[Tuple[str, str], bool]:
    if offline:
        return VALIDATED_PAIR, False
    oc_tag = latest_openclaw_tag()
    nr_tag = latest_nine_router_tag()
    if not oc_tag or not nr_tag:
        # Plan contract: partial metadata is a failure -> use the full validated pair.
        return VALIDATED_PAIR, False
    return (
        (
            _tag_with_repo(OPENCLAW_IMAGE_REPO, oc_tag),
            _tag_with_repo(NINE_ROUTER_IMAGE_REPO, nr_tag),
        ),
        True,
    )


def _pair_label(pair: Tuple[str, str]) -> str:
    return f"OpenClaw {_image_tag(pair[0])} + 9Router {_image_tag(pair[1])}"


def _availability(pair: Tuple[str, str], offline: bool, nine_tags: Optional[List[str]] = None):
    if offline:
        return ("not checked", "not checked")
    oc = _ghcr_manifest_exists(_image_tag(pair[0]))
    if nine_tags is None:
        try:
            nine_tags = _dockerhub_tags()
        except Exception:
            nine_tags = None
    nr = None if nine_tags is None else (_image_tag(pair[1]) in nine_tags)
    fmt = {True: "available", False: "missing", None: "unknown"}
    return (fmt[oc], fmt[nr])


def check_versions(offline: bool) -> int:
    """Print current, validated, latest, and image availability. No writes."""
    path = ENV_PATH if os.path.exists(ENV_PATH) else ENV_EXAMPLE
    env = read_env_values(path)
    current_pair = (
        env.get("OPENCLAW_BASE", ""),
        env.get("NINE_ROUTER_IMAGE", ""),
    )
    current_complete = bool(current_pair[0] and current_pair[1])

    latest_pair, latest_complete = resolve_latest_pair(offline)
    nine_tags: Optional[List[str]] = None
    if not offline:
        try:
            nine_tags = _dockerhub_tags()
        except Exception as e:
            log(f"warning: could not list 9Router image tags ({e})")
            nine_tags = None

    log("Stack versions")
    if current_complete:
        known = current_pair in (VALIDATED_PAIR, latest_pair)
        suffix = "" if known else "  [outside supported presets]"
        log(f"  Current:   {_pair_label(current_pair)}{suffix}")
    else:
        log("  Current:   not configured")
    log(f"  Validated: {_pair_label(VALIDATED_PAIR)}")
    if offline:
        log("  Latest:    skipped (--offline)")
    elif not latest_complete:
        log("  Latest:    unavailable (using Validated)")
    elif latest_pair != VALIDATED_PAIR:
        log(f"  Latest:    {_pair_label(latest_pair)}")
    else:
        log(f"  Latest:    {_pair_label(latest_pair)} (Validated is current upstream)")
    if not offline and current_complete:
        oc, nr = _availability(current_pair, offline, nine_tags)
        log(f"             current images: GHCR {oc}, Docker Hub {nr}")
    if not offline:
        oc, nr = _availability(VALIDATED_PAIR, offline, nine_tags)
        log(f"             validated images: GHCR {oc}, Docker Hub {nr}")
        if latest_pair != VALIDATED_PAIR:
            oc, nr = _availability(latest_pair, offline, nine_tags)
            log(f"             latest images: GHCR {oc}, Docker Hub {nr}")
    if current_complete and current_pair not in (VALIDATED_PAIR, latest_pair):
        log("")
        log("note: the current pair is outside the supported presets. Rerun setup to")
        log("      replace it with Validated (default) or Latest; manual overrides are")
        log("      supported as an escape hatch only.")
    if latest_complete and latest_pair != VALIDATED_PAIR:
        log("")
        log("note: a newer stable pair is available. Set it deliberately with")
        log("      `python scripts/setup.py --latest`, or stay on Validated.")
    return 0


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------


def ask(prompt: str, default: str = "") -> str:
    try:
        raw = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise SetupError("input aborted")
    return raw if raw else default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    raw = ask(prompt + suffix).lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def ask_secret(prompt: str) -> str:
    try:
        return getpass.getpass(prompt)
    except (EOFError, KeyboardInterrupt):
        raise SetupError("input aborted")


def ask_choice(prompt: str, options: Sequence[str], default: int) -> int:
    log(prompt)
    for i, option in enumerate(options, 1):
        log(f"  {i}) {option}")
    while True:
        raw = ask(f"Choose [{default}]: ", str(default))
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        log(f"invalid choice: {raw!r} (enter 1-{len(options)})")


def choose_stack(
    env: Dict[str, str],
    offline: bool,
    latest_flag: bool,
    yes: bool,
) -> Tuple[str, str]:
    current = (env.get("OPENCLAW_BASE", ""), env.get("NINE_ROUTER_IMAGE", ""))
    interactive = interactive_mode(yes)
    latest_pair, latest_complete = resolve_latest_pair(offline)
    if latest_flag and offline:
        log("warning: --latest cannot resolve upstream with --offline; using the current/validated pair.")
        latest_flag = False
    if not latest_complete and not offline:
        log("warning: upstream version metadata was unavailable; falling back to Validated.")

    log("")
    if latest_pair == VALIDATED_PAIR:
        if offline:
            label = "Validated (offline)"
        elif not latest_complete:
            label = "Validated (latest metadata unavailable)"
        else:
            label = "Validated / Latest (up to date)"
        log("Stack version:")
        log(f"  1) {label} - {_pair_label(VALIDATED_PAIR)}")
        selected = VALIDATED_PAIR
    else:
        log("Stack version:")
        log(f"  1) Validated (recommended) - {_pair_label(VALIDATED_PAIR)}")
        log(f"  2) Latest - {_pair_label(latest_pair)}")
        if interactive:
            default = 1
            if latest_flag and latest_pair != VALIDATED_PAIR:
                default = 2
            elif current == VALIDATED_PAIR:
                default = 1
            elif current == latest_pair:
                default = 2
            while True:
                raw = ask(f"Choose [{default}]: ", str(default))
                if raw in ("1", "2"):
                    selected = VALIDATED_PAIR if raw == "1" else latest_pair
                    break
                log("invalid choice: enter 1 or 2")
        elif latest_flag:
            selected = latest_pair
        elif current == latest_pair:
            selected = latest_pair
        elif current == VALIDATED_PAIR:
            selected = VALIDATED_PAIR
        else:
            selected = VALIDATED_PAIR

    if latest_flag and latest_pair != VALIDATED_PAIR and selected == latest_pair and interactive:
        if not ask_yes_no(f"Use Latest ({_pair_label(latest_pair)})?", default=True):
            selected = VALIDATED_PAIR
            log("using Validated instead.")

    if current != VALIDATED_PAIR and current != latest_pair and selected != current:
        log(f"Current (unsupported preset): {_pair_label(current)}")
        if interactive:
            if not ask_yes_no(f"Replace it with {_pair_label(selected)}?", default=False):
                raise SetupError("aborted: keeping the current unsupported stack pair")

    log(f"selected: {_pair_label(selected)}")
    return selected


def _prompt_telegram_token(env: Dict[str, str]) -> str:
    current = env.get("TELEGRAM_BOT_TOKEN", "")
    if is_real_secret(current):
        return current
    for _ in range(3):
        token = ask_secret(
            "Telegram bot token from @BotFather (input hidden): "
        ).strip()
        if _TELEGRAM_TOKEN_RE.match(token):
            return token
        log(
            "invalid token: expected the token @BotFather gave your bot "
            "(<bot-id>:<secret>). Try again."
        )
    raise SetupError("no valid Telegram bot token provided; choose Disabled or rerun later")


def _prompt_telegram_ids(env: Dict[str, str]) -> List[int]:
    existing = _valid_ids(env)
    if existing:
        log(f"currently allowed numeric Telegram user IDs: {_ids_text(existing)}")
    else:
        log(
            "Use the numeric Telegram user ID of each person allowed to DM the bot "
            "(not the bot's own ID before ':' in the token)."
        )
    for _ in range(3):
        raw = ask(
            "Telegram user IDs allowed to DM the bot (comma-separated"
            + (", Enter keeps current" if existing else "")
            + "): "
        )
        if not raw and existing:
            return existing
        try:
            ids = parse_telegram_ids(raw, strict=True)
        except SetupError as e:
            log(str(e))
            continue
        if ids:
            return ids
        log("at least one numeric Telegram user ID is required for allowlist mode.")
    raise SetupError("no valid Telegram user IDs provided; choose Pairing or Disabled")


def _prompt_telegram(env: Dict[str, str]) -> None:
    # A real token plus an explicit TELEGRAM_ENABLED=false means the user chose
    # Disabled earlier; default to keeping it that way on rerun.
    default = 3 if is_real_secret(env.get("TELEGRAM_BOT_TOKEN")) and not truthy(
        env.get("TELEGRAM_ENABLED")
    ) else 1
    choice = ask_choice(
        "Telegram access:",
        [
            "Allowlist: only these Telegram users may DM the bot (recommended)",
            "Pairing",
            "Disabled",
        ],
        default,
    )
    if choice == 1:
        token = _prompt_telegram_token(env)
        ids = _prompt_telegram_ids(env)
        env["TELEGRAM_ENABLED"] = "true"
        env["TELEGRAM_DM_POLICY"] = "allowlist"
        env["TELEGRAM_BOT_TOKEN"] = token
        env["TELEGRAM_ALLOWED_CHAT_IDS"] = _ids_text(ids)
    elif choice == 2:
        token = _prompt_telegram_token(env)
        env["TELEGRAM_ENABLED"] = "true"
        env["TELEGRAM_DM_POLICY"] = "pairing"
        env["TELEGRAM_BOT_TOKEN"] = token
        # Keep existing IDs in .env, but config leaves allowFrom empty.
    else:
        env["TELEGRAM_ENABLED"] = "false"
        # Do not erase existing token/ID values.


def _prompt_tavily_key(env: Dict[str, str]) -> str:
    current = env.get("TAVILY_API_KEY", "")
    if is_tavily_key(current):
        return current
    for _ in range(3):
        key = ask_secret("Tavily API key (tvly-..., input hidden): ").strip()
        if is_tavily_key(key):
            return key
        log("invalid Tavily key: expected a value starting with 'tvly-'.")
    raise SetupError("no valid Tavily key provided; choose DuckDuckGo or Disabled")


def _prompt_web(env: Dict[str, str]) -> None:
    provider = env.get("WEB_SEARCH_PROVIDER", "")
    if provider == "duckduckgo":
        default = 2
    elif provider == "disabled":
        # Respect an explicit Disabled choice on rerun (keys may still be kept).
        default = 3
    elif is_tavily_key(env.get("TAVILY_API_KEY")):
        default = 1
    else:
        default = 2
    choice = ask_choice(
        "Web search:",
        [
            "Tavily (recommended if you have a key)",
            "DuckDuckGo (key-free, experimental)",
            "Disabled",
        ],
        default,
    )
    if choice == 1:
        env["TAVILY_API_KEY"] = _prompt_tavily_key(env)
        env["WEB_SEARCH_PROVIDER"] = "tavily"
    elif choice == 2:
        env["WEB_SEARCH_PROVIDER"] = "duckduckgo"
    else:
        env["WEB_SEARCH_PROVIDER"] = "disabled"


def keep_integrations(env: Dict[str, str]) -> Dict[str, str]:
    out = dict(env)
    if not truthy(out.get("TELEGRAM_ENABLED")) or not is_real_secret(
        out.get("TELEGRAM_BOT_TOKEN")
    ):
        out["TELEGRAM_ENABLED"] = "false"
    elif out.get("TELEGRAM_DM_POLICY") == "allowlist" and not _valid_ids(out):
        log(
            "warning: TELEGRAM_ENABLED=true with allowlist policy but no numeric user IDs; "
            "leaving Telegram disabled."
        )
        out["TELEGRAM_ENABLED"] = "false"
    if out.get("WEB_SEARCH_PROVIDER") == "tavily" and not is_tavily_key(
        out.get("TAVILY_API_KEY")
    ):
        log(
            "warning: WEB_SEARCH_PROVIDER=tavily but TAVILY_API_KEY is missing or not "
            "a tvly-... key; disabling web search."
        )
        out["WEB_SEARCH_PROVIDER"] = "disabled"
    if out.get("WEB_SEARCH_PROVIDER") not in ("tavily", "duckduckgo", "disabled"):
        out["WEB_SEARCH_PROVIDER"] = "disabled"
    return out


def configure_integrations(
    env: Dict[str, str], live: Optional[dict], yes: bool
) -> Tuple[Dict[str, str], Optional[str]]:
    interactive = interactive_mode(yes)
    if not interactive:
        out = dict(env)
    else:
        out = dict(env)
        token = out.get("TELEGRAM_BOT_TOKEN", "")
        if truthy(out.get("TELEGRAM_ENABLED")) and is_real_secret(token):
            if ask_yes_no("Keep current Telegram config?", default=True):
                pass
            else:
                _prompt_telegram(out)
        else:
            _prompt_telegram(out)

        provider = out.get("WEB_SEARCH_PROVIDER")
        key = out.get("TAVILY_API_KEY", "")
        if provider == "tavily" and is_tavily_key(key):
            if ask_yes_no("Keep current Tavily config?", default=True):
                pass
            else:
                _prompt_web(out)
        else:
            _prompt_web(out)

    # Enforce valid combinations for both interactive and non-interactive runs.
    out = keep_integrations(out)

    plugin = None
    if out.get("WEB_SEARCH_PROVIDER") == "tavily":
        plugin = "@openclaw/tavily-plugin"
    elif out.get("WEB_SEARCH_PROVIDER") == "duckduckgo":
        plugin = "@openclaw/duckduckgo-plugin"
    return out, plugin


# ---------------------------------------------------------------------------
# 9Router HTTP API
# ---------------------------------------------------------------------------


class NineRouterError(SetupError):
    def __init__(
        self,
        message: str,
        status: Optional[int] = None,
        body: object = None,
        retry_after: Optional[int] = None,
    ):
        super().__init__(message)
        self.status = status
        self.body = body
        self.retry_after = retry_after


class NineRouterClient:
    """Cookie-jar management client. Never logs key material."""

    def __init__(self, port: str = "20128"):
        self.base = f"http://127.0.0.1:{port}"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        timeout: int = 30,
    ) -> Tuple[int, object]:
        data = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "jobclaw-setup/1.0",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(raw)
                except Exception:
                    return r.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                body: object = json.loads(raw)
            except Exception:
                body = raw
            retry_after = None
            try:
                retry_after = int(e.headers.get("Retry-After", ""))
            except Exception:
                pass
            if e.code == 429 and retry_after is not None:
                if isinstance(body, dict):
                    if body.get("retryAfter") is None:
                        body["retryAfter"] = retry_after
                else:
                    body = {"retryAfter": retry_after}
            return e.code, body
        except Exception as e:
            raise NineRouterError(
                f"9Router management request failed ({method} {path}): {e}"
            )

    def has_auth_cookie(self) -> bool:
        return any(c.name == "auth_token" for c in self.jar)

    def health(self) -> bool:
        try:
            req = urllib.request.Request(
                self.base + "/api/health",
                headers={"User-Agent": "jobclaw-setup/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                doc = json.loads(r.read().decode("utf-8", "replace"))
                return r.status == 200 and isinstance(doc, dict) and doc.get("ok") is True
        except Exception:
            return False

    def login(self, password: str) -> Tuple[int, object]:
        return self._request("POST", "/api/auth/login", {"password": password})

    def keys(self) -> Tuple[int, object]:
        return self._request("GET", "/api/keys")

    def create_key(self, name: str) -> Tuple[int, object]:
        return self._request("POST", "/api/keys", {"name": name})

    def combos(self) -> Tuple[int, object]:
        return self._request("GET", "/api/combos")

    def create_combo(self, name: str, models: List[str]) -> Tuple[int, object]:
        return self._request("POST", "/api/combos", {"name": name, "models": models})

    def update_combo(self, combo_id: str, models: List[str]) -> Tuple[int, object]:
        return self._request(
            "PUT", f"/api/combos/{urllib.request.quote(combo_id, safe='')}", {"models": models}
        )


def wait_for_nine_router_health(port: str, timeout_s: int = 180) -> bool:
    log("waiting for 9Router health ...")
    client = NineRouterClient(port)
    deadline = time.time() + timeout_s
    last_note = 0.0
    while time.time() < deadline:
        if client.health():
            log("9Router healthy")
            return True
        now = time.time()
        if now - last_note > 15:
            log("  still waiting (up to 180s) ...")
            last_note = now
        time.sleep(2)
    return False


def _http_error_hint(body: object) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    text = text[:300].replace("\n", " ")
    hints = []
    if "FreeTierError" in text:
        hints.append("gated free pool")
    if "No active credentials" in text:
        hints.append("provider not connected")
    if "Unsupported model" in text:
        hints.append("dead model slug")
    return (" - " + ", ".join(hints)) if hints else ""


def _assistant_text(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts).strip()
    return ""


def nine_chat(
    key: str, base: str, model: str, timeout: int = 45
) -> Tuple[bool, str]:
    """Tiny inference probe. Returns (ok, summary); never includes the key."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 32,
    }
    req = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8", "replace"))
            text = _assistant_text(body)
            if text:
                return True, f"answered {text[:60]!r}"
            return False, "HTTP 200 but empty assistant content"
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body: object = json.loads(raw)
        except Exception:
            body = raw
        return False, f"HTTP {e.code}{_http_error_hint(body)}"
    except Exception as e:
        return False, f"request failed: {type(e).__name__}: {e}"


def _login_9router(
    client: NineRouterClient, env: Dict[str, str], interactive: bool
) -> bool:
    """Log in once; on 401 prompt once for the real dashboard password.

    Returns True if the password in .env changed. Raises SetupError on hard stop.
    """
    password = env.get("NINE_ROUTER_PASSWORD", "")
    status, body = client.login(password)
    if status == 200 and isinstance(body, dict) and body.get("success"):
        return False

    if status == 401:
        remaining = body.get("remainingBeforeLock") if isinstance(body, dict) else None
        hint = (
            f" ({remaining} attempt(s) before lockout)" if remaining is not None else ""
        )
        if interactive:
            log(f"9Router rejected NINE_ROUTER_PASSWORD{hint}.")
            new_password = ask_secret("Current 9Router dashboard password (input hidden): ")
            if new_password:
                status, body = client.login(new_password)
                if status == 200 and isinstance(body, dict) and body.get("success"):
                    env["NINE_ROUTER_PASSWORD"] = new_password
                    log("9Router login OK; updated NINE_ROUTER_PASSWORD in .env.")
                    return True
        raise SetupError(
            "9Router login failed: NINE_ROUTER_PASSWORD does not match the stored "
            "dashboard password. Change it in the dashboard and update .env, or see "
            "docs/how-to/rotate-secrets.md for reset options (volume removal is destructive)."
        )

    if status == 429:
        retry_after = None
        if isinstance(body, dict):
            retry_after = body.get("retryAfter")
        if retry_after is None:
            retry_after = 30
        raise SetupError(
            f"9Router login is rate-limited; retry after about {retry_after}s. "
            "Login locks after 5 failures (30s -> 2m -> 10m -> 30m)."
        )

    if status == 403 and isinstance(body, dict) and body.get("mustChangePassword"):
        raise SetupError(
            "9Router requires the default password to be changed before login. Try the "
            f"local reset: curl -s -X POST {client.base}/api/auth/reset-password, then "
            "docker compose up -d --force-recreate 9router, then python scripts/setup.py. "
            "If the reset returns 403 'Local only: CLI token required', use the dashboard "
            "or the destructive volume-removal fallback in docs/how-to/rotate-secrets.md "
            "(never automatic)."
        )

    raise SetupError(f"9Router login failed (HTTP {status}).")


def _ensure_nine_router_key(
    client: NineRouterClient, env: Dict[str, str]
) -> Tuple[bool, str]:
    current = env.get("NINE_ROUTER_API_KEY", "")
    status, body = client.keys()
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get("keys"), list):
        raise SetupError(f"GET /api/keys failed (HTTP {status}); no key response was logged.")
    keys = [k for k in body["keys"] if isinstance(k, dict)]
    active = [k for k in keys if k.get("isActive", True)]
    selected = None
    source = ""

    if is_real_secret(current):
        for k in active:
            if k.get("key") == current:
                selected = k
                source = "existing .env key"
                break
    if selected is None:
        for k in active:
            if k.get("name") == NINE_ROUTER_KEY_NAME:
                selected = k
                source = "existing jobclaw key"
                break
    if selected is None:
        status, body = client.create_key(NINE_ROUTER_KEY_NAME)
        if status not in (200, 201) or not isinstance(body, dict) or not body.get("key"):
            raise SetupError(f"POST /api/keys failed (HTTP {status}); no key response was logged.")
        selected = body
        active.append(body)
        source = "created jobclaw key"

    key = str(selected.get("key", ""))
    if not key:
        raise SetupError("9Router returned an empty API key; refusing to write it.")
    changed = key != current
    if changed:
        env["NINE_ROUTER_API_KEY"] = key
    name = str(selected.get("name") or "unnamed")
    log(f"9Router API key: {name} ({len(active)} active key(s); {source})")
    return changed, key


def _probe_combo_candidates(key: str, base: str) -> List[str]:
    working: List[str] = []
    for candidate in COMBO_CANDIDATES:
        log(f"probing {candidate} ...")
        ok, summary = nine_chat(key, base, candidate, timeout=45)
        log(f"  {candidate}: {'OK ' + summary if ok else 'FAIL ' + summary}")
        if ok:
            working.append(candidate)
            if len(working) >= 3:
                break
    return working


def _ensure_nine_router_combo(
    client: NineRouterClient, key: str, port: str
) -> None:
    base = f"http://127.0.0.1:{port}"
    status, body = client.combos()
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get("combos"), list):
        raise SetupError(f"GET /api/combos failed (HTTP {status}).")
    combos = [c for c in body["combos"] if isinstance(c, dict)]
    combo = next((c for c in combos if c.get("name") == COMBO_NAME), None)
    models = combo.get("models") if isinstance(combo, dict) else None
    if isinstance(models, list) and models:
        log(f"9Router combo {COMBO_NAME} already has {len(models)} member(s); leaving unchanged.")
        return

    working = _probe_combo_candidates(key, base)
    if not working:
        working = [COMBO_CANDIDATES[0]]
        log("")
        log("WARNING: no no-auth OpenCode model answered the probe.")
        log("  Connect a provider once in the 9Router dashboard, then rerun")
        log("  `python scripts/setup.py --verify`. Creating the combo with the first candidate.")
        log("")

    if combo is None:
        status, body = client.create_combo(COMBO_NAME, working)
        if status == 201:
            log(f"9Router combo {COMBO_NAME}: created with {len(working)} member(s).")
            return
        error = str(body.get("error", "")) if isinstance(body, dict) else ""
        if status == 400 and "already exists" in error.lower():
            status, body = client.combos()
            if status != 200 or not isinstance(body, dict) or not isinstance(
                body.get("combos"), list
            ):
                raise SetupError(f"GET /api/combos failed after duplicate race (HTTP {status}).")
            combo = next(
                (
                    c
                    for c in body["combos"]
                    if isinstance(c, dict) and c.get("name") == COMBO_NAME
                ),
                None,
            )
            race_models = combo.get("models") if isinstance(combo, dict) else None
            if isinstance(race_models, list) and race_models:
                log(
                    f"9Router combo {COMBO_NAME} was filled concurrently; leaving unchanged."
                )
                return
        if combo is None:
            raise SetupError(f"POST /api/combos failed (HTTP {status}).")

    combo_id = str(combo.get("id", ""))
    if not combo_id:
        raise SetupError("9Router combo has no id; cannot fill it.")
    status, body = client.update_combo(combo_id, working)
    if status != 200:
        raise SetupError(f"PUT /api/combos/<id> failed (HTTP {status}).")
    log(f"9Router combo {COMBO_NAME}: filled with {len(working)} member(s).")


def ensure_nine_router_wreq() -> bool:
    """Repair 9Router images that omit wreq-js for the OpenCode free tier.

    9Router <= 0.5.111 lazy-loads wreq-js at request time but does not ship it
    in the Docker image; its fallback resolver is broken, so every OpenCode
    request returns 502. Install the module into the persisted /app/data
    volume and link it into /app/node_modules. The link is recreated by setup
    after a 9Router container recreate; the module itself stays in the volume.
    """
    exec_base = ["docker", "compose", "exec", "-T", "-u", "0", "9router"]
    try:
        # Skip images whose provider code no longer references the module.
        p = run(
            exec_base
            + ["sh", "-c", "grep -Rqs 'wreq-js' /app/.next/server/chunks"],
            capture=True,
            check=False,
        )
        if p.returncode != 0:
            return False
        # Already importable (bundled by a fixed image, or installed earlier)?
        p = run(
            exec_base + ["node", "-e", "require.resolve('wreq-js')"],
            capture=True,
            check=False,
        )
        if p.returncode == 0:
            return False

        log("9Router image lacks wreq-js (needed by OpenCode free models); installing ...")
        script = (
            "set -e; "
            "mkdir -p /app/data/runtime; "
            "cd /app/data/runtime; "
            "[ -f package.json ] || npm init -y >/dev/null 2>&1; "
            f"npm install --no-audit --no-fund wreq-js@{WREQ_JS_VERSION} >/dev/null 2>&1; "
            "rm -rf /app/node_modules/wreq-js /app/node_modules/@wreq-js; "
            "ln -s /app/data/runtime/node_modules/wreq-js /app/node_modules/wreq-js; "
            "cd /app; "
            "node -e \"require.resolve('wreq-js')\" >/dev/null"
        )
        p = run(
            exec_base + ["sh", "-c", script],
            capture=True,
            check=False,
            timeout=300,
        )
    except SetupError as e:
        log(f"warning: could not check/install wreq-js: {e}")
        return False
    if p.returncode != 0:
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        log("warning: could not install wreq-js; OpenCode free models may return 502.")
        if out:
            log("  " + out.splitlines()[-1])
        return False
    log("wreq-js installed for the OpenCode free tier.")
    return True


def bootstrap_nine_router(
    env: Dict[str, str], interactive: bool
) -> Tuple[Dict[str, str], bool]:
    """Start 9Router, log in, ensure the jobclaw key and jobclaw-free combo.

    Login/password and key changes are written to .env immediately. Returns
    (env, changed) where changed reports whether either value was updated.
    """
    port = env.get("NINE_ROUTER_PORT", "20128")
    log("starting 9Router ...")
    run(["docker", "compose", "up", "-d", "9router"])
    if not wait_for_nine_router_health(port):
        raise SetupError(
            "9Router did not become healthy within 180s - see: "
            "docker compose logs --tail 100 9router"
        )
    ensure_nine_router_wreq()
    client = NineRouterClient(port)
    changed = _login_9router(client, env, interactive)
    if changed:
        wrote = write_env_updates(_managed_updates(env))
        if wrote:
            log(f".env updated after 9Router login: {', '.join(wrote)}")
    if not client.has_auth_cookie():
        raise SetupError(
            "9Router login returned success but no auth_token cookie; refusing to continue."
        )
    key_changed, key = _ensure_nine_router_key(client, env)
    changed = changed or key_changed
    if key_changed:
        wrote = write_env_updates(_managed_updates(env))
        if wrote:
            log(f".env updated after 9Router key provisioning: {', '.join(wrote)}")
    _ensure_nine_router_combo(client, key, port)
    return env, changed


# ---------------------------------------------------------------------------
# Docker / gateway operations
# ---------------------------------------------------------------------------


def stop_gateway_if_running() -> bool:
    if gateway_running():
        log("stopping openclaw-gateway to apply config ...")
        run(["docker", "compose", "stop", "openclaw-gateway"])
        return True
    return False


def config_set_batch(batch_json: str) -> None:
    if not image_exists("jobclaw-openclaw:latest"):
        raise SetupError(
            "missing image jobclaw-openclaw:latest - run: "
            "docker compose build openclaw-gateway"
        )
    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "-T",
        "openclaw-setup",
        "config",
        "set",
        "--batch-json",
        batch_json,
    ]
    p = run(cmd, capture=True, check=False)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        print(out, file=sys.stderr)
        if "offline maintenance" in out.lower():
            log("")
            log("gateway holds the state lock (starting up or fresh volume without gateway.mode).")
            log("Stop the gateway first, then seed offline:")
            log("  docker compose stop openclaw-gateway")
            log("  python scripts/setup.py --one-shot")
        raise SetupError("config set failed (see output above)")
    if p.stdout.strip():
        log(p.stdout.strip())


def apply_desired_config(desired: dict) -> None:
    batch = json.dumps([{"path": p, "value": v} for p, v in desired.items()])
    config_set_batch(batch)
    log("config applied (additive; doctor-managed keys untouched)")


def seed_gateway_mode() -> None:
    log("seeding gateway.mode offline ...")
    p = run(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "-T",
            "openclaw-setup",
            "config",
            "set",
            "gateway.mode",
            "local",
        ],
        capture=True,
        check=False,
    )
    if p.returncode != 0:
        print((p.stdout or "") + (p.stderr or ""), file=sys.stderr)
        raise SetupError("offline seed of gateway.mode failed")


def install_plugin(package: str) -> bool:
    specs = [package, "npm:" + package]
    for spec in specs:
        log(f"installing search plugin {spec} ...")
        try:
            p = run(
                [
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "-T",
                    "openclaw-setup",
                    "plugins",
                    "install",
                    spec,
                ],
                capture=True,
                check=False,
                timeout=300,
            )
        except SetupError as e:
            log(f"  install attempt failed: {e}")
            continue
        if p.returncode == 0:
            log(f"search plugin installed: {package}")
            return True
        out = (p.stdout or "") + (p.stderr or "")
        log(f"  install attempt failed (exit {p.returncode})")
        tail = out.strip().splitlines()[-3:]
        for line in tail:
            log(f"  {line}")
    log("")
    log(f"WARNING: could not install {package}.")
    log("Retry exactly:")
    log(f"  docker compose stop openclaw-gateway")
    log(f"  docker compose run --rm -T openclaw-setup plugins install {package}")
    log(f"  docker compose up -d --force-recreate openclaw-gateway")
    log("Setup will still finish; fix the plugin install before using web search.")
    return False


def start_gateway_recreate() -> None:
    log("starting 9Router and recreating the gateway ...")
    run(["docker", "compose", "up", "-d", "9router"])
    run(["docker", "compose", "up", "-d", "--force-recreate", "openclaw-gateway"])


def wait_ready(timeout_s: int = 180) -> bool:
    log("waiting for gateway ready ...")
    steady = 0
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = run(
            ["docker", "compose", "logs", "--tail", "100", "openclaw-gateway"],
            capture=True,
            check=False,
        )
        if p.returncode == 0 and "gateway ready" in (p.stdout or "").lower():
            log("gateway ready")
            return True
        # Fallback: the ready marker may have scrolled out of the tail window
        # on chatty gateways - two consecutive successful validates mean serving.
        v = run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "openclaw-gateway",
                "node",
                "openclaw.mjs",
                "config",
                "validate",
            ],
            capture=True,
            check=False,
        )
        if v.returncode == 0:
            steady += 1
            if steady >= 2:
                log("gateway ready (validate steady)")
                return True
        else:
            steady = 0
        time.sleep(5)
    return False


def smoke_test() -> bool:
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "openclaw-gateway",
        "node",
        "openclaw.mjs",
        "infer",
        "model",
        "run",
        "--gateway",
        "--model",
        "9router/jobclaw-free",
        "--prompt",
        "Reply with exactly: GATEWAY_OK",
        "--json",
    ]
    try:
        p = run(cmd, capture=True, check=False, timeout=180)
    except SetupError as e:
        log(f"smoke test failed: {e}")
        return False
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode == 0 and "GATEWAY_OK" in out:
        log("smoke test OK (9router/jobclaw-free -> GATEWAY_OK)")
        return True
    log("smoke test FAILED")
    if out.strip():
        log(out.strip()[-2000:])
    log("gateway logs (tail 100):")
    run(["docker", "compose", "logs", "--tail", "100", "openclaw-gateway"], check=False)
    log("repair: python scripts/setup.py --verify")
    return False


def print_summary(env: Dict[str, str], plugin: Optional[str], plugin_ok: bool, smoke_ok: bool) -> None:
    log("")
    log("setup complete" if smoke_ok and plugin_ok else "setup finished with warnings")
    log(f"  Stack: OpenClaw {_image_tag(env.get('OPENCLAW_BASE', ''))} + "
        f"9Router {_image_tag(env.get('NINE_ROUTER_IMAGE', ''))}")
    log(f"  9Router dashboard: http://127.0.0.1:{env.get('NINE_ROUTER_PORT', '20128')}")
    log(f"  OpenClaw Control UI: http://127.0.0.1:{env.get('OPENCLAW_PORT', '18789')}")
    if truthy(env.get("TELEGRAM_ENABLED")) and is_real_secret(
        env.get("TELEGRAM_BOT_TOKEN")
    ):
        policy = env.get("TELEGRAM_DM_POLICY", "allowlist")
        log(f"  Telegram: enabled ({policy})")
    else:
        log("  Telegram: disabled")
    provider = env.get("WEB_SEARCH_PROVIDER", "disabled")
    log(f"  Web search: {provider}")
    if plugin and not plugin_ok:
        log(f"  Search plugin NOT installed: {plugin} (retry command above)")
    log("  Next steps:")
    log("    - Optional Kiro OAuth: 9Router dashboard -> Providers -> Kiro AI.")
    log("      Credentials persist in jobclaw-9router-data; no re-login after restarts.")
    log("    - Resume: openclaw-workspace/resume.yaml (copy resume.yaml.example if missing).")
    log("    - Profile: fill openclaw-workspace/USER.md (seeded from USER.md.example if missing).")
    if truthy(env.get("TELEGRAM_ENABLED")) and is_real_secret(
        env.get("TELEGRAM_BOT_TOKEN")
    ):
        if env.get("TELEGRAM_DM_POLICY") == "pairing":
            log("    - Telegram pairing: message your bot, then approve:")
            log("        docker compose exec openclaw-gateway node openclaw.mjs pairing list telegram")
            log("        docker compose exec openclaw-gateway node openclaw.mjs pairing approve telegram <CODE>")
        else:
            log("    - Telegram allowlist: message your bot from an allowed user ID.")
    log("    - Optional owner commands (config set requires the gateway stopped):")
    log("        docker compose stop openclaw-gateway")
    log("        docker compose run --rm -T openclaw-setup config set commands.ownerAllowFrom '[\"telegram:<YOUR_USER_ID>\"]'")
    log("        docker compose up -d openclaw-gateway")
    log("      Details: docs/how-to/telegram-setup.md")
    log("  Verify anytime: python scripts/setup.py --check / --verify")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_check() -> int:
    if not os.path.exists(ENV_PATH):
        log("missing .env - run: python scripts/setup.py")
        return 2
    env = load_env_state(generate=False)
    live = read_live_config_for_inference()
    env = keep_integrations(infer_markers(env, live))
    desired = desired_config_for_env(env)
    _warn_missing_env_refs(desired, env)
    if not live:
        log("no live openclaw.json yet (fresh volume - run setup without --check)")
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


def cmd_apply() -> None:
    env = load_env_state(generate=False)
    live = read_live_config_for_inference()
    env = keep_integrations(infer_markers(env, live))
    desired = desired_config_for_env(env)
    _warn_missing_env_refs(desired, env)
    apply_desired_config(desired)


def cmd_one_shot() -> int:
    need_tool("docker")
    env = load_env_state(generate=False)
    live = read_live_config_for_inference()
    env = keep_integrations(infer_markers(env, live))
    desired = desired_config_for_env(env)
    _warn_missing_env_refs(desired, env)
    was_running = gateway_running()
    if was_running:
        run(["docker", "compose", "stop", "openclaw-gateway"])
    apply_desired_config(desired)
    if was_running:
        run(["docker", "compose", "up", "-d", "openclaw-gateway"])
        if not wait_ready(timeout_s=120):
            raise SetupError(
                "gateway did not become ready - see: docker compose logs --tail 50 openclaw-gateway"
            )
    else:
        log("gateway was not running; start it with: docker compose up -d")
    return 0


def cmd_verify() -> int:
    if not os.path.exists(ENV_PATH):
        log("missing .env - run: python scripts/setup.py")
        return 2
    env = load_env_state(generate=False)
    key = env.get("NINE_ROUTER_API_KEY", "")
    if not is_real_secret(key):
        log("no real NINE_ROUTER_API_KEY in .env yet - run: python scripts/setup.py")
        return 2
    port = env.get("NINE_ROUTER_PORT", "20128")
    base = f"http://127.0.0.1:{port}"

    req = urllib.request.Request(
        base + "/v1/models", headers={"Authorization": "Bearer " + key}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            models_doc = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        log(f"/v1/models -> HTTP {e.code}: endpoint key rejected")
        log("repair: python scripts/setup.py  (setup creates/reuses the jobclaw key)")
        return 1
    except Exception as e:
        log(f"9Router unreachable at {base}: {e} - is the stack up?")
        return 1
    if not isinstance(models_doc, dict) or not isinstance(models_doc.get("data"), list):
        log("/v1/models returned an unexpected response shape; refusing to trust it.")
        return 1
    exposed = [
        m.get("id", "") for m in models_doc["data"] if isinstance(m, dict)
    ]
    log(f"/v1/models OK ({len(exposed)} ids exposed; listing is advisory)")

    client = NineRouterClient(port)
    status, body = client.login(env.get("NINE_ROUTER_PASSWORD", ""))
    if status != 200 or not isinstance(body, dict) or not body.get("success"):
        if status == 429:
            retry = body.get("retryAfter") if isinstance(body, dict) else None
            log(f"9Router management login rate-limited (retry after {retry or 'a while'}s).")
        elif status == 403 and isinstance(body, dict) and body.get("mustChangePassword"):
            log("9Router requires a password reset before the management API can be used.")
        else:
            log("9Router management login failed - NINE_ROUTER_PASSWORD may be stale.")
        log("repair: python scripts/setup.py  (or docs/how-to/rotate-secrets.md)")
        return 1
    if not client.has_auth_cookie():
        log("9Router login returned success but no auth_token cookie; refusing to trust it.")
        log("repair: python scripts/setup.py")
        return 1
    status, body = client.combos()
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get("combos"), list):
        log(f"GET /api/combos failed (HTTP {status}).")
        return 1
    combo = next(
        (
            c
            for c in body["combos"]
            if isinstance(c, dict) and c.get("name") == COMBO_NAME
        ),
        None,
    )
    members = combo.get("models") if isinstance(combo, dict) else None
    if not isinstance(members, list) or not members:
        log(f"combo {COMBO_NAME} is missing or empty - repair: python scripts/setup.py")
        return 1
    log(f"combo {COMBO_NAME} members: {', '.join(str(m) for m in members)}")

    rc = 0
    good: List[str] = []
    for model in members:
        listed = model in exposed
        if not listed:
            # 9Router's catalog can lag newly added OpenCode slugs. A real
            # chat response is authoritative; keep the listing as a warning.
            log(f"  {model}: not listed in /v1/models; probing anyway ...")
        ok, summary = nine_chat(key, base, str(model), timeout=45)
        note = "" if listed else " (not listed in /v1/models)"
        log(f"  {model}: {'OK ' + summary if ok else 'FAIL ' + summary}{note}")
        if ok:
            good.append(str(model))
        else:
            rc = 1
    if good:
        priority = {name: i for i, name in enumerate(COMBO_CANDIDATES)}
        good.sort(key=lambda name: priority.get(name, len(priority)))
        log(f"working members: {', '.join(good)}")
        log(
            f"suggested order: {', '.join(good)} "
            "(setup candidate priority; adjust if your probes disagree)"
        )
    else:
        log("NO working member - connect a provider (Kiro OAuth is the documented fallback),")
        log("then repair with: python scripts/setup.py")
    return rc


def cmd_full(offline: bool, latest: bool, yes: bool) -> int:
    need_tool("docker")
    env = load_env_state(generate=True)
    ensure_workspace_files()
    live = read_live_config_for_inference()
    env = infer_markers(env, live)

    print("")
    chosen = choose_stack(env, offline=offline, latest_flag=latest, yes=yes)
    env["OPENCLAW_BASE"] = chosen[0]
    env["NINE_ROUTER_IMAGE"] = chosen[1]

    env, plugin = configure_integrations(env, live, yes=yes)
    warn_weak_secrets(env)

    changed = write_env_updates(_managed_updates(env))
    if changed:
        log(f".env updated: {', '.join(changed)}")
    else:
        log(".env already up to date")

    log("building gateway image (base + Chromium) ...")
    run(["docker", "compose", "build", "openclaw-gateway"])

    env, _ = bootstrap_nine_router(env, interactive_mode(yes))

    stop_gateway_if_running()
    seed_gateway_mode()

    plugin_ok = True
    if plugin:
        plugin_ok = install_plugin(plugin)

    desired = desired_config_for_env(env)
    _warn_missing_env_refs(desired, env)
    apply_desired_config(desired)

    start_gateway_recreate()
    if not wait_ready():
        raise SetupError(
            "gateway did not become ready - see: docker compose logs --tail 50 openclaw-gateway"
        )
    smoke_ok = smoke_test()
    print_summary(env, plugin, plugin_ok, smoke_ok)
    return 0 if (plugin_ok and smoke_ok) else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="JobClaw cross-platform setup")
    ap.add_argument("--check", action="store_true", help="drift vs desired keys, no writes")
    ap.add_argument("--verify", action="store_true", help="prove combo members answer (tiny chat calls)")
    ap.add_argument("--check-versions", action="store_true", help="current/latest/validated + image availability")
    ap.add_argument("--one-shot", action="store_true", help="apply config via stopped-gateway one-shot")
    ap.add_argument("--offline", action="store_true", help="skip version metadata network calls")
    ap.add_argument("--latest", action="store_true", help="select the Latest preset (confirms unless --yes)")
    ap.add_argument("--yes", action="store_true", help="accept defaults, keep integrations, no prompts")
    args = ap.parse_args(argv)
    try:
        if args.check_versions:
            return check_versions(offline=args.offline)
        if args.check:
            return cmd_check()
        if args.verify:
            return cmd_verify()
        if args.one_shot:
            return cmd_one_shot()
        return cmd_full(offline=args.offline, latest=args.latest, yes=args.yes)
    except SetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("aborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
