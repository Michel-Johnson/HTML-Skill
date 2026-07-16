#!/usr/bin/env python3
"""Inject the HTML delivery contract at the start of every user turn."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path


SESSION_KEYS = {"session_id", "sessionId", "thread_id", "threadId", "conversation_id", "conversationId"}
SKILL_ROOT = Path(__file__).resolve().parents[1]


def command_line(*parts: object) -> str:
    values = [str(part) for part in parts]
    return subprocess.list2cmdline(values) if sys.platform == "win32" else shlex.join(values)


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


def context_for(sid: str) -> str:
    filename = f"output/reply-{sid}.html"
    helper = SKILL_ROOT / "scripts" / "reply_history.py"
    archive_command = command_line(sys.executable, helper, "archive", "--root", "<workspace>", "--session", sid)
    finalize_command = command_line(sys.executable, helper, "finalize", "--root", "<workspace>", "--session", sid)
    return f"""HTML Reply is mandatory for this turn and isolated by session.
Before answering, use the global `$html-reply` Skill at `{SKILL_ROOT / 'SKILL.md'}`.
This session id is `{sid}` and its one stable presentation file is `{filename}`. Other sessions use different files; never overwrite their reply HTML.
Before overwriting, run `{archive_command}`. After writing, run `{finalize_command}` so the left history drawer records this prompt and replays only this session's archived HTML.
The current session's HTML must contain the complete answer. In the final chat message, include one concise summary sentence plus a clickable link to `{filename}`. Copy that exact summary sentence into the page as visible text.
For a short acknowledgement, keep the page proportionally short, but still update this session-specific file."""


def redact(text: str) -> str:
    patterns = [
        r"(?i)(password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*([^\s,;]+)",
        r"\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|npm_[A-Za-z0-9]{12,})\b",
    ]
    for pattern in patterns:
        text = re.sub(pattern, lambda m: (m.group(1) + "=[REDACTED]") if m.lastindex and m.lastindex > 1 else "[REDACTED]", text)
    return text


def remember_prompt(payload: dict, sid: str) -> None:
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        return
    cwd = payload.get("cwd") or payload.get("workspace_root") or payload.get("project_root") or str(Path.cwd())
    if not isinstance(cwd, str) or not Path(cwd).expanduser().is_absolute():
        return
    output = Path(cwd).expanduser() / "output"
    try:
        state = output / ".html-reply" / "sessions"
        state.mkdir(parents=True, exist_ok=True)
        (state / f"{sid}.json").write_text(
            json.dumps({"session": sid, "prompt": redact(prompt.strip())}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    sid = session_id(payload) if isinstance(payload, dict) else "local"
    if isinstance(payload, dict):
        remember_prompt(payload, sid)
    event_name = sys.argv[1] if len(sys.argv) > 1 else "UserPromptSubmit"
    if event_name not in {"SessionStart", "UserPromptSubmit"}:
        event_name = "UserPromptSubmit"
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context_for(sid),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
