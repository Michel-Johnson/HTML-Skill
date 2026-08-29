#!/usr/bin/env python3
"""Archive one session-specific reply page and build its searchable history index."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin


START = "<!-- HTML_REPLY_HISTORY_START -->"
END = "<!-- HTML_REPLY_HISTORY_END -->"
THEME_VERSION = "soft-bauhaus-v1"
DATA_RE = re.compile(r'<script type="application/json" id="html-reply-history-data">([\s\S]*?)</script>')
TITLE_RE = re.compile(r"<title>([\s\S]*?)</title>", re.I)
CODE_BLOCK_RE = re.compile(
    r"(?P<pre><pre\b[^>]*>)(?P<gap>\s*)<code\b(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</code>(?P<close>\s*</pre>)",
    re.I,
)

LANGUAGE_ALIASES = {
    "js": "javascript", "jsx": "javascript", "javascript": "javascript",
    "ts": "typescript", "tsx": "typescript", "typescript": "typescript",
    "py": "python", "python": "python",
    "sh": "shell", "bash": "shell", "zsh": "shell", "shell": "shell",
    "html": "html", "htm": "html", "xml": "html",
    "css": "css", "sql": "sql", "json": "json",
}

SESSION_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?")
RESERVED_SESSIONS = {"local", "legacy", ".", ".."}
WINDOWS_DEVICE_NAMES = {
    "con", "prn", "aux", "nul", *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class StorageLayout:
    workspace_root: Path
    data_root: Path
    workspace_id: str
    workspace_dir: Path
    session: str
    session_dir: Path
    draft: Path
    prompt_file: Path
    reply: Path
    history: Path
    archive: Path
    replay: Path
    state: Path
    assets: Path

    def paths(self) -> dict[str, str]:
        legacy_output = self.workspace_root / "output"
        has_legacy = (
            (legacy_output / "reply.html").is_file()
            or (legacy_output / "history.html").is_file()
            or any(legacy_output.glob("reply-*.html"))
            or any(legacy_output.glob("history-*.html"))
            or (legacy_output / "archive" / "html-reply").exists()
        ) if legacy_output.is_dir() else False
        result = {
            "workspaceRoot": str(self.workspace_root),
            "dataRoot": str(self.data_root),
            "workspaceId": self.workspace_id,
            "session": self.session,
            "sessionDir": str(self.session_dir),
            "draft": str(self.draft),
            "promptFile": str(self.prompt_file),
            "reply": str(self.reply),
            "history": str(self.history),
            "archive": str(self.archive),
            "replay": str(self.replay),
            "state": str(self.state),
            "assets": str(self.assets),
        }
        if has_legacy:
            result["legacyOutput"] = str(legacy_output)
            result["legacyWarning"] = (
                "Legacy workspace output still exists and may be committed; migrate it explicitly, "
                "then review it before manual cleanup."
            )
        return result


def explicit_language(attrs: str) -> str:
    match = re.search(r"(?:class\s*=\s*['\"][^'\"]*\b(?:language|lang)-|data-language\s*=\s*['\"])([\w+-]+)", attrs, re.I)
    return LANGUAGE_ALIASES.get(match.group(1).lower(), "") if match else ""


def detect_language(text: str) -> str:
    sample = text.strip()
    if not sample:
        return "text"
    if sample[:1] in "[{":
        try:
            json.loads(sample)
            return "json"
        except Exception:
            pass
    if re.search(r"<!doctype\s+html|</?[a-z][^>]*>", sample, re.I):
        return "html"
    if re.search(r"^\s*(?:select|insert|update|delete|create|alter|with)\b", sample, re.I | re.M):
        return "sql"
    if re.search(r"^\s*(?:def|class|from|import)\b|\b(?:None|True|False|self)\b", sample, re.M):
        return "python"
    if re.search(r"\b(?:interface|namespace|enum)\s+\w+|\btype\s+\w+\s*=|:\s*(?:string|number|boolean)\b", sample):
        return "typescript"
    if re.search(r"\b(?:const|let|var|function)\b|=>|console\.\w+", sample):
        return "javascript"
    if re.search(r"^#!.*\b(?:ba|z)?sh\b|^\s*(?:\$\s+|sudo\s+|cd\s+|export\s+|echo\s+)", sample, re.M):
        return "shell"
    if re.search(r"(?:^|})\s*[^{}]+\{\s*[\w-]+\s*:", sample, re.M):
        return "css"
    return "text"


TOKEN_PATTERNS = {
    "json": re.compile(
        r'(?P<key>"(?:\\.|[^"\\])*")(?=\s*:)|(?P<string>"(?:\\.|[^"\\])*")|'
        r'(?P<number>-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(?P<literal>\b(?:true|false|null)\b)|(?P<punct>[{}\[\],:])'
    ),
    "python": re.compile(
        r'(?P<comment>\#[^\n]*)|(?P<string>"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|'
        r'(?P<keyword>\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|raise|return|True|try|while|with|yield)\b)|'
        r'(?P<number>\b\d+(?:\.\d+)?\b)|(?P<variable>@[A-Za-z_]\w*)'
    ),
    "javascript": re.compile(
        r'(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|(?P<string>`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|'
        r'(?P<keyword>\b(?:async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|false|finally|for|from|function|if|import|in|instanceof|let|new|null|of|return|static|super|switch|this|throw|true|try|typeof|undefined|var|void|while|with|yield)\b)|'
        r'(?P<number>\b\d+(?:\.\d+)?\b)'
    ),
    "typescript": re.compile(
        r'(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|(?P<string>`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|'
        r'(?P<keyword>\b(?:abstract|any|as|async|await|boolean|break|case|catch|class|const|constructor|continue|declare|default|delete|do|else|enum|export|extends|false|finally|for|from|function|if|implements|import|in|instanceof|interface|keyof|let|namespace|never|new|null|number|object|of|private|protected|public|readonly|return|static|string|super|switch|this|throw|true|try|type|typeof|undefined|unknown|var|void|while|yield)\b)|'
        r'(?P<number>\b\d+(?:\.\d+)?\b)'
    ),
    "shell": re.compile(
        r'(?P<comment>\#[^\n]*)|(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|'
        r'(?P<variable>\$\{?\w+\}?|\$[@*#?$!-])|(?P<keyword>\b(?:case|do|done|elif|else|esac|export|fi|for|function|if|in|local|readonly|select|then|until|while)\b)|'
        r'(?P<number>\b\d+(?:\.\d+)?\b)'
    ),
    "sql": re.compile(
        r'(?P<comment>--[^\n]*|/\*[\s\S]*?\*/)|(?P<string>\'(?:\'\'|[^\'])*\')|'
        r'(?P<keyword>\b(?:ADD|ALL|ALTER|AND|AS|ASC|BETWEEN|BY|CASE|CHECK|COLUMN|CREATE|DATABASE|DEFAULT|DELETE|DESC|DISTINCT|DROP|ELSE|END|EXISTS|FOREIGN|FROM|FULL|GROUP|HAVING|IN|INDEX|INNER|INSERT|INTO|IS|JOIN|LEFT|LIKE|LIMIT|NOT|NULL|ON|OR|ORDER|OUTER|PRIMARY|REFERENCES|RIGHT|ROW|SELECT|SET|TABLE|THEN|UNION|UNIQUE|UPDATE|VALUES|VIEW|WHEN|WHERE|WITH)\b)|'
        r'(?P<number>\b\d+(?:\.\d+)?\b)', re.I
    ),
    "html": re.compile(r'(?P<comment><!--[\s\S]*?-->)|(?P<tag></?[A-Za-z][^>]*>|<!doctype[^>]*>)', re.I),
    "css": re.compile(
        r'(?P<comment>/\*[\s\S]*?\*/)|(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|'
        r'(?P<property>--?[\w-]+|[A-Za-z-]+)(?=\s*:)|(?P<number>#[0-9A-Fa-f]{3,8}|\b\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw|s|ms|deg)?)'
    ),
}


def highlight_tokens(text: str, language: str) -> str:
    pattern = TOKEN_PATTERNS.get(language)
    if not pattern:
        return html.escape(text)
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        parts.append(html.escape(text[cursor:match.start()]))
        kind = match.lastgroup or "text"
        parts.append(f'<span class="hr-tok-{kind}">{html.escape(match.group(0))}</span>')
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def highlight_code_blocks(source: str) -> str:
    def replace(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        if "data-html-reply-highlighted" in attrs:
            return match.group(0)
        raw = html.unescape(re.sub(r"<[^>]+>", "", match.group("body")))
        language = explicit_language(attrs) or detect_language(raw)
        pre = match.group("pre")[:-1] + f' data-hr-language="{language}">'
        code_attrs = attrs + f' data-html-reply-highlighted="1" data-language="{language}"'
        return f'{pre}{match.group("gap")}<code{code_attrs}>{highlight_tokens(raw, language)}</code>{match.group("close")}'

    return CODE_BLOCK_RE.sub(replace, source)


def strip_history(source: str) -> str:
    return re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), "", source)


def mark_theme(source: str) -> str:
    """Attach the canonical theme marker without duplicating an older marker."""
    def replace(match: re.Match[str]) -> str:
        opening = match.group(0)
        marker = r"\sdata-html-reply-theme\s*=\s*(['\"])[^'\"]*\1"
        if re.search(marker, opening, re.I):
            return re.sub(
                marker,
                f' data-html-reply-theme="{THEME_VERSION}"',
                opening,
                count=1,
                flags=re.I,
            )
        return opening[:-1] + f' data-html-reply-theme="{THEME_VERSION}">'

    return re.sub(r"<body\b[^>]*>", replace, source, count=1, flags=re.I)


def existing_prompt(source: str) -> str:
    match = DATA_RE.search(source)
    if not match:
        return ""
    try:
        data = json.loads(html.unescape(match.group(1)))
        return str(data.get("currentPrompt", "")).strip()
    except Exception:
        return ""


def title_of(source: str, fallback: str) -> str:
    match = TITLE_RE.search(source)
    return html.unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else fallback


def safe_session(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SystemExit("HTML Reply isolation error: the session ID is missing or malformed")
    if not SESSION_RE.fullmatch(value):
        raise SystemExit(
            "HTML Reply isolation error: the session ID may contain only letters, digits, '.', '_' and '-'"
        )
    lowered = value.casefold()
    if lowered in RESERVED_SESSIONS or lowered.split(".", 1)[0] in WINDOWS_DEVICE_NAMES:
        raise SystemExit(f"HTML Reply isolation error: reserved session ID '{value}' is not allowed")
    return value


def current_thread_session(requested: str = "") -> str:
    """Resolve the publishing identity from the Codex process, not page history.

    ``CODEX_THREAD_ID`` is present in Codex shell tool processes and remains
    unique even when several threads share one working directory.  A caller
    may still pass ``--session`` for tests and non-Codex use, but a mismatched
    value is rejected inside Codex instead of publishing into another thread.
    """
    runtime_raw = os.environ.get("CODEX_THREAD_ID", "")
    runtime = safe_session(runtime_raw) if runtime_raw else ""
    explicit_raw = requested
    explicit = safe_session(explicit_raw) if explicit_raw else ""
    if runtime and explicit and explicit != runtime:
        raise SystemExit(
            "HTML Reply isolation error: --session does not match "
            f"CODEX_THREAD_ID ({explicit} != {runtime})"
        )
    session = runtime or explicit
    if not session:
        raise SystemExit(
            "HTML Reply isolation error: no CODEX_THREAD_ID or explicit --session; "
            "refusing a shared local output"
        )
    return session


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def git_root_for(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolve_data_root(workspace_root: Path, explicit: str | Path | None = None) -> Path:
    if explicit:
        candidate = Path(explicit)
    elif os.environ.get("HTML_REPLY_DATA_DIR", "").strip():
        candidate = Path(os.environ["HTML_REPLY_DATA_DIR"].strip())
    else:
        codex_home = (
            Path(os.environ["CODEX_HOME"].strip()).expanduser()
            if os.environ.get("CODEX_HOME", "").strip()
            else Path.home() / ".codex"
        )
        candidate = codex_home / "html-reply"
    data_root = candidate.expanduser().resolve()
    workspace_root = workspace_root.expanduser().resolve()
    workspace_git_root = git_root_for(workspace_root)
    data_git_root = git_root_for(data_root)
    if is_within(data_root, workspace_root) or (
        workspace_git_root is not None and is_within(data_root, workspace_git_root)
    ) or data_git_root is not None:
        raise SystemExit(
            "HTML Reply storage error: the data directory must be outside every workspace and Git worktree; "
            f"refusing {data_root}"
        )
    return data_root


def storage_layout(
    root: Path,
    session: str,
    data_dir: str | Path | None = None,
) -> StorageLayout:
    workspace_root = root.expanduser().resolve()
    if not workspace_root.is_dir():
        raise SystemExit(f"HTML Reply storage error: workspace does not exist: {workspace_root}")
    session = safe_session(session)
    data_root = resolve_data_root(workspace_root, data_dir)
    canonical_workspace = os.path.normcase(str(workspace_root)).replace("\\", "/")
    workspace_id = hashlib.sha256(canonical_workspace.encode("utf-8")).hexdigest()
    canonical_data_root = os.path.normcase(str(data_root)).replace("\\", "/")
    data_root_id = hashlib.sha256(canonical_data_root.encode("utf-8")).hexdigest()
    workspace_dir = data_root / "workspaces" / workspace_id
    session_dir = workspace_dir / "threads" / session
    draft_root = (Path(tempfile.gettempdir()) / "codex-html-reply" / "drafts").resolve()
    workspace_git_root = git_root_for(workspace_root)
    draft_git_root = git_root_for(draft_root)
    if is_within(draft_root, workspace_root) or (
        workspace_git_root is not None and is_within(draft_root, workspace_git_root)
    ) or draft_git_root is not None:
        raise SystemExit(
            "HTML Reply storage error: the system temporary directory is inside a workspace or Git worktree"
        )
    layout = StorageLayout(
        workspace_root=workspace_root,
        data_root=data_root,
        workspace_id=workspace_id,
        workspace_dir=workspace_dir,
        session=session,
        session_dir=session_dir,
        draft=draft_root / data_root_id / workspace_id / f"reply-{session}.html",
        prompt_file=draft_root / data_root_id / workspace_id / f"prompt-{session}.txt",
        reply=session_dir / f"reply-{session}.html",
        history=session_dir / f"history-{session}.html",
        archive=session_dir / "archive",
        replay=session_dir / "archive" / ".replay",
        state=session_dir / "session.json",
        assets=session_dir / "assets",
    )
    central_targets = (
        layout.workspace_dir,
        layout.session_dir,
        layout.reply,
        layout.history,
        layout.archive,
        layout.replay,
        layout.state,
        layout.assets,
        layout.workspace_dir / "workspace.json",
    )
    for target in central_targets:
        if not is_within(target.resolve(), layout.data_root):
            raise SystemExit(f"HTML Reply storage error: resolved path escapes the data directory: {target}")
    if not is_within(layout.draft.resolve(), draft_root):
        raise SystemExit(f"HTML Reply storage error: resolved draft escapes the temporary directory: {layout.draft}")
    if not is_within(layout.prompt_file.resolve(), draft_root):
        raise SystemExit(
            f"HTML Reply storage error: resolved prompt input escapes the temporary directory: {layout.prompt_file}"
        )
    return layout


def ensure_private_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            path.chmod(0o700)
    except PermissionError as error:
        raise SystemExit(
            "HTML Reply storage error: the external data directory is not writable. "
            "Grant the publisher access to this exact user-level directory; no repository fallback was used. "
            f"({path})"
        ) from error


def write_private(path: Path, content: str) -> None:
    ensure_private_directory(path.parent)
    try:
        path.write_text(content, encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)
    except PermissionError as error:
        raise SystemExit(
            "HTML Reply storage error: the external data directory is not writable. "
            "Grant the publisher access to this exact user-level directory; no repository fallback was used. "
            f"({path})"
        ) from error


def prepare_storage(layout: StorageLayout) -> None:
    for folder in (layout.session_dir, layout.archive, layout.replay, layout.assets):
        ensure_private_directory(folder)
    metadata = {
        "version": 1,
        "workspaceId": layout.workspace_id,
        "workspaceRoot": str(layout.workspace_root),
        "displayName": layout.workspace_root.name,
    }
    write_private(layout.workspace_dir / "workspace.json", json.dumps(metadata, ensure_ascii=False, indent=2))


def reply_path(root: Path, session: str, data_dir: str | Path | None = None) -> Path:
    return storage_layout(root, session, data_dir).reply


def history_path(root: Path, session: str, data_dir: str | Path | None = None) -> Path:
    return storage_layout(root, session, data_dir).history


def rewrite_workspace_urls(source: str, workspace_root: Path) -> str:
    """Make project-relative resources portable without changing page-local anchors."""
    base = workspace_root.as_uri().rstrip("/") + "/"

    def absolute_url(value: str) -> str:
        decoded = html.unescape(value.strip())
        if not decoded or decoded.startswith(("#", "?", "/", "\\", "//")):
            return decoded
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", decoded):
            return decoded
        return urljoin(base, decoded.replace("\\", "/"))

    def replace_attribute(match: re.Match[str]) -> str:
        value = absolute_url(match.group("value"))
        return f'{match.group("name")}{match.group("quote")}{html.escape(value, quote=True)}{match.group("quote")}'

    def replace_css_url(match: re.Match[str]) -> str:
        value = absolute_url(match.group("value"))
        quote = match.group("quote") or ""
        return f"url({quote}{value}{quote})"

    source = re.sub(r"\s*<base\b[^>]*>", "", source, flags=re.I)
    source = re.sub(
        r"(?P<name>\b(?:href|src|poster|action|xlink:href)\s*=\s*)(?P<quote>[\"'])(?P<value>[^\"']*)(?P=quote)",
        replace_attribute,
        source,
        flags=re.I,
    )
    return re.sub(
        r"url\(\s*(?P<quote>[\"']?)(?P<value>[^)\"']+)(?P=quote)\s*\)",
        replace_css_url,
        source,
        flags=re.I,
    )


def redact_sensitive_text(value: str) -> str:
    value = re.sub(
        r"\b(?:sk-[A-Za-z0-9_-]{8,}|github_pat_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9_]{8,})\b",
        "[已脱敏]",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"(\b(?:authorization|proxy-authorization)\s*:\s*)(?:bearer|basic|token)\s+[^\s<]+",
        r"\1[已脱敏]",
        value,
        flags=re.I,
    )
    key = (
        r"(?:[A-Za-z][A-Za-z0-9]*[_-])*"
        r"(?:password|passwd|pwd|token|api[_-]?key|secret(?:[_-]?access[_-]?key)?|"
        r"client[_-]?secret|access[_-]?key|cookie)"
    )
    value = re.sub(
        rf"([\"']?\b{key}\b[\"']?\s*[:=]\s*)([\"'])([\s\S]*?)\2",
        r"\1\2[已脱敏]\2",
        value,
        flags=re.I,
    )
    return re.sub(
        rf"([\"']?\b{key}\b[\"']?\s*[:=]\s*)[^\s,;}}]+",
        r"\1[已脱敏]",
        value,
        flags=re.I,
    )


def prompt_preview(value: str) -> str:
    value = re.sub(
        r"<in-app-browser-context\b[\s\S]*?</in-app-browser-context>",
        " ",
        value,
        flags=re.I,
    )
    value = re.sub(r"^\s*#+\s*My request for Codex:\s*", "", value, flags=re.I)
    value = redact_sensitive_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] or "未记录 Prompt"


def archive(layout: StorageLayout) -> Path | None:
    reply = layout.reply
    if not reply.exists():
        return None
    folder = layout.archive
    ensure_private_directory(folder)
    numbers = []
    for path in folder.glob("reply-*.html"):
        match = re.fullmatch(r"reply-(\d+)\.html", path.name)
        if match:
            numbers.append(int(match.group(1)))
    target = folder / f"reply-{max(numbers, default=0) + 1:04d}.html"
    if not is_within(target.resolve(), folder.resolve()):
        raise SystemExit(f"HTML Reply storage error: archive path escapes its session: {target}")
    try:
        shutil.copy2(reply, target)
        if os.name != "nt":
            target.chmod(0o600)
    except PermissionError as error:
        raise SystemExit(
            "HTML Reply storage error: the external archive is not writable; no repository fallback was used. "
            f"({target})"
        ) from error
    return target


def inject_shell(source: str, data: dict) -> str:
    injection = shell(data)
    if "</body>" in source.lower():
        pos = source.lower().rfind("</body>")
        return source[:pos] + injection + "\n" + source[pos:]
    return source + injection


def load_archive_metadata(layout: StorageLayout) -> dict[str, dict[str, object]]:
    path = layout.archive / ".metadata.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
    return entries if isinstance(entries, dict) else {}


def history_entries(layout: StorageLayout) -> list[dict[str, str]]:
    folder = layout.archive
    replay_folder = layout.replay
    ensure_private_directory(replay_folder)
    metadata = load_archive_metadata(layout)

    def archived_at(path: Path) -> float:
        record = metadata.get(path.name, {})
        if not isinstance(record, dict):
            return path.stat().st_mtime
        try:
            return float(record.get("mtime", path.stat().st_mtime))
        except (TypeError, ValueError):
            return path.stat().st_mtime

    records = []
    entries = []
    for path in sorted(folder.glob("*.html"), key=archived_at, reverse=True):
        source = path.read_text(encoding="utf-8", errors="ignore")
        record = metadata.get(path.name, {})
        stored_prompt = record.get("prompt", "") if isinstance(record, dict) else ""
        prompt = str(stored_prompt).strip() or existing_prompt(source) or "未记录 Prompt（该页面生成于历史功能启用之前）"
        replay_source = rewrite_workspace_urls(
            mark_theme(highlight_code_blocks(strip_history(source))),
            layout.workspace_root,
        )
        replay_path = replay_folder / path.name
        entry = {
            "title": title_of(source, path.stem),
            "prompt": prompt_preview(prompt),
            "path": replay_path.as_uri(),
            "time": datetime.fromtimestamp(archived_at(path)).strftime("%Y-%m-%d %H:%M"),
        }
        entries.append(entry)
        records.append((replay_path, replay_source, entry))
    latest_path = layout.reply.as_uri()
    for replay_path, replay_source, entry in records:
        if not is_within(replay_path.resolve(), replay_folder.resolve()):
            raise SystemExit(f"HTML Reply storage error: replay path escapes its session: {replay_path}")
        replay_data = {
            "workspaceId": layout.workspace_id,
            "session": layout.session,
            "currentPrompt": entry["prompt"],
            "entries": entries,
            "isReplay": True,
            "currentPath": entry["path"],
            "latestPath": latest_path,
            "historyPath": layout.history.as_uri(),
            "revision": hashlib.sha256(replay_source.encode("utf-8")).hexdigest()[:12],
        }
        write_private(replay_path, inject_shell(replay_source, replay_data))
    return entries


def write_history_index(
    layout: StorageLayout,
    prompt: str,
    source: str,
    entries: list[dict[str, str]],
) -> Path:
    target = layout.history
    current = {
        "title": title_of(source, "当前回复"),
        "prompt": prompt_preview(prompt),
        "path": layout.reply.as_uri(),
        "time": "当前回复",
        "current": True,
    }
    records = [current, *entries]
    cards = []
    for item in records:
        title = html.escape(item["title"])
        preview = html.escape(item["prompt"])
        href = html.escape(item["path"], quote=True)
        stamp = html.escape(item["time"])
        current_class = " current" if item.get("current") else ""
        searchable = html.escape(f"{item['title']} {item['prompt']} {item['time']}", quote=True)
        cards.append(
            f'<article class="entry{current_class}" data-search="{searchable}">'
            f'<div><a href="{href}">{title}</a><time>{stamp}</time></div>'
            f'<p>{preview}</p></article>'
        )
    payload = json.dumps(
        {
            "workspaceId": layout.workspace_id,
            "session": layout.session,
            "count": len(records),
            "currentPath": current["path"],
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    page = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>回复历史总览</title>
  <style>
    :root{{--paper:#faf9f5;--paper2:#efe8d6;--ink:#4f4a3c;--muted:#8a8271;--line:#4f4a3c;--accent:#d9a441;--blue:#dce9f4;--green:#dcebd9}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:18px;line-height:1.6}}
    main{{width:calc(100% - 48px);margin:24px auto 56px}}header{{padding:42px 44px;border:2px solid var(--line);border-left:12px solid var(--accent);background:var(--paper2)}}
    h1{{margin:0 0 8px;font-size:clamp(36px,5vw,62px);line-height:1.1}}header p{{margin:0;font-size:20px}}.tools{{display:flex;gap:12px;margin:22px 0}}
    input{{width:100%;min-height:56px;padding:12px 17px;border:2px solid var(--line);border-radius:5px;background:#fff;color:var(--ink);font:600 20px/1.4 inherit}}input::placeholder{{color:#756f62;opacity:1}}
    .entries{{display:grid;gap:12px}}.entry{{padding:20px 22px;border:2px solid var(--line);border-radius:5px;background:#fff}}.entry.current{{border-left:10px solid var(--accent);background:var(--green)}}
    .entry div{{display:flex;align-items:baseline;justify-content:space-between;gap:20px}}.entry a{{color:var(--ink);font-size:23px;font-weight:800;text-decoration:none}}.entry a:hover{{text-decoration:underline}}
    time{{flex:none;color:#756f62;font-size:18px;font-weight:700}}.entry p{{margin:7px 0 0;color:#756f62;font-size:19px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    .empty{{display:none;padding:28px;border:2px solid var(--line);background:var(--blue);font-size:20px;font-weight:750}}
    @media(max-width:700px){{main{{width:calc(100% - 24px);margin:12px auto 32px}}header{{padding:28px 22px}}.entry div{{display:block}}time{{display:block;margin-top:5px}}}}
  </style>
</head>
<body data-html-reply-theme="{THEME_VERSION}">
  <main>
    <header><h1>回复历史总览</h1><p>共 {len(records)} 条。输入标题、问题关键词或时间即可快速查找。</p></header>
    <div class="tools"><input id="history-search" type="search" placeholder="搜索标题、Prompt 或时间…" aria-label="搜索历史回复"></div>
    <section class="entries" id="history-entries">{''.join(cards)}</section>
    <p class="empty" id="history-empty">没有找到匹配的回复。</p>
  </main>
  <script type="application/json" id="html-reply-history-index-data">{payload}</script>
  <script>(()=>{{const input=document.getElementById('history-search');const rows=[...document.querySelectorAll('.entry')];const empty=document.getElementById('history-empty');input.addEventListener('input',()=>{{const q=input.value.trim().toLocaleLowerCase();let shown=0;rows.forEach(row=>{{const ok=!q||row.dataset.search.toLocaleLowerCase().includes(q);row.hidden=!ok;if(ok)shown++}});empty.style.display=shown?'none':'block'}})}})();</script>
</body>
</html>'''
    write_private(target, page)
    return target


def shell(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'''{START}
<style id="html-reply-history-style">
  body[data-html-reply-theme="{THEME_VERSION}"]{{
    --hr-paper:#faf9f5;--hr-paper-2:#efe8d6;--hr-ink:#4f4a3c;--hr-muted:#8a8271;
    --hr-accent:#d9a441;--hr-blue:#dce9f4;--hr-green:#dcebd9;
    margin:0!important;background:var(--hr-paper)!important;color:var(--hr-ink)!important;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif!important;
  }}
  body[data-html-reply-theme="{THEME_VERSION}"] main{{width:calc(100% - 56px)!important;max-width:none!important;margin:28px auto 48px!important}}
  body[data-html-reply-theme="{THEME_VERSION}"] :where(h1,h2,h3,h4,p,li,td,th){{color:inherit}}
  body[data-html-reply-theme="{THEME_VERSION}"] :where(header,section,article,.card,.panel,.metric,.file,.callout,table){{border-radius:5px!important;box-shadow:none!important}}
  body[data-html-reply-theme="{THEME_VERSION}"] :where(a){{color:#315f78}}
  body[data-html-reply-theme="{THEME_VERSION}"] :where(th){{background:var(--hr-paper-2)}}
  pre[data-hr-language]{{position:relative;overflow:auto;padding:46px 24px 24px!important;border:1.5px solid #4f4a3c!important;border-left:9px solid #7ca0b8!important;border-radius:4px!important;background:#202622!important;color:#e9e5d8!important;text-align:left;tab-size:2}}
  pre[data-hr-language]::before{{content:attr(data-hr-language);position:absolute;top:12px;right:16px;color:#b9b3a4;font:800 16px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;letter-spacing:.08em;text-transform:uppercase}}
  body[data-html-reply-theme="{THEME_VERSION}"] pre code{{background:transparent!important;color:inherit!important;padding:0!important;border-radius:0!important}}
  pre[data-hr-language] code{{display:block;font:500 17px/1.65 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;white-space:pre}}
  .hr-tok-key,.hr-tok-property{{color:#91c8ff}}.hr-tok-string{{color:#a8dc95}}.hr-tok-number{{color:#efbd78}}.hr-tok-literal,.hr-tok-keyword{{color:#d8afe9}}.hr-tok-comment{{color:#98a198;font-style:italic}}.hr-tok-tag{{color:#efa98c}}.hr-tok-variable{{color:#f0d27f}}.hr-tok-punct{{color:#cbc5b6}}
  form[data-html-reply-interaction]{{margin:28px 0;padding:24px;border:1.5px solid #4f4a3c;border-radius:5px;background:#fff}}
  form[data-html-reply-interaction] fieldset{{min-width:0;margin:0 0 18px;padding:18px;border:1.5px solid #4f4a3c;border-radius:5px;background:#faf9f5}}
  form[data-html-reply-interaction] legend{{padding:0 8px;font-size:20px;font-weight:800}}
  form[data-html-reply-interaction] label{{display:flex;align-items:flex-start;gap:10px;margin:10px 0;font-size:18px;line-height:1.55;cursor:pointer}}
  form[data-html-reply-interaction] :where(input[type="radio"],input[type="checkbox"]){{width:20px;height:20px;margin-top:4px;accent-color:#d9a441}}
  form[data-html-reply-interaction] :where(input[type="text"],textarea,select){{box-sizing:border-box;width:100%;margin-top:8px;padding:12px 14px;border:1.5px solid #4f4a3c;border-radius:4px;background:#fff;color:#4f4a3c;font:500 18px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
  form[data-html-reply-interaction] textarea{{min-height:120px;resize:vertical}}
  form[data-html-reply-interaction] button[type="submit"]{{display:none}}
  [data-interaction-status]{{min-height:28px;margin:12px 0 0;color:#315f78;font-size:17px;line-height:1.55}}
  #hr-history-button{{position:fixed;right:18px;top:18px;z-index:2147483000;min-height:44px;padding:10px 15px;border:1.5px solid #4f4a3c;border-radius:5px;background:#d9a441;color:#4f4a3c;font:800 16px/1 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;letter-spacing:.04em;cursor:pointer}}
  #hr-history-backdrop{{position:fixed;inset:0;z-index:2147483001;display:none;background:rgba(30,28,23,.34)}}
  #hr-history-backdrop.open{{display:block}}
  #hr-history-drawer{{position:absolute;inset:0 auto 0 0;width:min(390px,88vw);display:flex;flex-direction:column;border-right:2px solid #4f4a3c;background:#faf9f5;color:#4f4a3c;box-shadow:12px 0 30px rgba(40,35,25,.12)}}
  .hr-head{{display:flex;align-items:center;justify-content:space-between;padding:22px;border-bottom:1.5px solid #4f4a3c;background:#efe8d6}}.hr-head b{{font:800 20px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}.hr-close{{border:1.5px solid #4f4a3c;border-radius:4px;background:#faf9f5;color:#4f4a3c;font-size:20px;cursor:pointer}}
  #hr-latest-link{{display:none;margin:12px 10px 2px;padding:13px 14px;border:1.5px solid #4f4a3c;border-radius:5px;background:#efe8d6;color:#4f4a3c;text-decoration:none;font:800 17px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
  #hr-history-page{{display:block;margin:12px 10px 2px;padding:13px 14px;border:1.5px solid #4f4a3c;border-radius:5px;background:#dcebd9;color:#4f4a3c;text-decoration:none;font:800 17px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
  #hr-history-list{{overflow:auto;padding:10px}}.hr-item{{display:block;width:100%;margin:0 0 8px;padding:15px 14px;border:1.5px solid #4f4a3c;border-radius:5px;background:#fff;text-align:left;color:#4f4a3c;text-decoration:none;cursor:pointer}}.hr-item[aria-current="page"]{{background:#dce9f4}}.hr-item b{{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:800 17px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
  @media(max-width:700px){{body[data-html-reply-theme="{THEME_VERSION}"] main{{width:calc(100% - 24px)!important;margin:12px auto 32px!important}}#hr-history-button{{right:8px;top:8px}}}}
</style>
<button id="hr-history-button" type="button" aria-label="打开历史回复">历史</button>
<div id="hr-history-backdrop"><aside id="hr-history-drawer" aria-label="历史回复目录"><div class="hr-head"><b>回复历史</b><button class="hr-close" id="hr-drawer-close" type="button">×</button></div><a id="hr-history-page" href="#">打开完整历史总览 →</a><a id="hr-latest-link" href="#">← 返回最新回复</a><div id="hr-history-list"></div></aside></div>
<script type="application/json" id="html-reply-history-data">{payload}</script>
<script id="html-reply-history-script">(()=>{{const data=JSON.parse(document.getElementById('html-reply-history-data').textContent);const back=document.getElementById('hr-history-backdrop');const list=document.getElementById('hr-history-list');const trigger=document.getElementById('hr-history-button');const latest=document.getElementById('hr-latest-link');document.getElementById('hr-history-page').href=data.historyPath;trigger.onclick=()=>back.classList.add('open');document.getElementById('hr-drawer-close').onclick=()=>back.classList.remove('open');back.onclick=e=>{{if(e.target===back)back.classList.remove('open')}};document.addEventListener('keydown',e=>{{if(e.key==='Escape')back.classList.remove('open')}});if(data.isReplay&&data.latestPath){{latest.href=data.latestPath;latest.style.display='block'}};(data.entries||[]).forEach(item=>{{const a=document.createElement('a');a.className='hr-item';a.href=item.path;a.innerHTML='<b></b>';a.querySelector('b').textContent=item.title;if(data.currentPath===item.path)a.setAttribute('aria-current','page');list.appendChild(a)}});
const collect=form=>{{const answers=[];const seen=new Set();form.querySelectorAll('[name]').forEach(control=>{{if(seen.has(control.name)||control.disabled)return;seen.add(control.name);const group=[...form.querySelectorAll('[name="'+CSS.escape(control.name)+'"]')];let value='';if(control.type==='radio')value=(group.find(item=>item.checked)||{{}}).value||'';else if(control.type==='checkbox')value=group.filter(item=>item.checked).map(item=>item.value);else value=control.value;const owner=control.closest('[data-question]');answers.push({{id:control.name,question:(control.dataset.question||(owner&&owner.dataset.question)||control.name).trim(),answer:value}})}});return answers.filter(item=>Array.isArray(item.answer)?item.answer.length:String(item.answer).trim())}};
document.querySelectorAll('form[data-html-reply-interaction]').forEach(form=>{{let status=form.querySelector('[data-interaction-status]');if(!status){{status=document.createElement('p');status.setAttribute('data-interaction-status','');form.appendChild(status)}}if(data.isReplay){{form.querySelectorAll('input,textarea,select,button').forEach(control=>control.disabled=true);status.textContent='这是历史回复，只能查看；请返回最新回复继续回答。';return}}const formId=form.dataset.interactionId||form.id||'default';const key='html-reply:'+(data.workspaceId||'legacy')+':'+data.session+':'+formId;try{{const draft=JSON.parse(localStorage.getItem(key)||'{{}}');form.querySelectorAll('[name]').forEach(control=>{{const value=draft[control.name];if(value===undefined)return;if(control.type==='radio')control.checked=control.value===value;else if(control.type==='checkbox')control.checked=Array.isArray(value)&&value.includes(control.value);else control.value=value}})}}catch(_e){{}}
const exportAnswers=()=>{{const answers=collect(form);const draft={{}};answers.forEach(item=>draft[item.id]=item.answer);try{{localStorage.setItem(key,JSON.stringify(draft))}}catch(_e){{}}if(!answers.length){{status.textContent='等待回答…';return}}const payload={{version:1,workspaceId:data.workspaceId||'',session:data.session,pageTitle:document.title,revision:data.revision||'',submittedAt:new Date().toISOString(),answers}};const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='html-reply-response-'+data.session+'.json';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='回答已保存，并导出为当前 Session 的 JSON 文件。'}};
form.addEventListener('submit',event=>{{event.preventDefault();exportAnswers()}});form.addEventListener('change',exportAnswers);form.addEventListener('blur',event=>{{if(event.target.matches('textarea,input[type="text"]'))exportAnswers()}},true);status.textContent='回答会自动保存；文本输入在离开输入框时保存。'}});}})();</script>
{END}'''


def finalize(layout: StorageLayout, prompt: str) -> Path:
    reply = layout.reply
    if not reply.exists():
        raise SystemExit(f"missing {reply}")
    source = rewrite_workspace_urls(
        mark_theme(highlight_code_blocks(strip_history(reply.read_text(encoding="utf-8", errors="ignore")))),
        layout.workspace_root,
    )
    prompt = prompt_preview(prompt)
    entries = history_entries(layout)
    history = write_history_index(layout, prompt, source, entries)
    data = {
        "workspaceId": layout.workspace_id,
        "session": layout.session,
        "currentPrompt": prompt,
        "entries": entries,
        "historyPath": history.as_uri(),
        "revision": hashlib.sha256(source.encode("utf-8")).hexdigest()[:12],
    }
    source = inject_shell(source, data)
    write_private(reply, source)
    state = {
        "version": 1,
        "workspaceId": layout.workspace_id,
        "session": layout.session,
        "reply": layout.reply.as_uri(),
        "history": layout.history.as_uri(),
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_private(layout.state, json.dumps(state, ensure_ascii=False, indent=2))
    return reply


def migrate_legacy(layout: StorageLayout, shared: bool = False) -> Path:
    """Copy old workspace history without deleting or overwriting its source."""
    old_output = layout.workspace_root / "output"
    source_session = "legacy" if shared else layout.session
    old_reply = old_output / ("reply.html" if shared else f"reply-{layout.session}.html")
    old_archive = old_output / "archive" / "html-reply" / source_session
    marker = layout.session_dir / "legacy-migration.json"
    if marker.is_file():
        return marker
    archive_sources = (
        sorted(
            path
            for path in old_archive.glob("reply-*.html")
            if re.fullmatch(r"reply-\d+\.html", path.name)
        )
        if old_archive.is_dir()
        else []
    )
    if not old_reply.is_file() and not archive_sources:
        raise SystemExit(
            f"HTML Reply migration error: no legacy files found for source {source_session} under {old_output}"
        )
    if not old_reply.is_file():
        raise SystemExit("HTML Reply migration error: the legacy stable reply is missing; nothing was copied")
    if layout.session_dir.exists():
        raise SystemExit(
            "HTML Reply migration error: the external session already contains replies; refusing to overwrite it"
        )

    # Validate and decode every source before the first destination write so a
    # malformed later archive cannot strand a half-migrated session.
    old_source = old_reply.read_text(encoding="utf-8", errors="strict")
    prompt = existing_prompt(old_source)
    archive_payloads = []
    for source_path in archive_sources:
        source = source_path.read_text(encoding="utf-8", errors="strict")
        stat = source_path.stat()
        archive_payloads.append({
            "path": source_path,
            "source": source,
            "prompt": prompt_preview(existing_prompt(source)),
            "atime_ns": stat.st_atime_ns,
            "mtime_ns": stat.st_mtime_ns,
        })

    try:
        prepare_storage(layout)
        write_private(
            layout.reply,
            rewrite_workspace_urls(strip_history(old_source), layout.workspace_root),
        )
        archive_metadata: dict[str, dict[str, object]] = {}
        copied = []
        for item in archive_payloads:
            source_path = item["path"]
            assert isinstance(source_path, Path)
            target = layout.archive / source_path.name
            write_private(
                target,
                rewrite_workspace_urls(strip_history(str(item["source"])), layout.workspace_root),
            )
            os.utime(target, ns=(int(item["atime_ns"]), int(item["mtime_ns"])))
            archive_metadata[source_path.name] = {
                "prompt": item["prompt"],
                "mtime": int(item["mtime_ns"]) / 1_000_000_000,
            }
            copied.append(source_path.name)
        if archive_metadata:
            write_private(
                layout.archive / ".metadata.json",
                json.dumps({"version": 1, "entries": archive_metadata}, ensure_ascii=False, indent=2),
            )
        finalize(layout, prompt)
        migration = {
            "version": 1,
            "source": str(old_output),
            "sourceFormat": "shared" if shared else "session",
            "sourcePreserved": True,
            "reply": old_reply.name,
            "archives": copied,
            "migratedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        write_private(marker, json.dumps(migration, ensure_ascii=False, indent=2))
    except BaseException:
        if layout.session_dir.exists() and is_within(layout.session_dir.resolve(), layout.data_root):
            try:
                shutil.rmtree(layout.session_dir)
            except OSError:
                pass
        raise
    return marker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("path", "archive", "finalize", "migrate", "migrate-shared"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--data-dir", default="")
    parser.add_argument(
        "--session",
        default="",
        help="Compatibility override outside Codex; must match CODEX_THREAD_ID inside Codex",
    )
    parser.add_argument("--prompt", default="")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    session = current_thread_session(args.session)
    layout = storage_layout(root, session, args.data_dir or None)
    if args.action == "path":
        result = layout.reply
    elif args.action == "archive":
        result = archive(layout)
    elif args.action in {"migrate", "migrate-shared"}:
        result = migrate_legacy(layout, shared=args.action == "migrate-shared")
        print(
            "HTML Reply migration warning: the legacy workspace output was preserved and may still be committed; "
            "review it before manual cleanup.",
            file=sys.stderr,
        )
    else:
        result = finalize(layout, args.prompt)
    if result:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
