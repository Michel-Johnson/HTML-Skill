# HTML Reply style guide

## Writing

- Write concise, plain Chinese appropriate to the user's level and task.
- Answer the exact question first. Avoid long background introductions.
- For explanations, teach one concept at a time and use concrete examples before abstractions.
- For reports, lead with the outcome; for reviews, lead with findings; for blockers, lead with the blocking condition.
- Distinguish facts, source claims, interpretation, and inference whenever that distinction matters.
- Expand every abbreviation on first use as `缩写 = English full name = 中文含义`.
- Explain non-abbreviation English terms when they first matter.
- When introducing a formula, explain every symbol and say whether the formula is quoted or reconstructed from prose.
- Prefer short paragraphs over dense bullet lists. Remove repetition and ornamental prose.

## Line wrapping

- Keep a complete short sentence or short heading on one line whenever the available canvas can hold it.
- Do not force early wrapping with narrow fixed columns, decorative grids, or unnecessary `max-width` values.
- Use `max-content` for short labels and `minmax(0,1fr)` for explanatory text.
- Allow natural wrapping only when the actual container is too narrow; switch to one column on small screens.
- Do not use tiny gray helper text. Default explanatory copy should be about 18px or larger; secondary labels, timestamps, captions, and history summaries must remain at least 16px on desktop.

## Visual language

- Use a soft-Bauhaus reading-report style: cream paper, charcoal lines, ochre accent, muted blue and green information panels.
- Use system sans-serif fonts only; avoid ornate serif or display fonts.
- Use low-radius corners around 4–6 px, restrained borders, and almost no shadows.
- Keep the page spacious but efficient. Let the main content use the available horizontal space.
- Preserve the user's approved page structure across replies; do not replace it with a new hero, dashboard, or centered showcase template merely because the current answer is a fix report.
- On wide screens, avoid fixed narrow `max-width` containers that leave large decorative gutters. Keep only a small outer margin and let the content expand with the viewport.
- Use a clear cover header, optional compact sticky table of contents, and a single reading column.
- Use color to distinguish meaning, not as decoration.

Suggested tokens:

```css
:root {
  --paper: #faf9f5;
  --paper-2: #efe8d6;
  --ink: #4f4a3c;
  --muted: #8a8271;
  --accent: #d9a441;
  --blue: #dce9f4;
  --green: #dcebd9;
}
```

The finalizer enforces this foundation under the versioned body marker `data-html-reply-theme="soft-bauhaus-v1"`. Author pages may choose their own information structure, but must not depend on a conflicting narrow canvas, large rounded surfaces, decorative shadows, ornate fonts, or a different page/ink palette.

## Information structure

Use only the sections needed by the current response:

1. Direct answer or outcome.
2. Minimal evidence, explanation, findings, or changed files.
3. A concrete example, comparison, verification result, or next step when useful.
4. Source note or artifact links when relevant.

Do not force every page into the same number of cards. Avoid dashboards, excessive badges, decorative statistics, and overly fragmented layouts.

## Code rendering

- Put code in semantic `<pre><code>` elements and prefer an explicit `language-*` class, such as `language-python` or `language-json`.
- Keep inline `code` styling separate from code blocks. Every `pre code` must use a transparent background, inherit the `pre` color, and reset padding and border radius so selectors such as `.blog-guide code` cannot create light strips inside a dark block.
- The finalizer automatically highlights JSON, Python, JavaScript, TypeScript, Shell, SQL, HTML, and CSS. When no language class is present, it performs lightweight detection and uses plain text if uncertain.
- Keep code rendering dependency-free and server-side so syntax colors remain visible under `file://`, history replay, static screenshots, and Quick Look.
- Show the detected language as a label of at least 16px. Code should remain at least 17px on desktop, preserve whitespace, and scroll horizontally instead of wrapping syntax unpredictably.
- Use a dark, high-contrast code surface with distinct colors for keys, strings, numbers, keywords, comments, tags, properties, and variables. Do not encode meaning with faint gray text alone.

## Conditional PDF evidence

- Prefer one focused crop over a complete page.
- Preserve the source PDF's sharpness with a 300 DPI PNG crop.
- Crop around the meaningful content but retain labels, legends, and captions needed to interpret it.
- Use the full article width for wide tables and flows.
- Add a concise Chinese caption and click-to-zoom interaction.
- If the screenshot is not necessary to answer the current question, omit it.

## Stable output behavior

- Treat `--root <workspace>` only as the project identity used to derive the workspace hash and resolve relative project resources. It is never the output parent.
- Before authoring, run `publish.py --root <workspace> --paths`; write the session-specific body fragment only to the returned `draft` path and the current user request (without ambient UI context) to `promptFile`. Both inputs are under the system temporary directory and are deleted after successful publication. Never pass a sensitive Prompt on the command line.
- Keep document boilerplate and the visual foundation in `assets/fragment-shell.html`. Do not spend model tokens restating the shared CSS on every turn.
- Resolve the persistent data root in this order: explicit `--data-dir`, `$HTML_REPLY_DATA_DIR`, `$CODEX_HOME/html-reply`, then `~/.codex/html-reply`. Reject any data root inside the workspace or a Git worktree. Permission failure is terminal; never fall back to the repository.
- Store persistent files under `<data-root>/workspaces/<workspace-hash>/threads/<session-id>/`. The workspace hash comes from the canonical absolute project path, and each thread owns one stable presentation file named `reply-<session-id>.html`. Replies within the same session refresh that file; different projects and sessions remain isolated.
- Take `<session-id>` from the current Codex process environment variable `CODEX_THREAD_ID` through `publish.py --root <workspace> --paths`. Never infer it from an open browser URL, an older reply, history, nested workspace metadata, or a hard-coded business script, and never collapse missing identity to `local`.
- Do not embed stable `reply-<id>.html` paths in reusable report generators. Pass the current helper-resolved output path into the generator or publish a neutral staging artifact afterward.
- Enforce the boundary in the publisher: it must reject a draft or target whose session ID differs from the current process `CODEX_THREAD_ID`.
- Keep one searchable history entry per session: `history-<session-id>.html` in the external session directory. Rebuild it on every finalize and list the current reply before archived replies.
- Archive every accepted or superseded response under the external session archive folder.
- In chat, link the history index first and the current stable reply second. Never expose a raw archive file as the primary history link.
- Keep related images and other Publisher-managed assets under the returned external `assets` directory with stable descriptive names.
- The finalizer rewrites project-relative resource URLs to absolute workspace file URLs while preserving page-local links such as `href="#section"`; do not add a global `<base>` tag.
- Migrate an old workspace `output/` only with `reply_history.py migrate --root <workspace>`. Use `migrate-shared` for the oldest shared `reply.html` format. Migration copies one source into the current valid session without overwriting external records and preserves every source file; deletion is a separate user decision.

## Prompt-aware history

- Every finalized page must include the injected horizontal History button in the top-right corner from `scripts/reply_history.py` and show only that session's history. Keep the primary left reading edge clear.
- Record the current user prompt with the page; redact common passwords, tokens, API keys, and secrets before persistence.
- The history drawer lists archived replies by title and time, with a short prompt preview.
- Opening an entry shows the original user prompt above and the archived HTML unchanged below in an iframe.
- Legacy pages created before prompt capture should say the prompt was not recorded; do not invent it.

## Visual QA

- Render at roughly 1400–1600 px width.
- Check the top of the page and all wide figures.
- Reject layouts with clipped text, unwanted single-word title wraps, broken local assets, tiny PDF text, excessive empty margins, or figures confined to a narrow prose column.
- Treat Publisher validation as the delivery check: the agent must create, archive, and visually verify the HTML before finalizing. No Stop Hook is registered.
