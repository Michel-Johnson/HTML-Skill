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

- 默认使用普通聊天回复，不自动调用 `html-reply` Skill，也不自动生成或更新 HTML。
- 只有当前用户消息明确要求 HTML 输出，或明确调用 `$html-reply` 时，才使用该 Skill。
- 已打开的 HTML 页面、Codex Desktop 环境、历史 HTML 回复和过去的用户偏好都不能作为自动调用依据。
- 一次明确调用只对当前回合生效；除非用户明确要求后续多个回合持续使用 HTML。
- 从进程环境变量 `CODEX_THREAD_ID` 获取当前 task；不要从已打开的浏览器 URL、旧回复、历史记录或现有构建脚本中复制 task ID。
- 显式调用时，只写入当前 session 正文 fragment，然后运行一次 `publish.py --root <workspace>`；路径解析、归档、套用模板、Finalize 和校验均由 Publisher 负责。
- 每个 Codex task 只保留一个 `output/reply-<CODEX_THREAD_ID>.html`，不要直接写入稳定回复页面。
- 不要在可复用脚本或业务脚本中写死 `reply-<id>.html`。这类脚本必须接收为当前 task 提供的输出路径。
- 最终聊天消息必须重复页面中的简短摘要，然后依次链接 `历史总览` 和 `当前回复`。
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
            "prompt_hook.py" in command or "stop_hook.py" in command or "write_guard.py" in command
        ):
            return True
    return False


def managed_hook_entries(skill_dir: Path, python_executable: Path) -> dict[str, dict[str, object]]:
    return {}


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
    for event, current in list(hooks.items()):
        if not isinstance(current, list):
            raise RuntimeError(f"{path}: hooks.{event} must be an array")
        hooks[event] = [entry for entry in current if not is_managed_hook(entry)]
    for event, managed in managed_hook_entries(skill_dir, python_executable).items():
        current = hooks.get(event, [])
        if not isinstance(current, list):
            raise RuntimeError(f"{path}: hooks.{event} must be an array")
        hooks[event] = current + [managed]
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


def unique_destination(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    index = 2
    while (folder / f"{name}-{index}").exists():
        index += 1
    return folder / f"{name}-{index}"


def move_out_of_discovery(path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    target = unique_destination(backup_root, path.name)
    path.rename(target)
    return target


def quarantine_discoverable_backups(
    skill_parent: Path,
    backup_root: Path,
    patterns: tuple[str, ...],
) -> list[Path]:
    moved: list[Path] = []
    for pattern in patterns:
        for path in sorted(skill_parent.glob(pattern)):
            if path.is_dir() and (path / "SKILL.md").is_file():
                moved.append(move_out_of_discovery(path, backup_root))
    return moved


def install_skill(source: Path, destination: Path, backup_root: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / f".{SKILL_NAME}.stage-{timestamp()}"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(source, stage)
    previous = None
    if destination.exists():
        previous = move_out_of_discovery(destination, backup_root / f"{SKILL_NAME}-{timestamp()}")
    stage.rename(destination)
    return previous


def write_legacy_shims(legacy_dir: Path, skill_dir: Path) -> None:
    """Keep already-running sessions alive without exposing a duplicate SKILL.md."""
    scripts = legacy_dir / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("prompt_hook.py", "publish.py", "reply_history.py", "stop_hook.py", "write_guard.py"):
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
        skill_dir / "scripts" / "publish.py",
        skill_dir / "scripts" / "stop_hook.py",
        skill_dir / "scripts" / "reply_history.py",
        skill_dir / "scripts" / "write_guard.py",
    ]
    problems.extend(f"missing {path}" for path in required if not path.is_file())
    hooks_path = codex_home / "hooks.json"
    try:
        hooks = load_hooks(hooks_path).get("hooks", {})
        for event, entries in hooks.items() if isinstance(hooks, dict) else []:
            if isinstance(entries, list) and any(is_managed_hook(entry) for entry in entries):
                problems.append(f"hooks.{event} still contains an HTML Reply hook")
    except RuntimeError as error:
        problems.append(str(error))
    agents = codex_home / "AGENTS.md"
    if not agents.exists() or BLOCK_START not in agents.read_text(encoding="utf-8"):
        problems.append(f"managed guidance is missing from {agents}")
    discoverable_backups = [
        *skill_dir.parent.glob(f"{SKILL_NAME}.backup-*/SKILL.md"),
        *(codex_home / "skills").glob(f"{SKILL_NAME}.legacy-backup-*/SKILL.md"),
    ]
    problems.extend(f"discoverable backup must be quarantined outside the skills root: {path}" for path in discoverable_backups)
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
        user_backup_root = skills_home.parent / "skill-backups" / SKILL_NAME
        legacy_backup_root = codex_home / "skill-backups" / f"{SKILL_NAME}-legacy"
        quarantined = quarantine_discoverable_backups(
            skills_home,
            user_backup_root / "older-discoverable-backups",
            (f"{SKILL_NAME}.backup-*",),
        )
        had_legacy = legacy_skill_dir.exists() or any(
            legacy_skill_dir.parent.glob(f"{SKILL_NAME}.legacy-backup-*")
        )
        quarantined.extend(quarantine_discoverable_backups(
            legacy_skill_dir.parent,
            legacy_backup_root / "older-discoverable-backups",
            (f"{SKILL_NAME}.legacy-backup-*",),
        ))
        previous = install_skill(source, skill_dir, user_backup_root)
        merge_hooks(hooks_path, skill_dir, Path(sys.executable).resolve())
        update_guidance(agents_path)
        legacy_backup = None
        if legacy_skill_dir.exists() and legacy_skill_dir.resolve() != skill_dir.resolve():
            legacy_backup = move_out_of_discovery(
                legacy_skill_dir,
                legacy_backup_root / f"{SKILL_NAME}-{timestamp()}",
            )
        if had_legacy:
            write_legacy_shims(legacy_skill_dir, skill_dir)
        problems = verify(codex_home, skill_dir)
        if problems:
            raise RuntimeError("; ".join(problems))
    finally:
        if holder:
            holder.cleanup()

    print(f"Installed HTML Reply to {skill_dir}")
    print(f"Updated Codex hooks at {hooks_path}")
    if previous:
        print(f"Previous skill backed up to {previous}")
    if legacy_backup:
        print(f"Legacy CODEX_HOME skill migrated to {legacy_backup}")
    if quarantined:
        print(f"Quarantined {len(quarantined)} discoverable backup skill(s) outside the skills roots.")
    if legacy_skill_dir.exists():
        print(f"Legacy hook compatibility shims kept at {legacy_skill_dir / 'scripts'}")
    print("Restart Codex or open a new session to activate it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
