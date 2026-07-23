# Codex HTML Reply

让 Codex 的每次正式回复自动写入独立、可刷新、带历史记录的 HTML 页面。

页面也可以直接向用户提问：单选、复选、下拉选择会在改动后自动保存，文本回答会在离开输入框时自动保存。用户下一次正常向 Codex 发送消息时，`UserPromptSubmit` Hook 会读取当前 session 最新的回答；不需要点击“保存”，也不需要启动 localhost 服务。

![Codex HTML Reply 的软化包豪斯页面预览](docs/assets/html-reply-preview.png)

[查看完整 HTML 预览](docs/readme-preview.html)

## 不同任务的实际效果

这些示例均为本仓库单独生成的演示任务，不复用已有回复页面。

### Transformer 学习

[![Transformer 注意力机制学习页面](docs/assets/examples/transformer-learning.png)](docs/examples/transformer-learning.html)

### Tokenizer 学习

[![Tokenizer 分词器学习页面](docs/assets/examples/tokenizer-learning.png)](docs/examples/tokenizer-learning.html)

### Agent 调试报告

[![Agent 调试报告页面](docs/assets/examples/agent-debug-report.png)](docs/examples/agent-debug-report.html)

## 安装

要求：Codex 与 Python 3.9+。

macOS：

```bash
curl -fsSL https://raw.githubusercontent.com/Michel-Johnson/HTML-Skill/main/install.py | python3 -
```

Windows PowerShell：

```powershell
irm https://raw.githubusercontent.com/Michel-Johnson/HTML-Skill/main/install.py | py -3
```

如果 Windows 没有 `py` 启动器，但 `python` 命令可用：

```powershell
irm https://raw.githubusercontent.com/Michel-Johnson/HTML-Skill/main/install.py | python -
```

安装完成后重启 Codex，或新建一个 session。

## 安装器会做什么

- 将 Skill 安装到官方用户级目录 `~/.agents/skills/html-reply`。
- 将 HTML Reply Hook 合并进 `$CODEX_HOME/hooks.json`，不会覆盖已有 Hook。
- 将一小段全局规则写入 `$CODEX_HOME/AGENTS.md`，不会删除原内容。
- 修改已有文件前自动创建带时间戳的备份。
- 重复运行是安全的：每个 Hook 事件始终只保留一份 HTML Reply 配置。

`CODEX_HOME` 未设置时默认为 `~/.codex`。

## 验证

```bash
python3 install.py --check
```

Windows：

```powershell
py -3 install.py --check
```

## 卸载

```bash
python3 install.py --uninstall
```

卸载只删除 HTML Reply 管理的 Skill、Hook 和全局规则，其他 Codex 配置保持不变。

## 兼容性

- macOS：使用系统或用户安装的 Python 3.9+。
- Windows 10/11：支持 `py -3` 或 `python`，路径包含空格时也能正确安装。
- 安装位置遵循 Codex 用户级 Skill 目录；如果检测到旧的 `$CODEX_HOME/skills/html-reply`，会先备份再迁移，并保留仅含 Hook 转发脚本的兼容目录，避免正在运行的旧 session 中断。
- 当前只配置 Codex，不修改其他 Agent 或编辑器。
- 交互回答默认从系统 `Downloads` 目录读取；浏览器使用自定义下载目录时，可通过 `HTML_REPLY_INTERACTION_INBOX` 指定。回答文件必须匹配当前 session，且每个版本只会消费一次。

官方依据：[Build skills](https://learn.chatgpt.com/docs/build-skills) · [Codex Hooks](https://learn.chatgpt.com/docs/hooks)

## 本地安装

克隆仓库后运行：

```bash
python3 install.py
```

测试：

```bash
python3 -m unittest discover -s tests -v
```
