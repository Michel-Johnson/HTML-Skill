from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("html_reply_installer", ROOT / "install.py")
assert SPEC and SPEC.loader
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    def test_install_is_idempotent_and_preserves_existing_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex-home"
            skills_home = root / "user" / ".agents" / "skills"
            codex_home.mkdir(parents=True)
            existing = {
                "hooks": {
                    "PreToolUse": [{"hooks": [{"type": "command", "command": "keep-me"}]}],
                    "Stop": [{"hooks": [{"type": "command", "command": "also-keep-me"}]}],
                }
            }
            (codex_home / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")
            (codex_home / "AGENTS.md").write_text("# Existing guidance\n", encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "install.py"),
                "--source", str(ROOT),
                "--codex-home", str(codex_home),
                "--skills-home", str(skills_home),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command + ["--check"], check=True, capture_output=True, text=True)

            data = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(data["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "keep-me")
            self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "also-keep-me")
            for event in ("SessionStart", "UserPromptSubmit", "Stop"):
                managed = [entry for entry in data["hooks"][event] if INSTALLER.is_managed_hook(entry)]
                self.assertEqual(len(managed), 1)
            agents = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# Existing guidance", agents)
            self.assertEqual(agents.count(INSTALLER.BLOCK_START), 1)

    def test_uninstall_preserves_unrelated_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex-home"
            skills_home = root / "skills"
            base = [sys.executable, str(ROOT / "install.py"), "--source", str(ROOT), "--codex-home", str(codex_home), "--skills-home", str(skills_home)]
            subprocess.run(base, check=True, capture_output=True, text=True)
            subprocess.run(base + ["--uninstall"], check=True, capture_output=True, text=True)
            self.assertFalse((skills_home / "html-reply").exists())
            hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))["hooks"]
            self.assertFalse(any(INSTALLER.is_managed_hook(entry) for entries in hooks.values() for entry in entries))
            self.assertNotIn(INSTALLER.BLOCK_START, (codex_home / "AGENTS.md").read_text(encoding="utf-8"))

    def test_windows_command_quoting(self) -> None:
        command = INSTALLER.command_line([r"C:\Program Files\Python\python.exe", r"C:\Users\A B\hook.py"], platform="win32")
        self.assertIn('"C:\\Program Files\\Python\\python.exe"', command)
        self.assertIn('"C:\\Users\\A B\\hook.py"', command)

    def test_legacy_skill_becomes_non_skill_hook_shims(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex-home"
            skills_home = root / "skills"
            legacy = codex_home / "skills" / "html-reply"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text("legacy", encoding="utf-8")
            command = [sys.executable, str(ROOT / "install.py"), "--source", str(ROOT), "--codex-home", str(codex_home), "--skills-home", str(skills_home)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertFalse((legacy / "SKILL.md").exists())
            wrapper = legacy / "scripts" / "stop_hook.py"
            self.assertTrue(wrapper.is_file())
            self.assertIn(str(skills_home / "html-reply" / "scripts" / "stop_hook.py"), wrapper.read_text(encoding="utf-8"))

    def test_installed_hooks_complete_one_delivery_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex-home"
            skills_home = root / "skills"
            workspace = root / "workspace"
            workspace.mkdir()
            install = [sys.executable, str(ROOT / "install.py"), "--source", str(ROOT), "--codex-home", str(codex_home), "--skills-home", str(skills_home)]
            subprocess.run(install, check=True, capture_output=True, text=True)
            scripts = skills_home / "html-reply" / "scripts"
            session = "windows-safe-session"
            prompt_payload = {"session_id": session, "cwd": str(workspace), "prompt": "请用 HTML 回答"}
            injected = subprocess.run(
                [sys.executable, str(scripts / "prompt_hook.py")],
                input=json.dumps(prompt_payload), check=True, capture_output=True, text=True,
            )
            context = json.loads(injected.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn(str(scripts / "reply_history.py"), context)
            self.assertTrue((workspace / "output" / ".html-reply" / "sessions" / f"{session}.json").is_file())

            output = workspace / "output"
            output.mkdir(exist_ok=True)
            reply = output / f"reply-{session}.html"
            summary = "完整链路已经通过。"
            reply.write_text(f"<!doctype html><html><head><title>Test</title></head><body><p>{summary}</p></body></html>", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "finalize", "--root", str(workspace), "--session", session],
                check=True, capture_output=True, text=True,
            )
            stop_payload = {
                "session_id": session,
                "cwd": str(workspace),
                "last_assistant_message": f"{summary}\n\n[查看]({reply})",
            }
            stopped = subprocess.run(
                [sys.executable, str(scripts / "stop_hook.py")],
                input=json.dumps(stop_payload), check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(stopped.stdout), {})

    def test_stop_hook_rejects_shared_or_other_session_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            summary = "session-b 只能使用自己的页面。"

            def write_reply(name: str) -> Path:
                path = output / name
                path.write_text(
                    f'<!doctype html><html><body><p>{summary}</p>'
                    '<script type="application/json" id="html-reply-history-data">{}</script>'
                    '</body></html>',
                    encoding="utf-8",
                )
                return path

            def stop_with(path: Path) -> dict:
                payload = {
                    "session_id": "session-b",
                    "cwd": str(root),
                    "last_assistant_message": f"{summary}\n\n[查看]({path})",
                }
                result = subprocess.run(
                    [sys.executable, str(scripts / "stop_hook.py")],
                    input=json.dumps(payload), check=True, capture_output=True, text=True,
                )
                return json.loads(result.stdout)

            self.assertEqual(stop_with(write_reply("reply-session-b.html")), {})
            self.assertEqual(stop_with(write_reply("reply.html"))["decision"], "block")
            self.assertEqual(stop_with(write_reply("reply-session-a.html"))["decision"], "block")

    def test_prompt_state_and_history_are_isolated_by_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"

            for session, prompt in (("session-a", "Prompt A"), ("session-b", "Prompt B")):
                subprocess.run(
                    [sys.executable, str(scripts / "prompt_hook.py")],
                    input=json.dumps({"session_id": session, "cwd": str(root), "prompt": prompt}),
                    check=True, capture_output=True, text=True,
                )
                reply = output / f"reply-{session}.html"
                reply.write_text(
                    f"<!doctype html><html><head><title>{session}</title></head>"
                    f"<body><p>{prompt}</p></body></html>",
                    encoding="utf-8",
                )
                subprocess.run(
                    [sys.executable, str(scripts / "reply_history.py"), "finalize", "--root", str(root), "--session", session],
                    check=True, capture_output=True, text=True,
                )
                subprocess.run(
                    [sys.executable, str(scripts / "reply_history.py"), "archive", "--root", str(root), "--session", session],
                    check=True, capture_output=True, text=True,
                )

            a_source = (output / "reply-session-a.html").read_text(encoding="utf-8")
            b_source = (output / "reply-session-b.html").read_text(encoding="utf-8")
            self.assertIn('"session": "session-a"', a_source)
            self.assertIn('"currentPrompt": "Prompt A"', a_source)
            self.assertNotIn('"currentPrompt": "Prompt B"', a_source)
            self.assertIn('"session": "session-b"', b_source)
            self.assertIn('"currentPrompt": "Prompt B"', b_source)
            self.assertNotIn('"currentPrompt": "Prompt A"', b_source)
            self.assertTrue((output / "archive" / "html-reply" / "session-a" / "reply-0001.html").is_file())
            self.assertTrue((output / "archive" / "html-reply" / "session-b" / "reply-0001.html").is_file())

    def test_history_replay_uses_top_level_navigation_and_keeps_history_button(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "full-page-history"
            reply = output / f"reply-{session}.html"
            reply.write_text(
                "<!doctype html><html><head><title>Full page</title></head>"
                "<body><p>History viewer test</p></body></html>",
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "finalize", "--root", str(root), "--session", session, "--prompt", "第一轮 Prompt"],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "archive", "--root", str(root), "--session", session],
                check=True, capture_output=True, text=True,
            )
            reply.write_text(
                "<!doctype html><html><head><title>Latest</title></head>"
                "<body><p>Latest reply</p></body></html>",
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "finalize", "--root", str(root), "--session", session, "--prompt", "最新 Prompt"],
                check=True, capture_output=True, text=True,
            )

            source = reply.read_text(encoding="utf-8")
            self.assertIn('id="hr-history-button"', source)
            self.assertNotIn("hr-history-viewer", source)
            self.assertNotIn("hr-history-frame", source)
            self.assertNotIn("html-reply-embedded", source)
            self.assertNotIn("hideEmbeddedChrome", source)
            self.assertIn("a.href=item.path", source)

            replay = output / "archive" / "html-reply" / session / ".replay" / "reply-0001.html"
            replay_source = replay.read_text(encoding="utf-8")
            self.assertIn('id="hr-history-button"', replay_source)
            self.assertIn('id="hr-latest-link"', replay_source)
            self.assertIn("← 返回最新回复", replay_source)
            self.assertIn('"isReplay": true', replay_source)
            self.assertIn('"currentPrompt": "第一轮 Prompt"', replay_source)
            self.assertIn(reply.resolve().as_uri(), replay_source)
            self.assertNotIn("<iframe", replay_source)


if __name__ == "__main__":
    unittest.main()
