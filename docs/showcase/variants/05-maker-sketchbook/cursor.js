// Cursor 外壳的本地交互；文件、终端和模型选项均为演示数据。
(() => {
  'use strict';
  const {text: t} = window.ShowcaseLocale;
  const root = document.querySelector('[data-cursor-screen]');
  if (!root) return;
  const player = document.querySelector('[data-usage-player]');
  const find = name => root.querySelector(`[data-cursor-${name}]`);
  const ui = Object.fromEntries(['popup', 'palette', 'filter', 'results', 'toast', 'welcome', 'file-editor', 'file-name', 'file-path', 'dirty', 'code', 'lines', 'position', 'language', 'search', 'search-results', 'git-summary', 'changes', 'terminal', 'terminal-output', 'terminal-input', 'restore'].map(name => [name, find(name)]));
  const files = {
    bookmarks: {name: 'bookmarks.ts', language: 'TypeScript', text: t('type Bookmark = {\n  title: string;\n  url: string;\n};\n\nexport function normalizeTitle(value: string) {\n  return value.trim();\n}\n\n// 书签列表与侧栏当前分别排序。\nexport function sortBookmarks(items: Bookmark[]) {\n  return [...items].sort((a, b) =>\n    a.title.localeCompare(b.title)\n  );\n}\n\nexport function sortSidebar(items: Bookmark[]) {\n  return [...items].sort((a, b) =>\n    a.title.localeCompare(b.title)\n  );\n}\n', "type Bookmark = {\n  title: string;\n  url: string;\n};\n\nexport function normalizeTitle(value: string) {\n  return value.trim();\n}\n\n// The bookmark list and sidebar currently sort separately.\nexport function sortBookmarks(items: Bookmark[]) {\n  return [...items].sort((a, b) =>\n    a.title.localeCompare(b.title)\n  );\n}\n\nexport function sortSidebar(items: Bookmark[]) {\n  return [...items].sort((a, b) =>\n    a.title.localeCompare(b.title)\n  );\n}\n")},
    readme: {name: 'README.md', language: 'Markdown', text: t('# Bookmarks\n\n用于 HTML Reply 宣传页的虚构书签应用。\n\n## 试一试\n\n1. 在右侧 Agent 输入框中调用 /html-reply。\n2. 点击发送，观察整理内容、生成 HTML 的过程。\n3. 点击“当前回复”阅读真实的公开示例。\n\n这是交互演示，不会请求模型或操作本地仓库。\nCursor 原生接入尚未适配；结果不是根据输入即时生成的。\n', "# Bookmarks\n\nA fictional bookmark app for the HTML Reply showcase.\n\n## Try it\n\n1. Call /html-reply in the Agent input on the right.\n2. Send the request to see content preparation and HTML generation.\n3. Open “Current reply” to read the public example.\n\nThis is an interactive demo. It does not call a model or change a local repository.\nCursor native integration is not yet supported. Results are not generated from your input.\n")},
    skill: {name: '.cursor/skills/html-reply/SKILL.md', language: 'Markdown', text: t('# HTML Reply · 公开演示\n\n将回答组织为可阅读的独立 HTML。\n\n先给结论，再列出问题与修改建议。\n\n这里的文件树用于演示调用位置，\n不表示当前已完成 Cursor 原生适配。\n', "# HTML Reply · Public demo\n\nTurn an answer into a readable, standalone HTML page.\n\nStart with the conclusion, then list issues and suggested changes.\n\nThis file tree illustrates where a Skill would be called.\nIt does not imply that Cursor native integration is already supported.\n")}
  };
  Object.values(files).forEach(file => { file.saved = file.text; file.undo = []; file.redo = []; });
  let currentFile = null;
  const history = [];
  let historyIndex = -1;
  let menuAnchor = null;
  let paletteAnchor = null;
  let toastTimer;
  let mode = 'Agent';
  let model = 'Cursor Grok 4.6 High Fast';

  const command = (action, details = {}) => root.dispatchEvent(new CustomEvent('cursor-demo:command', {detail: {action, ...details}}));
  const notice = text => {
    clearTimeout(toastTimer);
    ui.toast.textContent = text;
    ui.toast.hidden = false;
    toastTimer = setTimeout(() => { ui.toast.hidden = true; }, 2600);
  };
  const pressed = (action, value) => root.querySelectorAll(`[data-cursor-action="${action}"][aria-pressed]`).forEach(button => button.setAttribute('aria-pressed', String(value)));
  const item = (label, action, shortcut = '', value = '') => ({label, action, shortcut, value});
  const viewItems = [item('Explorer', 'explorer'), item('Search', 'search', 'Ctrl+Shift+F'), item('Source Control', 'source'), item('Toggle Primary Side Bar', 'sidebar', 'Ctrl+B'), item('Toggle Agent', 'agent'), item('Toggle Terminal', 'terminal', 'Ctrl+J')];
  const menus = {
    file: [item('New Text File', 'new-file'), item('Open File…', 'quick-open', 'Ctrl+P'), item('Save', 'save', 'Ctrl+S'), item('Close Editor', 'close-file')],
    edit: [item('Undo', 'undo', 'Ctrl+Z'), item('Redo', 'redo', 'Ctrl+Shift+Z'), item('Find in Files', 'search', 'Ctrl+Shift+F')],
    selection: [item('Select All', 'select-all', 'Ctrl+A'), item('Select Line', 'select-line')],
    view: viewItems,
    views: viewItems,
    go: [item('Go to File…', 'quick-open', 'Ctrl+P'), item('Back', 'back-file'), item('Forward', 'forward-file')],
    run: [item('Start Demo', 'resume'), item('Pause Demo', 'pause'), item('Restart Demo', 'replay')],
    terminal: [item('New Terminal', 'show-terminal'), item('Clear Terminal', 'clear-terminal')],
    help: [item(t('HTML Reply 使用说明', "HTML Reply guide"), 'readme'), item('Keyboard Shortcuts', 'welcome')],
    history: [item(t('整理审查报告', "Prepare review report"), 'conversation'), item(t('打开 HTML 历史', "Open reply history"), 'open-history'), item('New Agent', 'new-agent')],
    agent: [item('New Agent', 'new-agent'), item('Replay Demo', 'replay'), item('Open HTML', 'open-result')],
    mode: ['Agent', 'Ask', 'Plan'].map(value => item(value, 'set-mode', '', value)),
    model: ['Cursor Grok 4.6 High Fast', 'Auto'].map(value => item(value, 'set-model', '', value))
  };

  function closeMenu(restoreFocus = false) {
    ui.popup.hidden = true;
    if (menuAnchor) {
      menuAnchor.setAttribute('aria-expanded', 'false');
      if (restoreFocus) menuAnchor.focus();
    }
    menuAnchor = null;
  }

  function openMenu(anchor, focusFirst = false) {
    if (menuAnchor === anchor) { closeMenu(); return; }
    closeMenu();
    closePalette();
    menuAnchor = anchor;
    anchor.setAttribute('aria-expanded', 'true');
    ui.popup.replaceChildren();
    for (const entry of menus[anchor.dataset.cursorMenu] || []) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.cursorAction = entry.action;
      button.dataset.cursorValue = entry.value;
      button.disabled = (['save', 'close-file'].includes(entry.action) && !currentFile)
        || (entry.action === 'undo' && (!currentFile || !files[currentFile].undo.length))
        || (entry.action === 'redo' && (!currentFile || !files[currentFile].redo.length))
        || (entry.action === 'back-file' && historyIndex <= 0)
        || (entry.action === 'forward-file' && historyIndex >= history.length - 1);
      button.setAttribute('role', entry.value ? 'menuitemradio' : 'menuitem');
      if (entry.value) button.setAttribute('aria-checked', String(entry.value === (entry.action === 'set-mode' ? mode : model)));
      const label = document.createElement('span');
      label.textContent = entry.label;
      button.append(label);
      if (entry.shortcut) {
        const shortcut = document.createElement('kbd');
        shortcut.textContent = entry.shortcut;
        button.append(shortcut);
      }
      ui.popup.append(button);
    }
    ui.popup.hidden = false;
    const bounds = root.getBoundingClientRect();
    const target = anchor.getBoundingClientRect();
    const popup = ui.popup.getBoundingClientRect();
    const left = Math.max(6, Math.min(target.left - bounds.left, bounds.width - popup.width - 6));
    const below = target.bottom - bounds.top + 3;
    const top = below + popup.height < bounds.height ? below : Math.max(6, target.top - bounds.top - popup.height - 3);
    ui.popup.style.left = left + 'px';
    ui.popup.style.top = top + 'px';
    if (focusFirst) [...ui.popup.querySelectorAll('button')].find(button => !button.disabled)?.focus();
  }

  function fileButton(key, detail) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.cursorFile = key;
    const label = document.createElement('span');
    label.textContent = files[key].name;
    button.append(label);
    if (detail) {
      const path = document.createElement('span');
      path.textContent = detail;
      button.append(path);
    }
    return button;
  }

  function renderSearch(container, query, contentSearch = false) {
    container.replaceChildren();
    const term = query.trim().toLowerCase();
    const matches = Object.entries(files).filter(([, file]) => (file.name + (contentSearch ? '\n' + file.text : '')).toLowerCase().includes(term));
    for (const [key, file] of matches) {
      const line = term && contentSearch ? file.text.split('\n').find(line => line.toLowerCase().includes(term)) : '';
      container.append(fileButton(key, line || 'bookmarks'));
    }
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.textContent = t('没有匹配的演示文件', "No matching demo files");
      container.append(empty);
    }
  }

  function closePalette(restoreFocus = false) {
    ui.palette.hidden = true;
    if (restoreFocus) paletteAnchor?.focus();
    paletteAnchor = null;
  }

  function quickOpen(anchor) {
    closeMenu();
    paletteAnchor = anchor || document.activeElement;
    ui.palette.hidden = false;
    ui.filter.value = '';
    renderSearch(ui.results, '');
    ui.filter.focus();
  }

  function setView(value) {
    root.dataset.sidebarHidden = 'false';
    root.dataset.chatMaximized = 'false';
    root.querySelectorAll('[data-cursor-pane]').forEach(pane => { pane.hidden = pane.dataset.cursorPane !== value; });
    root.querySelectorAll('[data-cursor-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.cursorView === value)));
    pressed('sidebar', true);
    pressed('maximize-chat', false);
    if (value === 'search') {
      renderSearch(ui['search-results'], ui.search.value, true);
      ui.search.focus();
    }
    if (value === 'source') renderChanges();
  }

  function showWorkspace() {
    if (player.dataset.phase === 'result') command('back');
    root.dataset.chatMaximized = 'false';
    pressed('maximize-chat', false);
  }

  function updatePosition() {
    const before = ui.code.value.slice(0, ui.code.selectionStart);
    ui.position.textContent = `Ln ${before.split('\n').length}, Col ${before.length - before.lastIndexOf('\n')}`;
  }

  function renderChanges() {
    ui.changes.replaceChildren();
    const changed = Object.keys(files).filter(key => files[key].text !== files[key].saved);
    ui['git-summary'].textContent = changed.length ? t(`${changed.length} 个文件未保存（仅本页）`, `${changed.length} unsaved ${changed.length === 1 ? 'file' : 'files'} (this page only)`) : t('没有未保存的更改', "No unsaved changes");
    changed.forEach(key => ui.changes.append(fileButton(key, 'M')));
    ui.dirty.hidden = !currentFile || files[currentFile].text === files[currentFile].saved;
  }

  function renderEditor() {
    const file = files[currentFile];
    ui.code.value = file.text;
    ui.lines.textContent = file.text.split('\n').map((_, index) => index + 1).join('\n');
    ui['file-name'].textContent = file.name.split('/').pop();
    ui['file-path'].textContent = file.name;
    ui.language.textContent = file.language;
    ui['file-editor'].hidden = false;
    ui.welcome.hidden = true;
    root.dataset.editorOpen = 'true';
    root.querySelectorAll('[data-cursor-file]').forEach(button => {
      if (button.dataset.cursorFile === currentFile) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
    find('back').disabled = historyIndex <= 0;
    find('forward').disabled = historyIndex >= history.length - 1;
    renderChanges();
    updatePosition();
  }

  function openFile(key, line = 1, addHistory = true) {
    if (!files[key]) return;
    closeMenu();
    closePalette();
    showWorkspace();
    if (addHistory && history[historyIndex] !== key) {
      history.splice(historyIndex + 1);
      history.push(key);
      historyIndex = history.length - 1;
    }
    currentFile = key;
    renderEditor();
    const position = ui.code.value.split('\n').slice(0, Math.max(0, line - 1)).reduce((total, text) => total + text.length + 1, 0);
    ui.code.setSelectionRange(position, position);
    ui.code.scrollTop = Math.max(0, line - 3) * 23;
    ui.lines.scrollTop = ui.code.scrollTop;
    ui.code.focus();
    updatePosition();
  }

  function closeFile() {
    currentFile = null;
    ui['file-editor'].hidden = true;
    ui.welcome.hidden = false;
    root.dataset.editorOpen = 'false';
    root.querySelectorAll('[data-cursor-file]').forEach(button => button.removeAttribute('aria-current'));
  }

  function toggleSection(name, action, expanded) {
    const section = find(name);
    section.hidden = expanded === undefined ? !section.hidden : !expanded;
    const button = root.querySelector(`[data-cursor-action="${action}"]`);
    button.setAttribute('aria-expanded', String(!section.hidden));
    const chevron = button.querySelector('span');
    if (chevron) chevron.textContent = section.hidden ? '›' : '⌄';
  }

  function showTerminal(forceOpen = false) {
    showWorkspace();
    ui.terminal.hidden = forceOpen ? false : !ui.terminal.hidden;
    if (!ui.terminal.hidden) ui['terminal-input'].focus();
  }

  function restoreWindow() {
    delete root.dataset.collapsed;
    ui.restore.hidden = true;
  }

  function act(action, button) {
    const value = button?.dataset.cursorValue;
    closeMenu();
    if (root.dataset.collapsed && !['minimize', 'close-window'].includes(action)) restoreWindow();
    if (['explorer', 'search', 'source'].includes(action)) setView(action);
    else if (action === 'folder') toggleSection('project-files', action);
    else if (action === 'skill-folder') toggleSection('skill-files', action);
    else if (action === 'outline' || action === 'timeline') toggleSection(action, action);
    else if (action === 'quick-open') quickOpen(button);
    else if (action === 'readme') openFile('readme');
    else if (action === 'close-file' || action === 'welcome') { showWorkspace(); closeFile(); }
    else if (action === 'new-file') {
      if (!files.untitled) files.untitled = {name: 'Untitled-1', language: 'Plain Text', text: '', saved: '', undo: [], redo: []};
      openFile('untitled');
    } else if (action === 'save') {
      if (!currentFile) { quickOpen(button); return; }
      files[currentFile].saved = files[currentFile].text;
      renderChanges();
      notice(t('已保存在本次演示中；刷新页面会还原。', "Saved in this demo. Reload the page to reset."));
    } else if (action === 'undo' || action === 'redo') {
      if (!currentFile) return;
      const file = files[currentFile];
      const from = action === 'undo' ? file.undo : file.redo;
      const to = action === 'undo' ? file.redo : file.undo;
      if (!from.length) { notice(action === 'undo' ? t('没有可撤销的编辑', "Nothing to undo") : t('没有可重做的编辑', "Nothing to redo")); return; }
      to.push(file.text);
      file.text = from.pop();
      renderEditor();
      ui.code.focus();
    } else if (action === 'select-all' || action === 'select-line') {
      if (!currentFile) openFile('bookmarks');
      ui.code.focus();
      const text = ui.code.value;
      const start = action === 'select-all' ? 0 : text.lastIndexOf('\n', Math.max(0, ui.code.selectionStart - 1)) + 1;
      const end = action === 'select-all' ? text.length : text.indexOf('\n', ui.code.selectionEnd);
      ui.code.setSelectionRange(start, end < 0 ? text.length : end);
    } else if (action === 'back-file' || action === 'forward-file') {
      const next = historyIndex + (action === 'back-file' ? -1 : 1);
      if (next >= 0 && next < history.length) { historyIndex = next; openFile(history[next], 1, false); }
    } else if (action === 'sidebar') {
      root.dataset.sidebarHidden = String(root.dataset.sidebarHidden !== 'true');
      root.dataset.chatMaximized = 'false';
      pressed('sidebar', root.dataset.sidebarHidden !== 'true');
      pressed('maximize-chat', false);
    } else if (action === 'agent') {
      root.dataset.agentHidden = String(root.dataset.agentHidden !== 'true');
      root.dataset.chatMaximized = 'false';
      pressed('agent', root.dataset.agentHidden !== 'true');
      pressed('maximize-chat', false);
    } else if (action === 'maximize-chat') {
      root.dataset.chatMaximized = String(root.dataset.chatMaximized !== 'true');
      root.dataset.agentHidden = 'false';
      pressed('agent', true);
      pressed('maximize-chat', root.dataset.chatMaximized === 'true');
    } else if (action === 'terminal' || action === 'show-terminal') showTerminal(action === 'show-terminal');
    else if (action === 'clear-terminal') { showTerminal(true); ui['terminal-output'].textContent = ''; }
    else if (action === 'workspace') { setView('explorer'); toggleSection('project-files', 'folder', true); openFile('readme'); }
    else if (action === 'attach' || action === 'detach') find('context-chip').hidden = action === 'detach';
    else if (action === 'set-mode') { mode = value; find('mode-label').textContent = mode; }
    else if (action === 'set-model') { model = value; find('model-label').textContent = model; }
    else if (action === 'minimize' || action === 'close-window') {
      command('pause');
      root.dataset.collapsed = action;
      ui.restore.hidden = false;
    } else if (action === 'restore') restoreWindow();
    else if (action === 'maximize') {
      restoreWindow();
      root.dataset.expanded = String(root.dataset.expanded !== 'true');
      pressed('maximize', root.dataset.expanded === 'true');
    } else if (action === 'open-result' || action === 'open-history') {
      root.dataset.chatMaximized = 'false';
      command('open', {file: action === 'open-history' ? 'history' : 'review'});
    } else if (action === 'conversation') { restoreWindow(); command('ready'); }
    else if (action === 'edit-prompt') command('edit');
    else if (['new-agent', 'play', 'pause', 'replay', 'send', 'resume'].includes(action)) {
      restoreWindow();
      root.dataset.agentHidden = 'false';
      pressed('agent', true);
      command(action);
    }
  }

  root.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || !root.contains(button)) return;
    if (button.hasAttribute('data-cursor-menu')) openMenu(button);
    else if (button.dataset.cursorFile) openFile(button.dataset.cursorFile, Number(button.dataset.cursorLine) || 1);
    else if (button.dataset.cursorAction) act(button.dataset.cursorAction, button);
  });
  root.addEventListener('cursor-demo:reset', () => {
    restoreWindow();
    root.dataset.agentHidden = 'false';
    root.dataset.chatMaximized = 'false';
    pressed('agent', true);
    pressed('maximize-chat', false);
  });
  ui.filter.addEventListener('input', () => renderSearch(ui.results, ui.filter.value));
  ui.search.addEventListener('input', () => renderSearch(ui['search-results'], ui.search.value, true));
  ui.code.addEventListener('input', () => {
    if (!currentFile) return;
    const file = files[currentFile];
    file.undo.push(file.text);
    if (file.undo.length > 100) file.undo.shift();
    file.redo = [];
    file.text = ui.code.value;
    ui.lines.textContent = file.text.split('\n').map((_, index) => index + 1).join('\n');
    renderChanges();
    updatePosition();
  });
  ui.code.addEventListener('scroll', () => { ui.lines.scrollTop = ui.code.scrollTop; });
  ui.code.addEventListener('click', updatePosition);
  ui.code.addEventListener('keyup', updatePosition);
  ui['terminal-input'].addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.isComposing) return;
    event.preventDefault();
    const text = ui['terminal-input'].value.trim();
    ui['terminal-input'].value = '';
    if (!text) return;
    if (text.toLowerCase() === 'clear' || text.toLowerCase() === 'cls') { ui['terminal-output'].textContent = ''; return; }
    const replies = {help: t('help  查看示例命令\npwd   查看虚构路径\nls    列出示例文件\nclear 清空面板', "help  Show demo commands\npwd   Show the fictional path\nls    List demo files\nclear Clear the panel"), pwd: 'C:\\demo\\bookmarks', ls: '.cursor/\nbookmarks.ts\nREADME.md', dir: '.cursor/\nbookmarks.ts\nREADME.md'};
    ui['terminal-output'].textContent += '\n> ' + text + '\n' + (replies[text.toLowerCase()] || t('这是模拟终端，不会执行命令。输入 help 查看示例。', "This terminal is simulated. No commands run. Type help for examples.")) + '\n';
    ui['terminal-output'].scrollTop = ui['terminal-output'].scrollHeight;
  });

  root.addEventListener('keydown', event => {
    if (event.isComposing) return;
    const button = event.target.closest('button');
    if (event.key === 'Escape') {
      if (!ui.popup.hidden) closeMenu(true);
      else if (!ui.palette.hidden) closePalette(true);
      else if (root.dataset.expanded === 'true') { root.dataset.expanded = 'false'; pressed('maximize', false); }
      else if (player.dataset.phase === 'working') command('pause');
      event.preventDefault();
      return;
    }
    const list = !ui.popup.hidden ? ui.popup : !ui.palette.hidden ? ui.results : null;
    if (list && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      const buttons = [...list.querySelectorAll('button')].filter(button => !button.disabled);
      if (!buttons.length) return;
      const index = buttons.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : index < 0 ? event.key === 'ArrowUp' ? buttons.length - 1 : 0 : (index + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length;
      event.preventDefault();
      buttons[next].focus();
      return;
    }
    if (!ui.palette.hidden && event.key === 'Enter' && event.target === ui.filter) { event.preventDefault(); ui.results.querySelector('button')?.click(); return; }
    if (button?.hasAttribute('data-cursor-menu') && ['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); openMenu(button, true); return; }
    if (button?.closest('.cursor-menubar') && ['ArrowRight', 'ArrowLeft'].includes(event.key)) {
      const buttons = [...root.querySelectorAll('.cursor-menubar button')];
      const next = (buttons.indexOf(button) + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      event.preventDefault();
      const open = !ui.popup.hidden;
      closeMenu();
      buttons[next].focus();
      if (open) openMenu(buttons[next]);
      return;
    }
    if (!(event.ctrlKey || event.metaKey)) return;
    const key = event.key.toLowerCase();
    let action;
    if (key === 'p') action = 'quick-open';
    else if (key === 'j') action = 'terminal';
    else if (key === 'b') action = event.shiftKey ? 'open-result' : 'sidebar';
    else if (key === 'l' && event.shiftKey) action = 'new-agent';
    else if (key === 'e' && event.altKey) action = 'maximize-chat';
    else if (key === 'a' && event.altKey) action = 'workspace';
    else if (key === 'f' && event.shiftKey) action = 'search';
    else if (event.target === ui.code && key === 's') action = 'save';
    else if (event.target === ui.code && key === 'z') action = event.shiftKey ? 'redo' : 'undo';
    if (action) { event.preventDefault(); act(action, button); }
  });
  document.addEventListener('pointerdown', event => {
    if (!ui.popup.contains(event.target) && !event.target.closest('[data-cursor-menu]')) closeMenu();
    if (!ui.palette.contains(event.target)) closePalette();
  });
  // 打开结果时优先显示文档；编辑器交互不改变自动播放状态。
  let previousPhase = player.dataset.phase;
  new MutationObserver(() => {
    if (player.dataset.running === 'true' && root.dataset.collapsed) restoreWindow();
    if (player.dataset.phase === 'result' && previousPhase !== 'result') {
      root.dataset.chatMaximized = 'false';
      pressed('maximize-chat', false);
    }
    previousPhase = player.dataset.phase;
    if (root.hidden) { closeMenu(); closePalette(); }
  }).observe(player, {attributes: true, attributeFilter: ['data-phase', 'data-platform', 'data-running']});
})();
