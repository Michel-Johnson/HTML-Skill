#!/usr/bin/env python3
"""Block one Codex thread from writing another thread's HTML Reply files."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path


SESSION_KEYS = ("session_id", "thread_id", "threadId", "sessionId", "conversation_id", "conversationId")
TRANSCRIPT_ID_RE = re.compile(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.I)
STABLE_FILE_RE = re.compile(r"(?:^|[/\\])(?:reply|history)-([A-Za-z0-9._-]+)\.html\b", re.I)
PROMPT_FILE_RE = re.compile(r"(?:^|[/\\])prompt-([A-Za-z0-9._-]+)\.txt\b", re.I)
SHARED_FILE_RE = re.compile(r"(?:^|[/\\])(?:reply|history)\.html\b", re.I)
SESSION_STATE_RE = re.compile(
    r"(?:^|[/\\])(?:sessions[/\\]([A-Za-z0-9._-]+)\.json|"
    r"interactions[/\\]([A-Za-z0-9._-]+)(?:\.state\.json|[/\\]))",
    re.I,
)
ARCHIVE_RE = re.compile(r"(?:^|[/\\])archive[/\\]html-reply[/\\]([A-Za-z0-9._-]+)(?:[/\\]|$)", re.I)
THREAD_PATH_RE = re.compile(r"(?:^|[/\\])threads[/\\]([A-Za-z0-9._-]+)(?:[/\\]|$)", re.I)
NUMBERED_ARCHIVE_FILE_RE = re.compile(
    r"(?:^|[/\\])archive[/\\](?:\.replay[/\\])?reply-\d+\.html\b",
    re.I,
)


def desktop_html_enabled() -> bool:
    override = os.environ.get("HTML_REPLY_SURFACE", "").strip().casefold()
    if override:
        return override in {"desktop", "codex-desktop"}
    return os.environ.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "").strip() == "Codex Desktop"


def safe_identity(payload: dict) -> str:
    raw = ""
    for key in SESSION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            break
    if not raw:
        transcript = payload.get("transcript_path")
        if isinstance(transcript, str):
            match = TRANSCRIPT_ID_RE.search(Path(transcript).name)
            raw = match.group(1) if match else ""
    payload_identity = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.")
    runtime = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        os.environ.get("CODEX_THREAD_ID", "").strip(),
    ).strip("-.")
    return runtime or payload_identity


def command_text(payload: dict) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    for key in ("command", "patch", "input"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return json.dumps(tool_input, ensure_ascii=False)


def reply_history_session(command: str) -> str:
    if "reply_history.py" not in command or not re.search(r"\b(?:archive|finalize)\b", command):
        return ""
    try:
        tokens = shlex.split(command, posix=sys.platform != "win32")
    except ValueError:
        tokens = command.split()
    for index, token in enumerate(tokens[:-1]):
        if token == "--session":
            return re.sub(r"[^A-Za-z0-9._-]+", "-", tokens[index + 1]).strip("-.")
    match = re.search(r"--session(?:=|\s+)[\"']?([A-Za-z0-9._-]+)", command)
    return match.group(1) if match else ""


def protected_identities(command: str) -> set[str]:
    stable_source = NUMBERED_ARCHIVE_FILE_RE.sub("", command)
    identities = set(STABLE_FILE_RE.findall(stable_source))
    identities.update(PROMPT_FILE_RE.findall(command))
    identities.update(match.group(1) or match.group(2) for match in SESSION_STATE_RE.finditer(command))
    identities.update(ARCHIVE_RE.findall(command))
    identities.update(THREAD_PATH_RE.findall(command))
    helper_session = reply_history_session(command)
    if helper_session:
        identities.add(helper_session)
    return {identity for identity in identities if identity}


def invoked_script_sources(payload: dict, command: str) -> str:
    """Read small directly-invoked scripts so hidden hard-coded outputs are visible."""
    cwd = payload.get("cwd")
    root = Path(cwd).expanduser() if isinstance(cwd, str) else Path.cwd()
    try:
        tokens = shlex.split(command, posix=sys.platform != "win32")
    except ValueError:
        tokens = command.split()
    sources: list[str] = []
    for token in tokens:
        clean = token.strip("\"'")
        if not clean.lower().endswith((".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".ps1")):
            continue
        path = Path(clean).expanduser()
        if not path.is_absolute():
            path = root / path
        try:
            if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
                sources.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(sources)


def source_writes_html_reply(source: str) -> bool:
    return bool(
        protected_identities(source)
        and re.search(
            r"\b(?:write_text|write_bytes|writeFile|writeFileSync|copyfile|copy2|rename|replace)\s*\(|"
            r"\bopen\s*\([^)]*,\s*[\"'][wax+]|"
            r"(?:^|\s)(?:cp|mv|tee)\s+",
            source,
            re.M,
        )
    )


def is_write_attempt(payload: dict, command: str, script_source: str = "") -> bool:
    tool_name = str(payload.get("tool_name", ""))
    if tool_name == "apply_patch":
        return True
    if "reply_history.py" in command and re.search(r"\b(?:archive|finalize)\b", command):
        return True
    if script_source and source_writes_html_reply(script_source):
        return True
    return bool(
        re.search(
            r"(?:^|[;&|]\s*)(?:cp|mv|rm|install|tee)\s|"
            r"(?:^|\s)(?:sed|perl)\s+-i\b|"
            r"(?:^|\s)(?:>|>>)\s*[^\s]+|"
            r"\b(?:write_text|write_bytes|open)\s*\(",
            command,
        )
    )


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main() -> int:
    if not desktop_html_enabled():
        print("{}")
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    command = command_text(payload)
    script_source = invoked_script_sources(payload, command) if command else ""
    if not command or not is_write_attempt(payload, command, script_source):
        print("{}")
        return 0

    current = safe_identity(payload)
    inspected = command + ("\n" + script_source if script_source else "")
    targets = protected_identities(inspected)
    shared = bool(SHARED_FILE_RE.search(inspected))
    if shared and current != "legacy":
        deny(
            "HTML Reply isolation guard: shared reply.html/history.html writes are forbidden. "
            "Use the external session paths returned by publish.py --paths."
        )
        return 0
    if targets and (not current or any(target != current for target in targets)):
        deny(
            "HTML Reply isolation guard: this tool call targets another thread's HTML Reply state. "
            f"Current session is {current or '<missing>'}; requested session target(s): {', '.join(sorted(targets))}."
        )
        return 0
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
