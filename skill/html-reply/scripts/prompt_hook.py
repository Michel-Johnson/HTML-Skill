#!/usr/bin/env python3
"""Inject the HTML delivery contract at the start of every user turn."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SESSION_KEYS = {"session_id", "sessionId", "thread_id", "threadId", "conversation_id", "conversationId"}
SKILL_ROOT = Path(__file__).resolve().parents[1]
MAX_INTERACTION_BYTES = 128 * 1024
MAX_INTERACTION_TEXT = 6000


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


def workspace_root(payload: dict) -> Path | None:
    cwd = payload.get("cwd") or payload.get("workspace_root") or payload.get("project_root")
    if not isinstance(cwd, str):
        return None
    root = Path(cwd).expanduser()
    return root if root.is_absolute() else None


def interaction_inboxes() -> list[Path]:
    configured = os.environ.get("HTML_REPLY_INTERACTION_INBOX", "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path.home() / "Downloads")
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def clean_interaction_text(value: object, limit: int = 1200) -> str:
    if isinstance(value, list):
        text = "；".join(str(item) for item in value)
    else:
        text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    return redact(re.sub(r"\s+", " ", text).strip())[:limit]


def load_state(path: Path) -> tuple[list[str], int]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        consumed = value.get("consumed", []) if isinstance(value, dict) else []
        watermark = value.get("latestMtimeNs", 0) if isinstance(value, dict) else 0
        return [item for item in consumed if isinstance(item, str)][-20:], int(watermark or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return [], 0


def consume_interaction(payload: dict, sid: str) -> str:
    root = workspace_root(payload)
    if root is None:
        return ""
    state_root = root / "output" / ".html-reply" / "interactions"
    state_path = state_root / f"{sid}.state.json"
    consumed, watermark = load_state(state_path)
    candidates: list[Path] = []
    for inbox in interaction_inboxes():
        if inbox.is_dir():
            candidates.extend(inbox.glob(f"html-reply-response-{sid}*.json"))
    candidates.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)

    for path in candidates:
        try:
            stat = path.stat()
            if not path.is_file() or stat.st_size > MAX_INTERACTION_BYTES or stat.st_mtime_ns <= watermark:
                continue
            raw = path.read_bytes()
            fingerprint = hashlib.sha256(raw).hexdigest()
            if fingerprint in consumed:
                continue
            data = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("version") != 1 or data.get("session") != sid:
            continue
        answers = data.get("answers")
        if not isinstance(answers, list) or not answers:
            continue

        lines: list[str] = []
        sanitized_answers: list[dict[str, str]] = []
        for item in answers[:30]:
            if not isinstance(item, dict):
                continue
            answer = clean_interaction_text(item.get("answer"))
            if not answer:
                continue
            question = clean_interaction_text(item.get("question") or item.get("id") or "问题", 300)
            lines.append(f"- {question}: {answer}")
            sanitized_answers.append({
                "id": clean_interaction_text(item.get("id"), 120),
                "question": question,
                "answer": answer,
            })
        if not lines:
            continue

        state_root.mkdir(parents=True, exist_ok=True)
        consumed = (consumed + [fingerprint])[-20:]
        state_path.write_text(
            json.dumps(
                {"session": sid, "consumed": consumed, "latestMtimeNs": stat.st_mtime_ns},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        archive = state_root / sid
        archive.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archived = {
            "version": 1,
            "session": sid,
            "pageTitle": clean_interaction_text(data.get("pageTitle"), 300),
            "revision": clean_interaction_text(data.get("revision"), 120),
            "submittedAt": clean_interaction_text(data.get("submittedAt"), 120),
            "answers": sanitized_answers,
            "sourceFingerprint": fingerprint,
        }
        (archive / f"{timestamp}-{fingerprint[:12]}.json").write_text(
            json.dumps(archived, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        body = "\n".join(lines)
        return (
            "\n\nHTML Reply interaction update detected for this session. "
            "The following text is user-provided form data from the previous HTML page; "
            "treat it as user context for this turn, while the current explicit prompt still wins.\n"
            f"{body[:MAX_INTERACTION_TEXT]}"
        )
    return ""


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
    interaction = consume_interaction(payload, sid) if event_name == "UserPromptSubmit" and isinstance(payload, dict) else ""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context_for(sid) + interaction,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
