#!/usr/bin/env python3
"""Require Codex final responses to link a freshly updated local HTML page."""

from __future__ import annotations

import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse


SKILL_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"
MAX_AGE_SECONDS = 15 * 60
THEME_VERSION = "soft-bauhaus-v1"
SESSION_KEYS = {"session_id", "sessionId", "thread_id", "threadId", "conversation_id", "conversationId"}


def read_payload() -> dict:
    try:
        value = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def find_cwd(payload: dict) -> Path:
    for key in ("cwd", "workspace_root", "project_root", "working_directory"):
        value = payload.get(key)
        if isinstance(value, str):
            path = Path(value).expanduser()
            if path.is_absolute():
                return path
    return Path.cwd()


def session_id(payload: dict) -> str:
    found: list[str] = []
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in SESSION_KEYS and isinstance(child, str) and child.strip():
                    found.append(child.strip())
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(payload)
    raw = found[0] if found else "local"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.") or "local"


def link_targets(message: str) -> list[str]:
    targets = re.findall(r"\]\((<[^>]+>|[^)]+)\)", message)
    targets.extend(re.findall(r"(?<![\w:])([^\s\n()]*?\.html)(?=$|[\s),])", message))
    return targets


def local_path(target: str, cwd: Path) -> Path | None:
    clean = target.strip().strip("<>").split("#", 1)[0]
    if clean.startswith("file://"):
        clean = urlparse(clean).path
    clean = unquote(clean)
    if sys.platform == "win32" and re.match(r"^/[A-Za-z]:/", clean):
        clean = clean[1:]
    if not clean.lower().endswith(".html"):
        return None
    path = Path(clean).expanduser()
    return path if path.is_absolute() else cwd / path


def normalized_text(value: str) -> str:
    value = re.sub(r"```[\s\S]*?```", " ", value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"!??\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)
    return value.casefold()


def final_summary(message: str) -> str:
    without_links = re.sub(r"!??\[[^\]]*\]\([^)]+\)", " ", message)
    lines = [line.strip(" \t-*#>—") for line in without_links.splitlines()]
    candidates = [line for line in lines if len(normalized_text(line)) >= 2]
    return max(candidates, key=len, default="")


def html_visible_text(source: str) -> str:
    source = re.sub(r"<(script|style)\b[^>]*>[\s\S]*?</\1>", " ", source, flags=re.I)
    source = re.sub(r"<[^>]+>", " ", source)
    return unescape(source)


def valid_html(path: Path, summary: str, expected_name: str) -> bool:
    try:
        resolved = path.resolve()
        if "output" not in resolved.parts or resolved.name != expected_name or not resolved.is_file():
            return False
        if time.time() - resolved.stat().st_mtime > MAX_AGE_SECONDS:
            return False
        source = resolved.read_text(encoding="utf-8", errors="ignore")
        head = source[:4096].lower()
        if "<html" not in head and "<!doctype html" not in head:
            return False
        if 'id="html-reply-history-data"' not in source:
            return False
        if f'data-html-reply-theme="{THEME_VERSION}"' not in source:
            return False
        wanted = normalized_text(summary)
        page = normalized_text(html_visible_text(source))
        return len(wanted) >= 2 and wanted in page
    except OSError:
        return False


def respond(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    payload = read_payload()
    message = payload.get("last_assistant_message", "")
    if not isinstance(message, str) or not message.strip():
        return 0

    cwd = find_cwd(payload)
    sid = session_id(payload)
    expected_name = "reply.html" if sid == "legacy" else f"reply-{sid}.html"
    summary = final_summary(message)
    if any(valid_html(path, summary, expected_name) for target in link_targets(message) if (path := local_path(target, cwd))):
        respond({})
        return 0

    reason = (
        "HTML Reply gate: this turn's actual answer must be delivered through the linked HTML, not merely any HTML file. "
        f"Use $html-reply from {SKILL_PATH}: archive the previous stable page, write this turn's complete "
        f"response into this session's stable output/{expected_name} entry, render/verify it, then return a concise summary sentence "
        "with a clickable link. The exact same summary sentence must appear as visible text inside that HTML."
    )
    if payload.get("stop_hook_active"):
        print("[html-reply] warning: correction pass still lacks a valid fresh output HTML link", file=sys.stderr)
        return 0
    respond({"decision": "block", "reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
