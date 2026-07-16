#!/usr/bin/env python3
"""Archive reply.html and inject a prompt-aware history drawer into the current page."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


START = "<!-- HTML_REPLY_HISTORY_START -->"
END = "<!-- HTML_REPLY_HISTORY_END -->"
DATA_RE = re.compile(r'<script type="application/json" id="html-reply-history-data">([\s\S]*?)</script>')
TITLE_RE = re.compile(r"<title>([\s\S]*?)</title>", re.I)


def strip_history(source: str) -> str:
    return re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), "", source)


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
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return value or "local"


def reply_path(root: Path, session: str) -> Path:
    session = safe_session(session)
    return root / "output" / ("reply.html" if session == "legacy" else f"reply-{session}.html")


def archive(root: Path, session: str) -> Path | None:
    reply = reply_path(root, session)
    if not reply.exists():
        return None
    folder = root / "output" / "archive" / "html-reply" / safe_session(session)
    folder.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in folder.glob("reply-*.html"):
        match = re.fullmatch(r"reply-(\d+)\.html", path.name)
        if match:
            numbers.append(int(match.group(1)))
    target = folder / f"reply-{max(numbers, default=0) + 1:04d}.html"
    shutil.copy2(reply, target)
    return target


def history_entries(root: Path, session: str) -> list[dict[str, str]]:
    output = root / "output"
    folder = output / "archive" / "html-reply" / safe_session(session)
    replay_folder = folder / ".replay"
    replay_folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for path in sorted(folder.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        source = path.read_text(encoding="utf-8", errors="ignore")
        prompt = existing_prompt(source) or "未记录 Prompt（该页面生成于历史功能启用之前）"
        replay_source = strip_history(source)
        if not re.search(r"<base\b", replay_source, re.I):
            replay_source = re.sub(r"(<head\b[^>]*>)", r'\1\n<base href="../">', replay_source, count=1, flags=re.I)
        replay_path = replay_folder / path.name
        replay_path.write_text(replay_source, encoding="utf-8")
        entries.append({
            "title": title_of(source, path.stem),
            "prompt": prompt,
            "path": replay_path.relative_to(output).as_posix(),
            "time": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return entries


def shell(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'''{START}
<style id="html-reply-history-style">
  #hr-history-button{{position:fixed;left:14px;top:50%;z-index:2147483000;transform:translateY(-50%);padding:14px 9px;border:1.5px solid #4f4a3c;border-radius:5px;background:#d9a441;color:#4f4a3c;font:800 16px/1 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;writing-mode:vertical-rl;letter-spacing:.12em;cursor:pointer}}
  #hr-history-backdrop{{position:fixed;inset:0;z-index:2147483001;display:none;background:rgba(30,28,23,.34)}}
  #hr-history-backdrop.open{{display:block}}
  #hr-history-drawer{{position:absolute;inset:0 auto 0 0;width:min(390px,88vw);display:flex;flex-direction:column;border-right:2px solid #4f4a3c;background:#faf9f5;color:#4f4a3c;box-shadow:12px 0 30px rgba(40,35,25,.12)}}
  .hr-head{{display:flex;align-items:center;justify-content:space-between;padding:22px;border-bottom:1.5px solid #4f4a3c;background:#efe8d6}}.hr-head b{{font:800 20px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}.hr-close{{border:1.5px solid #4f4a3c;border-radius:4px;background:#faf9f5;color:#4f4a3c;font-size:20px;cursor:pointer}}
  .hr-current{{padding:16px 20px;border-bottom:1.5px solid #4f4a3c;background:#dcebd9;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}.hr-current b{{display:block;margin-bottom:5px}}
  #hr-history-list{{overflow:auto;padding:10px}}.hr-item{{display:block;width:100%;margin:0 0 8px;padding:13px 14px;border:1.5px solid #4f4a3c;border-radius:5px;background:#fff;text-align:left;color:#4f4a3c;cursor:pointer}}.hr-item b{{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:800 17px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}.hr-item span{{display:block;margin-top:5px;color:#817968;font:16px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
  #hr-history-viewer{{position:fixed;inset:22px;z-index:2147483002;display:none;grid-template-rows:auto minmax(0,1fr);border:2px solid #4f4a3c;border-radius:6px;background:#faf9f5;overflow:hidden}}#hr-history-viewer.open{{display:grid}}.hr-view-head{{padding:18px 22px;border-bottom:2px solid #4f4a3c;background:#efe8d6}}.hr-view-row{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}}.hr-view-head b{{font:800 16px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;letter-spacing:.1em}}#hr-history-prompt{{margin:10px 0 0;max-height:24vh;overflow:auto;white-space:pre-wrap;font:18px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}#hr-history-frame{{width:100%;height:100%;border:0;background:#faf9f5}}
  @media(max-width:700px){{#hr-history-viewer{{inset:8px}}#hr-history-button{{left:5px}}}}
</style>
<button id="hr-history-button" type="button" aria-label="打开历史回复">历史</button>
<div id="hr-history-backdrop"><aside id="hr-history-drawer" aria-label="历史回复目录"><div class="hr-head"><b>回复历史</b><button class="hr-close" id="hr-drawer-close" type="button">×</button></div><div class="hr-current"><b>本轮 Prompt</b><span id="hr-current-prompt"></span></div><div id="hr-history-list"></div></aside></div>
<div id="hr-history-viewer"><div class="hr-view-head"><div class="hr-view-row"><b>用户 Prompt</b><button class="hr-close" id="hr-view-close" type="button">×</button></div><p id="hr-history-prompt"></p></div><iframe id="hr-history-frame" title="历史 HTML 原文"></iframe></div>
<script type="application/json" id="html-reply-history-data">{payload}</script>
<script id="html-reply-history-script">(()=>{{const chromeIds=['hr-history-button','hr-history-backdrop','hr-history-viewer'];const hideEmbeddedChrome=doc=>{{try{{chromeIds.forEach(id=>doc.getElementById(id)?.remove())}}catch(_error){{}}}};if(new URLSearchParams(location.search).get('html-reply-embedded')==='1'){{hideEmbeddedChrome(document);return}}const data=JSON.parse(document.getElementById('html-reply-history-data').textContent);const back=document.getElementById('hr-history-backdrop');const viewer=document.getElementById('hr-history-viewer');const frame=document.getElementById('hr-history-frame');const list=document.getElementById('hr-history-list');const trigger=document.getElementById('hr-history-button');document.getElementById('hr-current-prompt').textContent=data.currentPrompt||'未记录';trigger.onclick=()=>back.classList.add('open');document.getElementById('hr-drawer-close').onclick=()=>back.classList.remove('open');back.onclick=e=>{{if(e.target===back)back.classList.remove('open')}};frame.onload=()=>hideEmbeddedChrome(frame.contentDocument);document.getElementById('hr-view-close').onclick=()=>{{viewer.classList.remove('open');frame.src='about:blank';trigger.style.display=''}};(data.entries||[]).forEach(item=>{{const b=document.createElement('button');b.className='hr-item';b.innerHTML='<b></b><span></span>';b.querySelector('b').textContent=item.title;b.querySelector('span').textContent=item.time+' · '+item.prompt.replace(/\s+/g,' ').slice(0,80);b.onclick=()=>{{document.getElementById('hr-history-prompt').textContent=item.prompt;frame.src=item.path+(item.path.includes('?')?'&':'?')+'html-reply-embedded=1';trigger.style.display='none';viewer.classList.add('open');back.classList.remove('open')}};list.appendChild(b)}});}})();</script>
{END}'''


def finalize(root: Path, session: str, prompt: str) -> Path:
    reply = reply_path(root, session)
    if not reply.exists():
        raise SystemExit(f"missing {reply}")
    source = strip_history(reply.read_text(encoding="utf-8", errors="ignore"))
    if not prompt.strip():
        state = root / "output" / ".html-reply" / "sessions" / f"{safe_session(session)}.json"
        try:
            prompt = str(json.loads(state.read_text(encoding="utf-8")).get("prompt", ""))
        except Exception:
            prompt = ""
    data = {
        "session": safe_session(session),
        "currentPrompt": prompt.strip() or "未记录",
        "entries": history_entries(root, session),
    }
    injection = shell(data)
    if "</body>" in source.lower():
        pos = source.lower().rfind("</body>")
        source = source[:pos] + injection + "\n" + source[pos:]
    else:
        source += injection
    reply.write_text(source, encoding="utf-8")
    return reply


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("path", "archive", "finalize"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--session", default="legacy")
    parser.add_argument("--prompt", default="")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if args.action == "path":
        result = reply_path(root, args.session)
    elif args.action == "archive":
        result = archive(root, args.session)
    else:
        result = finalize(root, args.session, args.prompt)
    if result:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
