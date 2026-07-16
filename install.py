#!/usr/bin/env python3
"""Install HTML Reply for Codex on macOS or Windows without replacing user config."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


REPOSITORY = "Michel-Johnson/HTML-Skill"
SKILL_NAME = "html-reply"
BLOCK_START = "<!-- html-reply:managed:start -->"
BLOCK_END = "<!-- html-reply:managed:end -->"
GUIDANCE = f"""{BLOCK_START}
## HTML Reply

- Deliver every substantive final answer through the global `html-reply` Skill.
- Keep one stable `output/reply-<session-id>.html` file per Codex session.
- The final chat message must repeat the page's concise summary sentence and link the session HTML.
{BLOCK_END}"""


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def command_line(parts: list[str], platform: str | None = None) -> str:
    target = platform or sys.platform
    return subprocess.list2cmdline(parts) if target == "win32" else shlex.join(parts)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.html-reply.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    target = path.with_name(f"{path.name}.backup-{timestamp()}")
    shutil.copy2(path, target)
    return target


def download_source(repository: str) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(prefix="html-reply-install-")
    archive = Path(holder.name) / "source.zip"
    url = f"https://github.com/{repository}/archive/refs/heads/main.zip"
    print(f"Downloading {repository}...")
    with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    extracted = Path(holder.name) / "source"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    matches = list(extracted.glob(f"*/skill/{SKILL_NAME}/SKILL.md"))
    if len(matches) != 1:
        holder.cleanup()
        raise RuntimeError("Downloaded repository does not contain skill/html-reply/SKILL.md")
    return matches[0].parent, holder


def resolve_source(explicit: str | None, repository: str) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if explicit:
        source = Path(explicit).expanduser().resolve()
        if (source / "SKILL.md").is_file():
            return source, None
        nested = source / "skill" / SKILL_NAME
        if (nested / "SKILL.md").is_file():
            return nested, None
        raise RuntimeError(f"No HTML Reply skill found under {source}")
    script_root = Path(__file__).resolve().parent
    local = script_root / "skill" / SKILL_NAME
    if (local / "SKILL.md").is_file():
        return local, None
    return download_source(repository)


def is_managed_hook(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks", [])
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command", "")).replace("\\", "/").lower()
        if "/html-reply/scripts/" in command and (
            "prompt_hook.py" in command or "stop_hook.py" in command
        ):
            return True
    return False


def managed_hook_entries(skill_dir: Path, python_executable: Path) -> dict[str, dict[str, object]]:
    scripts = skill_dir / "scripts"
    prompt = str(scripts / "prompt_hook.py")
    stop = str(scripts / "stop_hook.py")
    python = str(python_executable)
    return {
        "SessionStart": {
            "matcher": "startup|resume|clear|compact",
            "hooks": [{
                "type": "command",
                "command": command_line([python, prompt, "SessionStart"]),
                "timeout": 10,
                "statusMessage": "Loading HTML Reply",
            }],
        },
        "UserPromptSubmit": {
            "hooks": [{
                "type": "command",
                "command": command_line([python, prompt]),
                "timeout": 10,
                "statusMessage": "Requiring HTML Reply delivery",
            }],
        },
        "Stop": {
            "hooks": [{
                "type": "command",
                "command": command_line([python, stop]),
                "timeout": 10,
                "statusMessage": "Enforcing HTML Reply delivery",
            }],
        },
    }


def load_hooks(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"hooks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(f"Cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError(f"{path}: 'hooks' must be a JSON object")
    return data


def merge_hooks(path: Path, skill_dir: Path, python_executable: Path) -> None:
    data = load_hooks(path)
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    for event, managed in managed_hook_entries(skill_dir, python_executable).items():
        current = hooks.get(event, [])
        if not isinstance(current, list):
            raise RuntimeError(f"{path}: hooks.{event} must be an array")
        hooks[event] = [entry for entry in current if not is_managed_hook(entry)] + [managed]
    backup(path)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def update_guidance(path: Path) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    start = existing.find(BLOCK_START)
    end = existing.find(BLOCK_END)
    if start >= 0 and end >= start:
        end += len(BLOCK_END)
        updated = existing[:start].rstrip() + "\n\n" + GUIDANCE + existing[end:]
    else:
        updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + GUIDANCE + "\n"
    backup(path)
    atomic_write(path, updated)


def install_skill(source: Path, destination: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / f".{SKILL_NAME}.stage-{timestamp()}"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(source, stage)
    previous = None
    if destination.exists():
        previous = destination.parent / f"{SKILL_NAME}.backup-{timestamp()}"
        destination.rename(previous)
    stage.rename(destination)
    return previous


def write_legacy_shims(legacy_dir: Path, skill_dir: Path) -> None:
    """Keep already-running sessions alive without exposing a duplicate SKILL.md."""
    scripts = legacy_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("prompt_hook.py", "reply_history.py", "stop_hook.py"):
        target = skill_dir / "scripts" / name
        wrapper = (
            "#!/usr/bin/env python3\n"
            "import runpy\n"
            f"runpy.run_path({str(target)!r}, run_name='__main__')\n"
        )
        atomic_write(scripts / name, wrapper)


def verify(codex_home: Path, skill_dir: Path) -> list[str]:
    problems: list[str] = []
    required = [
        skill_dir / "SKILL.md",
        skill_dir / "scripts" / "prompt_hook.py",
        skill_dir / "scripts" / "stop_hook.py",
        skill_dir / "scripts" / "reply_history.py",
    ]
    problems.extend(f"missing {path}" for path in required if not path.is_file())
    hooks_path = codex_home / "hooks.json"
    try:
        hooks = load_hooks(hooks_path).get("hooks", {})
        for event in ("SessionStart", "UserPromptSubmit", "Stop"):
            entries = hooks.get(event, []) if isinstance(hooks, dict) else []
            if sum(1 for entry in entries if is_managed_hook(entry)) != 1:
                problems.append(f"hooks.{event} does not contain exactly one HTML Reply hook")
    except RuntimeError as error:
        problems.append(str(error))
    agents = codex_home / "AGENTS.md"
    if not agents.exists() or BLOCK_START not in agents.read_text(encoding="utf-8"):
        problems.append(f"managed guidance is missing from {agents}")
    return problems


def remove_managed_hooks(path: Path) -> None:
    if not path.exists():
        return
    data = load_hooks(path)
    hooks = data.get("hooks", {})
    assert isinstance(hooks, dict)
    for event, entries in list(hooks.items()):
        if isinstance(entries, list):
            hooks[event] = [entry for entry in entries if not is_managed_hook(entry)]
    backup(path)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def remove_guidance(path: Path) -> None:
    if not path.exists():
        return
    source = path.read_text(encoding="utf-8")
    start, end = source.find(BLOCK_START), source.find(BLOCK_END)
    if start < 0 or end < start:
        return
    backup(path)
    end += len(BLOCK_END)
    atomic_write(path, (source[:start].rstrip() + "\n\n" + source[end:].lstrip()).strip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install HTML Reply for Codex")
    parser.add_argument("--source", help="Local repository or skill directory; otherwise download GitHub main")
    parser.add_argument("--repository", default=REPOSITORY, help="GitHub owner/repository used for remote install")
    parser.add_argument("--codex-home", help="Override CODEX_HOME")
    parser.add_argument("--skills-home", help="Override the user skill directory")
    parser.add_argument("--check", action="store_true", help="Only verify the current installation")
    parser.add_argument("--uninstall", action="store_true", help="Remove HTML Reply-managed files and hook entries")
    args = parser.parse_args()

    codex_home = Path(args.codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    skills_home = Path(args.skills_home or Path.home() / ".agents" / "skills").expanduser().resolve()
    skill_dir = skills_home / SKILL_NAME
    legacy_skill_dir = codex_home / "skills" / SKILL_NAME
    hooks_path, agents_path = codex_home / "hooks.json", codex_home / "AGENTS.md"

    if args.uninstall:
        remove_managed_hooks(hooks_path)
        remove_guidance(agents_path)
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        if legacy_skill_dir.exists() and not (legacy_skill_dir / "SKILL.md").exists():
            shutil.rmtree(legacy_skill_dir)
        print("HTML Reply removed. Existing user hooks and guidance were preserved.")
        return 0

    if args.check:
        problems = verify(codex_home, skill_dir)
        if problems:
            print("HTML Reply check failed:", file=sys.stderr)
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            return 1
        print("HTML Reply is installed correctly.")
        return 0

    source, holder = resolve_source(args.source, args.repository)
    try:
        codex_home.mkdir(parents=True, exist_ok=True)
        previous = install_skill(source, skill_dir)
        merge_hooks(hooks_path, skill_dir, Path(sys.executable).resolve())
        update_guidance(agents_path)
        problems = verify(codex_home, skill_dir)
        if problems:
            raise RuntimeError("; ".join(problems))
        legacy_backup = None
        had_legacy = legacy_skill_dir.exists() or any(legacy_skill_dir.parent.glob(f"{SKILL_NAME}.legacy-backup-*"))
        if legacy_skill_dir.exists() and legacy_skill_dir.resolve() != skill_dir.resolve():
            legacy_backup = legacy_skill_dir.parent / f"{SKILL_NAME}.legacy-backup-{timestamp()}"
            legacy_skill_dir.rename(legacy_backup)
        if had_legacy:
            write_legacy_shims(legacy_skill_dir, skill_dir)
    finally:
        if holder:
            holder.cleanup()

    print(f"Installed HTML Reply to {skill_dir}")
    print(f"Updated Codex hooks at {hooks_path}")
    if previous:
        print(f"Previous skill backed up to {previous}")
    if legacy_backup:
        print(f"Legacy CODEX_HOME skill migrated to {legacy_backup}")
    if legacy_skill_dir.exists():
        print(f"Legacy hook compatibility shims kept at {legacy_skill_dir / 'scripts'}")
    print("Restart Codex or open a new session to activate it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
