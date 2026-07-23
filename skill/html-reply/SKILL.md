---
name: html-reply
description: Render every substantive user-facing response as a polished standalone HTML page with one stable browser entry, concise Chinese writing, soft-Bauhaus styling, automatic response archiving, and visual verification. Use for explanations, analysis, reports, reviews, implementation summaries, file deliveries, research, learning, and any task where the user expects all formal replies to be written into the same refreshable HTML file.
---

# HTML Reply

Turn every substantive answer into one focused HTML response that is easy to refresh, read, and verify.

## Required workflow

1. Use the session-specific path injected by the Hook: `output/reply-<session-id>.html`. Keep one stable file per session, not one file per workspace.
2. Before overwriting, run the exact cross-platform archive command injected by the Hook to preserve this session's existing page.
3. Perform the task and verify relevant sources, files, code, or artifacts before writing the response.
4. Answer only the current request. Lead with the outcome, then add the minimum explanation, evidence, files, or next steps needed.
5. Update the injected `output/reply-<session-id>.html`. Never overwrite another session's page.
6. Run the exact cross-platform finalize command injected by the Hook. It applies the canonical `soft-bauhaus-v1` visual foundation, injects the top-right History trigger and left history drawer, records the current prompt, and indexes only this session's archived HTML pages.
7. Render the HTML and visually inspect typography, wrapping, spacing, drawer behavior, history replay, image clarity, and overflow before delivery.
8. Return only the stable page link and a short answer summary. Do not link archive files.

## Page construction

- Read [references/style-guide.md](references/style-guide.md) before creating or materially restyling a page.
- Start from [assets/reply-page-template.html](assets/reply-page-template.html) when no established page exists.
- Preserve an existing approved layout instead of rebuilding it unnecessarily.
- Let the finalizer normalize only the visual foundation: paper, ink, system font, wide canvas, restrained radius, and shadows. Keep the content structure free to use the tables, flows, cards, or prose the answer actually needs.
- Keep each page centered on the current request. Choose only the structure the answer needs: explanation, comparison, implementation report, review findings, or file delivery.
- Use local, dependency-free HTML/CSS/JavaScript so `file://` viewing works.
- Mark code semantically as `<pre><code class="language-json">…</code></pre>` whenever the language is known. The finalizer performs dependency-free server-side syntax highlighting and falls back to lightweight language detection when the class is omitted.
- When a reply materially benefits from user choices, use a semantic `<form data-html-reply-interaction data-interaction-id="...">`. Put each question in a `<fieldset data-question="完整问题">`, give every input a stable `name`, and include `<p data-interaction-status></p>`. The finalizer restores drafts and automatically exports the current answers after a choice changes or a text field loses focus; do not require a separate Save button.
- Treat the generated `html-reply-response-<session-id>.json` as a session-scoped sidecar, not as a modified HTML file. The next `UserPromptSubmit` Hook validates and consumes only a new matching response once. The current explicit user message always takes priority over older form data.

## Task-specific handling

- For research or explanation, distinguish primary sources, secondary summaries, and inference.
- For code or implementation work, lead with the completed outcome, then show touched files, verification, and any remaining risk.
- For reviews, lead with actionable findings ordered by severity; state clearly when no findings remain.
- For deliverables, provide clickable local file links in the HTML and keep the chat response minimal.
- For PDFs, render evidence at 300 DPI, crop to the relevant content, let wide figures use the full content width, and add click-to-zoom.
- For short questions, still update the HTML, but keep the page proportionally short.

## Completion checks

- Confirm this session's stable file still exists at the same path.
- Confirm the stable filename exactly matches the Hook-supplied session ID. Never use shared `output/reply.html` unless the Hook explicitly identifies the session as `legacy`.
- Confirm short headings and complete short sentences stay on one line when space permits.
- Confirm abbreviations are expanded on first use.
- Confirm no image is broken, blurry, unnecessarily narrow, or cropped past relevant content.
- Confirm code samples show a readable language label and syntax colors; check both explicitly labelled code and any block that relies on automatic detection.
- If the page asks questions, confirm choices auto-save, text saves on blur, the visible status explains this behavior, and archived pages disable stale inputs.
- Confirm the previous response was archived and the archive was not presented as the primary link.
- Confirm the finalized `<body>` contains `data-html-reply-theme="soft-bauhaus-v1"`; the Stop Hook rejects an unthemed page.

## Stop Hook enforcement

- Use `scripts/prompt_hook.py` from the global `UserPromptSubmit` Hook to inject this Skill's delivery contract into every turn, including new sessions.
- Use `scripts/stop_hook.py` from the local Codex `Stop` Hook to enforce this delivery protocol.
- Let the Hook pass only when the final message links a recently updated, valid local HTML file under `output/` and its concise summary sentence also appears as visible text inside that page.
- Treat “this turn's answer is delivered in HTML” as the completion condition; the mere existence of an HTML file is never enough.
- If validation fails, block completion once and return this Skill's execution instructions to Codex; allow the correction pass to stop to avoid an infinite Hook loop.
