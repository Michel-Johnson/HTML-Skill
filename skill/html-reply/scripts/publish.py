#!/usr/bin/env python3
"""Publish one session-scoped HTML body fragment as a complete HTML Reply."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import reply_history


FORBIDDEN_DOCUMENT_TAGS = re.compile(r"<!doctype\b|<(?:html|head|body|style|script)\b", re.I)
TITLE_RE = re.compile(r"<h1\b[^>]*>([\s\S]*?)</h1>", re.I)
SUMMARY_RE = re.compile(
    r"<(?P<tag>[a-z][\w-]*)\b(?=[^>]*\bdata-html-reply-summary(?:\s*=|\s|>))[^>]*>"
    r"(?P<body>[\s\S]*?)</(?P=tag)>",
    re.I,
)


def plain_text(source: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", source))).strip()


def draft_path(root: Path, session: str) -> Path:
    return root / "output" / ".html-reply" / "drafts" / f"reply-{reply_history.safe_session(session)}.html"


def fragment_metadata(fragment: str) -> tuple[str, str]:
    if FORBIDDEN_DOCUMENT_TAGS.search(fragment):
        raise SystemExit(
            "HTML Reply publish error: the draft must be a body fragment; "
            "remove doctype/html/head/body/style/script boilerplate"
        )
    title_match = TITLE_RE.search(fragment)
    summary_match = SUMMARY_RE.search(fragment)
    title = plain_text(title_match.group(1)) if title_match else ""
    summary = plain_text(summary_match.group("body")) if summary_match else ""
    if not title:
        raise SystemExit("HTML Reply publish error: the draft needs one visible <h1>")
    if not summary:
        raise SystemExit(
            "HTML Reply publish error: the draft needs one visible element marked data-html-reply-summary"
        )
    return title, summary


def render_shell(skill_root: Path, title: str, fragment: str) -> str:
    template = (skill_root / "assets" / "fragment-shell.html").read_text(encoding="utf-8")
    if template.count("__HTML_REPLY_TITLE__") != 1 or template.count("__HTML_REPLY_FRAGMENT__") != 1:
        raise SystemExit("HTML Reply publish error: invalid fragment-shell.html placeholders")
    return template.replace("__HTML_REPLY_TITLE__", html.escape(title)).replace(
        "__HTML_REPLY_FRAGMENT__", fragment.strip()
    )


def publish(root: Path, requested_session: str = "", prompt: str = "") -> dict[str, str]:
    session = reply_history.current_thread_session(requested_session)
    draft = draft_path(root, session)
    if not draft.is_file():
        raise SystemExit(f"HTML Reply publish error: missing session draft {draft}")
    fragment = draft.read_text(encoding="utf-8", errors="strict")
    title, summary = fragment_metadata(fragment)
    page = render_shell(Path(__file__).resolve().parents[1], title, fragment)

    archived = reply_history.archive(root, session)
    reply = reply_history.reply_path(root, session)
    reply.parent.mkdir(parents=True, exist_ok=True)
    reply.write_text(page, encoding="utf-8")
    reply_history.finalize(root, session, prompt)

    finalized = reply.read_text(encoding="utf-8", errors="ignore")
    if f'data-html-reply-theme="{reply_history.THEME_VERSION}"' not in finalized:
        raise SystemExit("HTML Reply publish error: final page is missing the canonical theme")
    if plain_text(summary) not in plain_text(finalized):
        raise SystemExit("HTML Reply publish error: visible summary was lost during finalization")
    history = reply_history.history_path(root, session)
    if not history.is_file():
        raise SystemExit("HTML Reply publish error: history index was not created")
    return {
        "session": session,
        "summary": summary,
        "draft": str(draft),
        "reply": str(reply),
        "history": str(history),
        "archived": str(archived) if archived else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an HTML Reply body fragment")
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--session",
        default="",
        help="Compatibility override outside Codex; must match CODEX_THREAD_ID inside Codex",
    )
    parser.add_argument("--prompt", default="")
    args = parser.parse_args()
    result = publish(Path(args.root).expanduser().resolve(), args.session, args.prompt)
    # Keep stdout ASCII-safe because Windows runners may expose a legacy
    # console encoding even when the fragment and summary contain Unicode.
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
