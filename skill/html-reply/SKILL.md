---
name: html-reply
description: Render a response as a polished standalone HTML page with session history. Use only when the user explicitly asks for HTML output or explicitly invokes $html-reply. Never invoke implicitly for ordinary replies.
---

# HTML Reply

Turn every substantive answer into one focused HTML response that is easy to refresh, read, and verify.

## Invocation boundary

- Default to the normal chat response format.
- Use this Skill only when the current user message explicitly requests HTML output or names `$html-reply`.
- Do not infer permission from Codex Desktop, an open HTML tab, prior HTML replies, workspace files, or conversation history.
- One explicit invocation applies only to the current turn unless the user explicitly asks for HTML across multiple turns.

## Required workflow

1. Perform the task and verify its sources, code, or artifacts. Answer only the current request and lead with the outcome.
2. Obtain `<session-id>` only from the current process `CODEX_THREAD_ID`, then write only a body fragment to `output/.html-reply/drafts/reply-<session-id>.html`. Do not write doctype, `html`, `head`, `body`, `style`, `script`, history controls, or the stable reply page. Include one visible `<h1>` and one visible element marked `data-html-reply-summary`; the marked text is the exact final chat summary.
3. Run `scripts/publish.py --root <workspace>` once. The publisher takes `CODEX_THREAD_ID` as authoritative, archives the previous page, applies the fixed template, finalizes syntax highlighting and interactions, rebuilds the session-only history index, validates the output, and prints the summary plus both paths. Never call `path`, `archive`, and `finalize` separately during normal delivery.
4. Render the current reply and history index. Visually inspect typography, wrapping, search, navigation, history replay, image clarity, and overflow.
5. Return the publisher's exact summary sentence and two labelled links in this order: `历史总览`, then `当前回复`.

## Page construction

- Read [references/style-guide.md](references/style-guide.md) before creating or materially restyling a page.
- The publisher wraps the fragment with [assets/fragment-shell.html](assets/fragment-shell.html). Do not repeat its CSS or document boilerplate in the draft.
- Use semantic fragment structures such as `header`, `section`, `article`, `.grid`, `.card`, `.panel`, tables, lists, forms, and code blocks. Add inline style only when the current information cannot be expressed by the shared shell.
- Keep each page centered on the current request. Choose only the structure the answer needs: explanation, comparison, implementation report, review findings, or file delivery.
- Keep the fragment dependency-free so `file://` viewing works after publication.
- Mark code semantically as `<pre><code class="language-json">…</code></pre>` whenever the language is known. The finalizer performs dependency-free server-side syntax highlighting and falls back to lightweight language detection when the class is omitted.
- When a reply materially benefits from user choices, use a semantic `<form data-html-reply-interaction data-interaction-id="...">`. Put each question in a `<fieldset data-question="完整问题">`, give every input a stable `name`, and include `<p data-interaction-status></p>`. The finalizer restores drafts and automatically exports the current answers after a choice changes or a text field loses focus; do not require a separate Save button.
- Treat the generated `html-reply-response-<session-id>.json` as a session-scoped sidecar, not as a modified HTML file. The explicit-only version does not automatically read this file in the next turn.

## Task-specific handling

- For research or explanation, distinguish primary sources, secondary summaries, and inference.
- For code or implementation work, lead with the completed outcome, then show touched files, verification, and any remaining risk.
- For reviews, lead with actionable findings ordered by severity; state clearly when no findings remain.
- For deliverables, provide clickable local file links in the HTML and keep the chat response minimal.
- For PDFs, render evidence at 300 DPI, crop to the relevant content, let wide figures use the full content width, and add click-to-zoom.
- For short questions, still update the HTML, but keep the page proportionally short.

## Completion checks

- Confirm this session's stable file still exists at the same path.
- Confirm the filename contains the current process `CODEX_THREAD_ID`; reject a path copied from ambient browser context or a previous task.
- Confirm the draft filename also contains the current session id and no full-document boilerplate was written into it.
- Confirm the searchable `output/history-<session-id>.html` exists, includes the current reply plus archived replies, and its search can match titles, Prompt previews, and times.
- Confirm the stable filename exactly matches the current process `CODEX_THREAD_ID`. Never use shared `output/reply.html`.
- Confirm no `reply-local.html`, `history-local.html`, or `local` state was created as an identity fallback. Missing thread identity is a publishing error, not a reason to share files.
- Confirm short headings and complete short sentences stay on one line when space permits.
- Confirm abbreviations are expanded on first use.
- Confirm no image is broken, blurry, unnecessarily narrow, or cropped past relevant content.
- Confirm code samples show a readable language label and syntax colors; check both explicitly labelled code and any block that relies on automatic detection.
- If the page asks questions, confirm choices auto-save, text saves on blur, the visible status explains this behavior, and archived pages disable stale inputs.
- Confirm the previous response was archived; present the history index as the first link and the current stable reply as the second link.
- Confirm the finalized `<body>` contains `data-html-reply-theme="soft-bauhaus-v1"`; publisher validation, not a Stop Hook, owns this check.

## Integration

- Keep backups outside all discoverable `skills/` roots. A backup containing `SKILL.md` under `~/.agents/skills` or `$CODEX_HOME/skills` is another live Skill version, not an inert backup.
- Let `scripts/publish.py` own the deterministic production steps. If validation fails, fix the fragment or publisher rather than manually repeating path, archive, and finalize calls.
- No HTML Reply Hook is registered. Old tasks may retain cached Hook commands, so the compatibility scripts must not force HTML or block normal replies.
