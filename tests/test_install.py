from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("html_reply_installer", ROOT / "install.py")
assert SPEC and SPEC.loader
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._codex_thread_id = os.environ.pop("CODEX_THREAD_ID", None)
        self._html_reply_surface = os.environ.get("HTML_REPLY_SURFACE")
        os.environ["HTML_REPLY_SURFACE"] = "desktop"

    def tearDown(self) -> None:
        if self._codex_thread_id is not None:
            os.environ["CODEX_THREAD_ID"] = self._codex_thread_id
        else:
            os.environ.pop("CODEX_THREAD_ID", None)
        if self._html_reply_surface is None:
            os.environ.pop("HTML_REPLY_SURFACE", None)
        else:
            os.environ["HTML_REPLY_SURFACE"] = self._html_reply_surface

    def test_hooks_are_silent_and_non_blocking_in_codex_cli(self) -> None:
        scripts = ROOT / "skill" / "html-reply" / "scripts"
        env = os.environ.copy()
        env["HTML_REPLY_SURFACE"] = "cli"
        env.pop("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", None)
        payload = {
            "session_id": "cli-session",
            "cwd": str(ROOT),
            "prompt": "普通 CLI 请求",
            "last_assistant_message": "普通文本回复",
            "tool_name": "apply_patch",
            "tool_input": {"patch": "*** Begin Patch\n*** End Patch"},
        }

        prompt = subprocess.run(
            [sys.executable, str(scripts / "prompt_hook.py")],
            input=json.dumps(payload), env=env, check=True, capture_output=True, text=True,
        )
        stop = subprocess.run(
            [sys.executable, str(scripts / "stop_hook.py")],
            input=json.dumps(payload), env=env, check=True, capture_output=True, text=True,
        )
        guard = subprocess.run(
            [sys.executable, str(scripts / "write_guard.py")],
            input=json.dumps(payload), env=env, check=True, capture_output=True, text=True,
        )

        self.assertEqual(json.loads(prompt.stdout), {})
        self.assertEqual(json.loads(stop.stdout), {})
        self.assertEqual(json.loads(guard.stdout), {})

    def test_skill_requires_explicit_invocation(self) -> None:
        metadata = (ROOT / "skill" / "html-reply" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        skill = (ROOT / "skill" / "html-reply" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertIn("Use only when the user explicitly asks for HTML output", skill)
        self.assertIn("Default to the normal chat response format", skill)

    def test_prompt_hook_is_noop_on_every_surface(self) -> None:
        script = ROOT / "skill" / "html-reply" / "scripts" / "prompt_hook.py"
        payload = {"session_id": "surface-test", "cwd": str(ROOT), "prompt": "测试"}
        env = os.environ.copy()
        env.pop("HTML_REPLY_SURFACE", None)
        env.pop("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", None)
        disabled = subprocess.run(
            [sys.executable, str(script)], input=json.dumps(payload), env=env,
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(disabled.stdout), {})

        env["CODEX_INTERNAL_ORIGINATOR_OVERRIDE"] = "Codex Desktop"
        enabled = subprocess.run(
            [sys.executable, str(script)], input=json.dumps(payload), env=env,
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(enabled.stdout), {})

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
            self.assertFalse(any(
                INSTALLER.is_managed_hook(entry)
                for entries in data["hooks"].values()
                for entry in entries
            ))
            agents = (codex_home / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# Existing guidance", agents)
            self.assertEqual(agents.count(INSTALLER.BLOCK_START), 1)
            self.assertIn("CODEX_THREAD_ID", agents)
            self.assertIn("默认使用普通聊天回复", agents)
            self.assertIn("明确要求 HTML 输出", agents)
            self.assertIn("一次明确调用只对当前回合生效", agents)

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
            installed_stop = (skills_home / "html-reply" / "scripts" / "stop_hook.py").resolve()
            self.assertIn(str(installed_stop), wrapper.read_text(encoding="utf-8"))
            self.assertTrue((legacy / "scripts" / "write_guard.py").is_file())

    def test_install_quarantines_old_backups_outside_skill_discovery_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            codex_home = root / "codex-home"
            skills_home = root / "user" / ".agents" / "skills"
            old_user = skills_home / "html-reply.backup-old"
            old_legacy = codex_home / "skills" / "html-reply.legacy-backup-old"
            for path in (old_user, old_legacy):
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text("---\nname: html-reply\n---\nold", encoding="utf-8")

            command = [
                sys.executable,
                str(ROOT / "install.py"),
                "--source",
                str(ROOT),
                "--codex-home",
                str(codex_home),
                "--skills-home",
                str(skills_home),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command + ["--check"], check=True, capture_output=True, text=True)

            discovered = [
                *skills_home.glob("html-reply.backup-*/SKILL.md"),
                *(codex_home / "skills").glob("html-reply.legacy-backup-*/SKILL.md"),
            ]
            self.assertEqual(discovered, [])
            quarantined = [
                *(skills_home.parent / "skill-backups").rglob("SKILL.md"),
                *(codex_home / "skill-backups").rglob("SKILL.md"),
            ]
            self.assertGreaterEqual(len(quarantined), 3)

    def obsolete_installed_hooks_complete_one_delivery_cycle(self) -> None:
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
            self.assertIn(str(scripts / "publish.py"), context)
            self.assertIn(f"output/.html-reply/drafts/reply-{session}.html", context)
            self.assertIn(f"output/history-{session}.html", context)
            self.assertIn("历史总览", context)
            self.assertIn("当前回复", context)
            self.assertTrue((workspace / "output" / ".html-reply" / "sessions" / f"{session}.json").is_file())

            output = workspace / "output"
            output.mkdir(exist_ok=True)
            reply = output / f"reply-{session}.html"
            summary = "完整链路已经通过。"
            draft = output / ".html-reply" / "drafts" / f"reply-{session}.html"
            draft.parent.mkdir(parents=True)
            draft.write_text(
                f"<header><h1>Test</h1></header><section><p data-html-reply-summary>{summary}</p></section>",
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(scripts / "publish.py"), "--root", str(workspace), "--session", session],
                check=True, capture_output=True, text=True,
            )
            history = output / f"history-{session}.html"
            stop_payload = {
                "session_id": session,
                "cwd": str(workspace),
                "last_assistant_message": (
                    f"{summary}\n\n[历史总览]({history}) [当前回复]({reply})"
                    "\n\n<!-- development-reflection:complete -->"
                ),
            }
            stopped = subprocess.run(
                [sys.executable, str(scripts / "stop_hook.py")],
                input=json.dumps(stop_payload), check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(stopped.stdout), {})

    def test_legacy_stop_hook_never_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            summary = "session-b 只能使用自己的页面。"
            history = output / "history-session-b.html"
            history.write_text(
                '<!doctype html><html><body data-html-reply-theme="soft-bauhaus-v1">'
                '<script type="application/json" id="html-reply-history-index-data">'
                '{"session":"session-b","count":1}</script></body></html>',
                encoding="utf-8",
            )

            def write_reply(name: str) -> Path:
                path = output / name
                path.write_text(
                    f'<!doctype html><html><body data-html-reply-theme="soft-bauhaus-v1"><p>{summary}</p>'
                    '<script type="application/json" id="html-reply-history-data">{}</script>'
                    '</body></html>',
                    encoding="utf-8",
                )
                return path

            def stop_with(path: Path) -> dict:
                payload = {
                    "session_id": "session-b",
                    "cwd": str(root),
                    "last_assistant_message": (
                        f"{summary}\n\n[历史总览]({history}) [当前回复]({path})"
                        "\n\n<!-- development-reflection:complete -->"
                    ),
                }
                result = subprocess.run(
                    [sys.executable, str(scripts / "stop_hook.py")],
                    input=json.dumps(payload), check=True, capture_output=True, text=True,
                )
                return json.loads(result.stdout)

            self.assertEqual(stop_with(write_reply("reply-session-b.html")), {})
            self.assertEqual(stop_with(write_reply("reply.html")), {})
            self.assertEqual(stop_with(write_reply("reply-session-a.html")), {})

    def obsolete_prompt_state_and_history_are_isolated_by_session(self) -> None:
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
            a_history = (output / "history-session-a.html").read_text(encoding="utf-8")
            b_history = (output / "history-session-b.html").read_text(encoding="utf-8")
            self.assertIn('"session": "session-a"', a_history)
            self.assertNotIn('"session": "session-b"', a_history)
            self.assertIn('"session": "session-b"', b_history)
            self.assertNotIn('"session": "session-a"', b_history)
            self.assertIn('id="history-search"', a_history)
            self.assertTrue((output / "archive" / "html-reply" / "session-a" / "reply-0001.html").is_file())
            self.assertTrue((output / "archive" / "html-reply" / "session-b" / "reply-0001.html").is_file())

    def obsolete_hook_identity_uses_top_level_thread_not_nested_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            payload = {
                "metadata": {
                    "session_id": "shared-workspace-session",
                    "thread_id": "parent-thread",
                },
                "session_id": "current-thread",
                "cwd": str(root),
                "prompt": "只属于当前 thread",
            }
            result = subprocess.run(
                [sys.executable, str(scripts / "prompt_hook.py")],
                input=json.dumps(payload), check=True, capture_output=True, text=True,
            )
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("reply-current-thread.html", context)
            self.assertNotIn("shared-workspace-session", context)
            self.assertNotIn("parent-thread", context)
            self.assertTrue((root / "output" / ".html-reply" / "sessions" / "current-thread.json").is_file())

    def obsolete_transcript_path_fallback_is_thread_scoped_and_never_local(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            thread_a = "019f1111-1111-7111-8111-111111111111"
            thread_b = "019f2222-2222-7222-8222-222222222222"

            def invoke(thread: str) -> str:
                payload = {
                    "transcript_path": str(root / f"rollout-2026-07-30-{thread}.jsonl"),
                    "cwd": str(root),
                    "prompt": thread,
                }
                result = subprocess.run(
                    [sys.executable, str(scripts / "prompt_hook.py")],
                    input=json.dumps(payload), check=True, capture_output=True, text=True,
                )
                return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

            with ThreadPoolExecutor(max_workers=2) as pool:
                context_a, context_b = list(pool.map(invoke, (thread_a, thread_b)))
            self.assertIn(f"reply-{thread_a}.html", context_a)
            self.assertNotIn(thread_b, context_a)
            self.assertIn(f"reply-{thread_b}.html", context_b)
            self.assertNotIn(thread_a, context_b)
            self.assertFalse((root / "output" / ".html-reply" / "sessions" / "local.json").exists())

            output = root / "output"
            for thread in (thread_a, thread_b):
                (output / f"reply-{thread}.html").write_text(
                    f"<!doctype html><html><head><title>{thread}</title></head>"
                    f"<body><p>{thread}</p></body></html>",
                    encoding="utf-8",
                )

            def finalize(thread: str) -> None:
                subprocess.run(
                    [
                        sys.executable,
                        str(scripts / "reply_history.py"),
                        "finalize",
                        "--root",
                        str(root),
                        "--session",
                        thread,
                        "--prompt",
                        thread,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(finalize, (thread_a, thread_b)))
            source_a = (output / f"history-{thread_a}.html").read_text(encoding="utf-8")
            source_b = (output / f"history-{thread_b}.html").read_text(encoding="utf-8")
            self.assertIn(f'"session": "{thread_a}"', source_a)
            self.assertNotIn(thread_b, source_a)
            self.assertIn(f'"session": "{thread_b}"', source_b)
            self.assertNotIn(thread_a, source_b)

    def obsolete_missing_hook_identity_fails_closed_without_shared_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            payload = {"cwd": str(root), "prompt": "没有 thread id"}
            result = subprocess.run(
                [sys.executable, str(scripts / "prompt_hook.py")],
                input=json.dumps(payload), check=True, capture_output=True, text=True,
            )
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("cannot determine this Codex thread", context)
            self.assertIn("Do not create or update", context)
            self.assertFalse((root / "output" / ".html-reply" / "sessions" / "local.json").exists())

            stopped = subprocess.run(
                [sys.executable, str(scripts / "stop_hook.py")],
                input=json.dumps({
                    "cwd": str(root),
                    "last_assistant_message": (
                        "不能写入共享页面。\n\n<!-- development-reflection:not-applicable -->"
                    ),
                }),
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(stopped.stdout), {})

    def test_write_guard_blocks_other_thread_and_shared_html_writes(self) -> None:
        scripts = ROOT / "skill" / "html-reply" / "scripts"
        guard = scripts / "write_guard.py"

        def invoke(tool_name: str, command: str, session: str = "session-a") -> dict:
            result = subprocess.run(
                [sys.executable, str(guard)],
                input=json.dumps({
                    "session_id": session,
                    "tool_name": tool_name,
                    "tool_input": {"command": command},
                }),
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(result.stdout)

        own_patch = "*** Begin Patch\n*** Update File: output/reply-session-a.html\n"
        other_patch = "*** Begin Patch\n*** Update File: output/reply-session-b.html\n"
        shared_patch = "*** Begin Patch\n*** Update File: output/reply.html\n"
        self.assertEqual(invoke("apply_patch", own_patch), {})
        self.assertEqual(
            invoke("apply_patch", other_patch)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertEqual(
            invoke("apply_patch", shared_patch)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertEqual(
            invoke(
                "Bash",
                "python3 reply_history.py finalize --root /tmp/work --session session-b",
            )["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertEqual(
            invoke(
                "Bash",
                "python3 reply_history.py finalize --root /tmp/work --session session-a",
            ),
            {},
        )
        self.assertEqual(
            invoke("Bash", "rg -n title output/reply-session-b.html"),
            {},
        )

        patch_payload = {
            "session_id": "session-a",
            "tool_name": "apply_patch",
            "tool_input": {
                "patch": "*** Begin Patch\n*** Update File: output/.html-reply/drafts/reply-session-b.html\n"
            },
        }
        guarded = subprocess.run(
            [sys.executable, str(guard)],
            input=json.dumps(patch_payload), check=True, capture_output=True, text=True,
        )
        self.assertEqual(
            json.loads(guarded.stdout)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

    def test_single_publish_command_wraps_fragment_archives_and_finalizes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "fragment-publisher"
            output = root / "output"
            output.mkdir()
            old_reply = output / f"reply-{session}.html"
            old_reply.write_text(
                "<!doctype html><html><head><title>Old</title></head><body>old</body></html>",
                encoding="utf-8",
            )
            draft = output / ".html-reply" / "drafts" / f"reply-{session}.html"
            draft.parent.mkdir(parents=True)
            summary = "两次 Tool Call 已经完成完整发布。"
            draft.write_text(
                "<header><h1>Fragment Publisher</h1></header>"
                f"<section><p data-html-reply-summary>{summary}</p>"
                '<pre><code class="language-python">answer = True</code></pre></section>',
                encoding="utf-8",
            )
            published = subprocess.run(
                [sys.executable, str(scripts / "publish.py"), "--root", str(root), "--session", session, "--prompt", "简化流程"],
                check=True, capture_output=True, text=True,
            )
            self.assertTrue(published.stdout.isascii())
            result = json.loads(published.stdout)
            self.assertEqual(result["summary"], summary)
            self.assertEqual(Path(result["reply"]).resolve(), old_reply.resolve())
            source = old_reply.read_text(encoding="utf-8")
            self.assertIn("<title>Fragment Publisher</title>", source)
            self.assertIn(summary, source)
            self.assertIn('data-html-reply-theme="soft-bauhaus-v1"', source)
            self.assertIn('data-hr-language="python"', source)
            self.assertTrue((output / f"history-{session}.html").is_file())
            archived = output / "archive" / "html-reply" / session / "reply-0001.html"
            self.assertTrue(archived.is_file())
            self.assertIn("<title>Old</title>", archived.read_text(encoding="utf-8"))

    def test_publisher_rejects_full_document_before_archiving(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "fragment-only"
            output = root / "output"
            output.mkdir()
            reply = output / f"reply-{session}.html"
            reply.write_text("old stable page", encoding="utf-8")
            draft = output / ".html-reply" / "drafts" / f"reply-{session}.html"
            draft.parent.mkdir(parents=True)
            draft.write_text(
                "<!doctype html><html><body><h1>Wrong</h1><p data-html-reply-summary>wrong</p></body></html>",
                encoding="utf-8",
            )
            rejected = subprocess.run(
                [sys.executable, str(scripts / "publish.py"), "--root", str(root), "--session", session],
                capture_output=True, text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("body fragment", rejected.stderr)
            self.assertEqual(reply.read_text(encoding="utf-8"), "old stable page")
            self.assertFalse((output / "archive" / "html-reply" / session).exists())

    def test_reply_history_uses_codex_thread_id_and_rejects_stale_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper = ROOT / "skill" / "html-reply" / "scripts" / "reply_history.py"
            current = "019f1111-1111-7111-8111-111111111111"
            stale = "019f2222-2222-7222-8222-222222222222"
            env = dict(os.environ, CODEX_THREAD_ID=current)

            resolved = subprocess.run(
                [sys.executable, str(helper), "path", "--root", str(root)],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                Path(resolved.stdout.strip()).resolve(),
                (root / "output" / f"reply-{current}.html").resolve(),
            )

            rejected = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "path",
                    "--root",
                    str(root),
                    "--session",
                    stale,
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("does not match CODEX_THREAD_ID", rejected.stderr)

    def test_write_guard_scans_directly_invoked_script_for_stale_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = "019f1111-1111-7111-8111-111111111111"
            stale = "019f2222-2222-7222-8222-222222222222"
            script = root / "build_report.py"
            script.write_text(
                "from pathlib import Path\n"
                f"REPLY = Path('output/reply-{stale}.html')\n"
                "REPLY.write_text('<html></html>')\n",
                encoding="utf-8",
            )
            guard = ROOT / "skill" / "html-reply" / "scripts" / "write_guard.py"
            env = dict(os.environ, CODEX_THREAD_ID=current)
            result = subprocess.run(
                [sys.executable, str(guard)],
                env=env,
                input=json.dumps({
                    "session_id": current,
                    "cwd": str(root),
                    "tool_name": "Bash",
                    "tool_input": {"command": f"python3 {script.name}"},
                }),
                check=True,
                capture_output=True,
                text=True,
            )
            decision = json.loads(result.stdout)["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], "deny")
            self.assertIn(stale, decision["permissionDecisionReason"])

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
            self.assertIn('data-html-reply-theme="soft-bauhaus-v1"', source)
            self.assertIn("right:18px;top:18px", source)
            self.assertNotIn("left:14px;top:50%", source)
            self.assertNotIn("writing-mode:vertical-rl", source)
            self.assertNotIn("translateY(-50%)", source)
            self.assertNotIn("hr-history-viewer", source)
            self.assertNotIn("hr-history-frame", source)
            self.assertNotIn("html-reply-embedded", source)
            self.assertNotIn("hideEmbeddedChrome", source)
            self.assertIn("a.href=item.path", source)
            self.assertNotIn('id="hr-current-prompt"', source)
            self.assertNotIn("a.querySelector('span')", source)
            self.assertIn("a.innerHTML='<b></b>'", source)

            replay = output / "archive" / "html-reply" / session / ".replay" / "reply-0001.html"
            replay_source = replay.read_text(encoding="utf-8")
            self.assertIn('id="hr-history-button"', replay_source)
            self.assertIn('data-html-reply-theme="soft-bauhaus-v1"', replay_source)
            self.assertIn("right:18px;top:18px", replay_source)
            self.assertIn('id="hr-latest-link"', replay_source)
            self.assertIn("← 返回最新回复", replay_source)
            self.assertIn('"isReplay": true', replay_source)
            self.assertIn('"currentPrompt": "第一轮 Prompt"', replay_source)
            self.assertIn(reply.resolve().as_uri(), replay_source)
            self.assertNotIn("<iframe", replay_source)
            self.assertNotIn('id="hr-current-prompt"', replay_source)
            self.assertNotIn("a.querySelector('span')", replay_source)

    def test_finalizer_highlights_multiple_code_languages_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "syntax-colors"
            reply = output / f"reply-{session}.html"
            samples = {
                "json": '<pre><code class="language-json">{&quot;ok&quot;: true, &quot;count&quot;: 3}</code></pre>',
                "python": '<pre><code>def greet(name):\n    return f&quot;Hi {name}&quot;</code></pre>',
                "javascript": '<pre><code class="language-js">const answer = true;</code></pre>',
                "typescript": '<pre><code class="language-ts">interface User { id: number }</code></pre>',
                "shell": '<pre><code class="language-bash">export NAME=&quot;Codex&quot;\necho $NAME</code></pre>',
                "sql": '<pre><code>SELECT id FROM users WHERE active = 1;</code></pre>',
                "html": '<pre><code class="language-html">&lt;main&gt;Hello&lt;/main&gt;</code></pre>',
                "css": '<pre><code class="language-css">.card { color: #d9a441; }</code></pre>',
            }
            reply.write_text(
                '<!doctype html><html><head><title>Syntax</title></head><body>'
                + "".join(samples.values()) + '</body></html>',
                encoding="utf-8",
            )
            command = [
                sys.executable, str(scripts / "reply_history.py"), "finalize",
                "--root", str(root), "--session", session, "--prompt", "高亮代码",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command, check=True, capture_output=True, text=True)

            source = reply.read_text(encoding="utf-8")
            for language in samples:
                self.assertIn(f'data-hr-language="{language}"', source)
            self.assertEqual(source.count('data-html-reply-highlighted="1"'), len(samples))
            self.assertIn('class="hr-tok-key"', source)
            self.assertIn('class="hr-tok-string"', source)
            self.assertIn('class="hr-tok-keyword"', source)
            self.assertIn('class="hr-tok-variable"', source)
            self.assertIn('class="hr-tok-tag"', source)
            self.assertIn('class="hr-tok-property"', source)
            self.assertIn('content:attr(data-hr-language)', source)

    def test_pre_code_resets_inline_code_background(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "code-background-reset"
            reply = output / f"reply-{session}.html"
            reply.write_text(
                '<!doctype html><html><head><title>Code CSS</title>'
                '<style>.blog-guide code{background:#f0eee8}.blog-guide pre{background:#202521;color:#f2f0e8}</style>'
                '</head><body><main class="blog-guide"><p><code>inline</code></p>'
                '<pre><code class="language-css">.card { color: red; }</code></pre></main></body></html>',
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "finalize", "--root", str(root), "--session", session],
                check=True, capture_output=True, text=True,
            )
            source = reply.read_text(encoding="utf-8")
            self.assertIn(
                f'body[data-html-reply-theme="soft-bauhaus-v1"] pre code{{background:transparent!important;color:inherit!important;padding:0!important;border-radius:0!important}}',
                source,
            )
            self.assertIn('.blog-guide code{background:#f0eee8}', source)
            template = (ROOT / "skill" / "html-reply" / "assets" / "fragment-shell.html").read_text(encoding="utf-8")
            self.assertIn('.reply-page pre code{background:transparent;color:inherit;padding:0;border-radius:0}', template)

    def test_finalizer_normalizes_drifted_visual_foundation_without_stop_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "canonical-theme"
            summary = "固定主题已经生效。"
            reply = output / f"reply-{session}.html"
            reply.write_text(
                '<!doctype html><html><head><title>Drift</title>'
                '<style>body{background:#102f27}main{max-width:1080px}.card{border-radius:18px;box-shadow:0 20px 50px #000}</style>'
                f'</head><body><main><article class="card"><p>{summary}</p></article></main></body></html>',
                encoding="utf-8",
            )

            def stop() -> dict:
                history = output / f"history-{session}.html"
                payload = {
                    "session_id": session,
                    "cwd": str(root),
                    "last_assistant_message": (
                        f"{summary}\n\n[历史总览]({history}) [当前回复]({reply})"
                        "\n\n<!-- development-reflection:complete -->"
                    ),
                }
                result = subprocess.run(
                    [sys.executable, str(scripts / "stop_hook.py")],
                    input=json.dumps(payload), check=True, capture_output=True, text=True,
                )
                return json.loads(result.stdout)

            reply.write_text(
                f'<!doctype html><html><body><p>{summary}</p>'
                '<script type="application/json" id="html-reply-history-data">{}</script></body></html>',
                encoding="utf-8",
            )
            self.assertEqual(stop(), {})

            reply.write_text(
                '<!doctype html><html><head><title>Drift</title>'
                '<style>body{background:#102f27}main{max-width:1080px}.card{border-radius:18px;box-shadow:0 20px 50px #000}</style>'
                f'</head><body><main><article class="card"><p>{summary}</p></article></main></body></html>',
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "finalize", "--root", str(root), "--session", session],
                check=True, capture_output=True, text=True,
            )
            source = reply.read_text(encoding="utf-8")
            self.assertIn('data-html-reply-theme="soft-bauhaus-v1"', source)
            self.assertGreater(source.index("max-width:none!important"), source.index("max-width:1080px"))
            self.assertGreater(source.index("border-radius:5px!important"), source.index("border-radius:18px"))
            self.assertIn("box-shadow:none!important", source)
            self.assertEqual(stop(), {})

    def obsolete_interactive_answers_are_consumed_once_and_isolated_by_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            downloads.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            old_response = downloads / "html-reply-response-session-a.json"
            old_response.write_text(json.dumps({
                "version": 1,
                "session": "session-a",
                "pageTitle": "交互测试",
                "revision": "old",
                "submittedAt": "2026-07-23T11:59:00Z",
                "answers": [{"id": "priority", "question": "优先支持什么？", "answer": "旧答案"}],
            }, ensure_ascii=False), encoding="utf-8")
            os.utime(old_response, ns=(1_000_000_000, 1_000_000_000))
            response = downloads / "html-reply-response-session-a (1).json"
            response.write_text(json.dumps({
                "version": 1,
                "session": "session-a",
                "pageTitle": "交互测试",
                "revision": "new",
                "submittedAt": "2026-07-23T12:00:00Z",
                "answers": [
                    {"id": "priority", "question": "优先支持什么？", "answer": "单选题"},
                    {"id": "notes", "question": "补充要求", "answer": "不需要保存按钮"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            env = os.environ.copy()
            env["HTML_REPLY_INTERACTION_INBOX"] = str(downloads)

            def invoke(session: str) -> str:
                result = subprocess.run(
                    [sys.executable, str(scripts / "prompt_hook.py"), "UserPromptSubmit"],
                    input=json.dumps({"session_id": session, "cwd": str(root), "prompt": "继续"}),
                    env=env, check=True, capture_output=True, text=True,
                )
                return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

            first = invoke("session-a")
            self.assertIn("优先支持什么？: 单选题", first)
            self.assertIn("补充要求: 不需要保存按钮", first)
            self.assertNotIn("旧答案", first)
            self.assertNotIn("interaction update detected", invoke("session-a"))
            self.assertNotIn("优先支持什么？", invoke("session-b"))
            self.assertTrue((root / "output" / ".html-reply" / "interactions" / "session-a.state.json").is_file())
            self.assertEqual(
                len(list((root / "output" / ".html-reply" / "interactions" / "session-a").glob("*.json"))),
                1,
            )

    def test_finalizer_adds_automatic_interaction_runtime_and_disables_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            scripts = ROOT / "skill" / "html-reply" / "scripts"
            session = "interactive"
            reply = output / f"reply-{session}.html"
            reply.write_text(
                '<!doctype html><html><head><title>Interactive</title></head><body>'
                '<form data-html-reply-interaction data-interaction-id="next-step">'
                '<fieldset data-question="下一步做什么？"><legend>下一步做什么？</legend>'
                '<label><input type="radio" name="next" value="测试">测试</label></fieldset>'
                '<label data-question="补充要求">补充要求<textarea name="notes"></textarea></label>'
                '<p data-interaction-status></p></form></body></html>',
                encoding="utf-8",
            )
            finalize = [
                sys.executable, str(scripts / "reply_history.py"), "finalize",
                "--root", str(root), "--session", session, "--prompt", "请提问",
            ]
            subprocess.run(finalize, check=True, capture_output=True, text=True)
            source = reply.read_text(encoding="utf-8")
            self.assertIn("html-reply-response-'+data.session+'.json", source)
            self.assertIn("form.addEventListener('change',exportAnswers)", source)
            self.assertIn("form.addEventListener('blur'", source)
            self.assertIn("回答已保存", source)
            self.assertIn("localStorage", source)
            self.assertIn('"revision": "', source)
            subprocess.run(
                [sys.executable, str(scripts / "reply_history.py"), "archive", "--root", str(root), "--session", session],
                check=True, capture_output=True, text=True,
            )
            reply.write_text("<!doctype html><html><head><title>Next</title></head><body>next</body></html>", encoding="utf-8")
            subprocess.run(finalize, check=True, capture_output=True, text=True)
            replay = output / "archive" / "html-reply" / session / ".replay" / "reply-0001.html"
            replay_source = replay.read_text(encoding="utf-8")
            self.assertIn("这是历史回复，只能查看", replay_source)
            self.assertIn('"isReplay": true', replay_source)


if __name__ == "__main__":
    unittest.main()
