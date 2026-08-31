// 工作台外壳的本地控件；不安装Skill、不修改软件设置、不请求模型或执行命令。
(() => {
  'use strict';
  const {text: t} = window.ShowcaseLocale;
  const player = document.querySelector('[data-usage-player]');
  if (!player) return;
  const examples = [...player.querySelectorAll('[data-usage-file]')].map(button => ({file: button.dataset.usageFile, title: button.textContent}));
  const create = (tag, attributes = {}, text = '') => {
    const node = document.createElement(tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    node.textContent = text;
    return node;
  };
  const item = (label, action, value = '', checked = null) => ({label, action, value, checked});

  player.querySelectorAll('[data-workbench]').forEach(root => {
    if (!root.querySelector('[data-demo-input]')) return; // Cursor沿用独立的编辑器控制器。
    const platform = root.dataset.workbench;
    const popup = create('div', {class: 'demo-popup', 'data-demo-popup': '', role: 'menu', 'aria-label': t('本地演示菜单', "Local demo menu")});
    const toast = create('div', {class: 'demo-toast', 'data-demo-toast': '', role: 'status'});
    const restore = create('div', {class: 'demo-restore', 'data-demo-restore': ''});
    const restoreLabel = create('p');
    restore.append(restoreLabel, create('button', {type: 'button', 'data-demo-action': 'restore'}, t('重新打开演示', "Reopen demo")));
    popup.hidden = toast.hidden = restore.hidden = true;
    root.append(popup, toast, restore);
    let anchor = null;
    let toastTimer;
    let model = platform === 'claude' ? 'Opus' : 'Ultra';
    let permission = platform === 'claude' ? 'Manual' : t('权限', "Permissions");
    const permissions = platform === 'claude' ? ['Manual', 'Accept edits', 'Plan'] : [t('权限', "Permissions"), t('只读', "Read only"), t('默认权限', "Default permissions")];
    const command = (action, details = {}) => root.dispatchEvent(new CustomEvent('showcase-demo:command', {detail: {action, ...details}}));
    const notice = text => {
      clearTimeout(toastTimer);
      toast.textContent = text;
      toast.hidden = false;
      toastTimer = setTimeout(() => { toast.hidden = true; }, 3200);
    };

    function closePopup(restoreFocus = false) {
      popup.hidden = true;
      if (anchor) {
        anchor.setAttribute('aria-expanded', 'false');
        if (restoreFocus) anchor.focus();
      }
      anchor = null;
    }

    function positionPopup(target) {
      popup.hidden = false;
      const bounds = root.getBoundingClientRect();
      const rect = target.getBoundingClientRect();
      const size = popup.getBoundingClientRect();
      popup.style.left = Math.max(8, Math.min(rect.left - bounds.left, bounds.width - size.width - 8)) + 'px';
      const below = rect.bottom - bounds.top + 4;
      popup.style.top = (below + size.height <= bounds.height - 8 ? below : Math.max(8, rect.top - bounds.top - size.height - 4)) + 'px';
    }

    function menuItems(name) {
      const files = examples.map(example => item(example.title, 'open-file', example.file));
      const playback = [item(t('播放演示', "Play demo"), 'play'), item(t('暂停演示', "Pause demo"), 'pause'), item(t('重播完整流程', "Replay the full workflow"), 'replay')];
      if (name === 'file' || name === 'terminal') return [item(t('新建演示会话', "New demo session"), 'new-session'), ...files, item(t('关闭演示', "Close demo"), 'close')];
      if (name === 'edit') return [item(t('编辑请求', "Edit request"), 'edit'), item(t('复制审查摘要', "Copy review summary"), 'copy'), item(t('重置演示输入', "Reset demo input"), 'new-session')];
      if (name === 'view') return [item(t('显示 / 隐藏侧栏', "Show / hide sidebar"), 'sidebar'), item(t('打开 / 关闭 HTML 预览', "Open / close HTML preview"), 'preview'), item(t('展开 / 恢复高度', "Expand / restore height"), 'maximize')];
      if (name === 'model') return (platform === 'claude' ? ['Opus', 'Sonnet', 'Haiku'] : ['Low', 'Medium', 'Ultra']).map(value => item(platform === 'claude' ? value : 'gpt-5.6-sol · ' + value, 'set-model', value, value === model));
      if (name === 'permission') return permissions.map(value => item(value, 'set-permission', value, value === permission));
      if (name === 'conversation') return [...playback, item(t('历史总览', "All replies"), 'open-file', 'history.html'), item(t('复制审查摘要', "Copy review summary"), 'copy')];
      if (name === 'attach') return [item(t('bookmarks.ts（公开虚构文件）', "bookmarks.ts (fictional public file)"), 'attach'), item(t('移除附件', "Remove attachment"), 'detach')];
      if (name === 'plugins') return [item(t('HTML Reply · 插入演示引用', "HTML Reply · Insert demo Skill"), 'use-skill'), item(t('查看生成示例', "Open generated example"), 'open-file', 'review.html')];
      if (name === 'branch') return [item(t('main（仅演示，不切换仓库分支）', "main (demo only; no repository changes)"), 'local')];
      if (name === 'account') return [item(t('演示用户 · 不关联真实账号', "Demo user · No real account connected"), 'local'), item(t('重新播放', "Replay"), 'replay')];
      return [...playback, item(t('Enter 发送 · Shift+Enter 换行', "Enter to send · Shift+Enter for a new line"), 'edit'), item(t('Tab 选择 Skill · Esc 暂停 / 关闭', "Tab to select a Skill · Esc to pause / close"), 'use-skill')];
    }

    function addMenuItems(items) {
      items.forEach(entry => {
        const button = create('button', {type: 'button', role: entry.checked === null ? 'menuitem' : 'menuitemradio', 'data-demo-action': entry.action, 'data-demo-value': entry.value}, entry.label);
        if (entry.checked !== null) button.setAttribute('aria-checked', String(entry.checked));
        popup.append(button);
      });
    }

    function openMenu(target, name = target.dataset.demoMenu) {
      if (anchor === target && !popup.hidden) { closePopup(true); return; }
      closePopup();
      anchor = target;
      target.setAttribute('aria-expanded', 'true');
      popup.replaceChildren();
      popup.setAttribute('role', name === 'search' ? 'dialog' : 'menu');
      popup.setAttribute('aria-label', name === 'search' ? t('查找公开示例', "Find public examples") : t('本地演示菜单', "Local demo menu"));
      if (name === 'search') {
        const input = create('input', {'aria-label': t('输入示例名称', "Enter an example name"), placeholder: t('查找公开示例…', "Find a public example…"), 'data-demo-search': '', autocomplete: 'off'});
        const choices = create('div');
        const filter = () => {
          choices.replaceChildren();
          const matches = examples.filter(example => example.title.toLocaleLowerCase().includes(input.value.trim().toLocaleLowerCase()));
          matches.forEach(example => choices.append(create('button', {type: 'button', 'data-demo-action': 'open-file', 'data-demo-value': example.file}, example.title)));
          if (!matches.length) choices.append(create('p', {}, t('没有匹配的公开示例', "No matching public examples")));
        };
        input.addEventListener('input', filter);
        popup.append(input, choices);
        filter(); positionPopup(target); input.focus();
      } else {
        addMenuItems(menuItems(name));
        positionPopup(target);
        popup.querySelector('button')?.focus();
      }
    }

    function showCopy(text, target) {
      closePopup();
      anchor = target;
      popup.setAttribute('role', 'dialog');
      popup.setAttribute('aria-label', t('复制演示内容', "Copy demo content"));
      const field = create('textarea', {'aria-label': t('可复制的演示内容', "Demo content to copy"), readonly: ''});
      field.value = text;
      popup.replaceChildren(create('p', {}, t('已选中内容，可按 Ctrl+C 复制。', "Content selected. Press Ctrl+C to copy.")), field, create('button', {type: 'button', 'data-demo-action': 'close-popup'}, t('关闭', "Close")));
      positionPopup(target);
      field.focus(); field.setSelectionRange(0, text.length);
    }

    async function copy(text, target) {
      try {
        if (!navigator.clipboard?.writeText) { showCopy(text, target); return; }
        await navigator.clipboard.writeText(text);
        notice(t('已复制演示内容', "Demo content copied"));
      } catch { showCopy(text, target); }
    }

    function setPermission(value) {
      permission = value;
      root.querySelectorAll('[data-demo-permission-label]').forEach(label => { label.textContent = value; });
    }

    function sidebarVisible() {
      return root.dataset.demoSidebar === 'shown' || (root.dataset.demoSidebar !== 'hidden' && root.clientWidth > 700);
    }

    function syncSidebar() {
      root.querySelectorAll('[data-demo-action="sidebar"]').forEach(button => button.setAttribute('aria-pressed', String(sidebarVisible())));
    }

    function act(action, value, target) {
      if (action === 'close-popup') { closePopup(true); return; }
      const origin = anchor || target;
      closePopup(true);
      if (['play', 'pause', 'replay', 'edit', 'send', 'back', 'forward', 'preview', 'conversation', 'use-skill'].includes(action)) {
        if (action === 'conversation') resetWindow();
        command(action);
      } else if (action === 'open-file') command('open', {file: value});
      else if (action === 'new-session') {
        resetWindow(); root.dataset.demoNewSession = 'true';
        const title = root.querySelector('.codex-thread-title');
        if (title) title.textContent = t('新对话', "New thread");
        command('new-session');
      } else if (action === 'project') {
        const expanded = target.getAttribute('aria-expanded') !== 'true';
        target.setAttribute('aria-expanded', String(expanded));
        const group = target.closest('.codex-project-group');
        [...group.querySelectorAll('.codex-recent-task'), ...group.querySelectorAll('.codex-selected-task')].forEach(node => { node.hidden = !expanded; });
      } else if (action === 'sidebar') {
        const hidden = sidebarVisible();
        root.dataset.demoSidebar = hidden ? 'hidden' : 'shown';
        syncSidebar();
      } else if (action === 'minimize' || action === 'close') {
        command('pause'); root.dataset.demoWindow = action;
        restoreLabel.textContent = action === 'close' ? t('演示已关闭', "Demo closed") : t('演示已最小化', "Demo minimized");
        restore.hidden = false; restore.querySelector('button').focus();
      } else if (action === 'restore') {
        delete root.dataset.demoWindow; restore.hidden = true;
        const editor = root.querySelector('[data-demo-editor]');
        root.querySelector(editor.hidden ? '[data-demo-edit]' : '[data-demo-input]').focus();
      } else if (action === 'maximize') {
        root.dataset.demoExpanded = String(root.dataset.demoExpanded !== 'true');
      } else if (action === 'set-model') {
        model = value;
        root.querySelectorAll('[data-demo-model-label]').forEach(label => { label.textContent = platform === 'claude' ? value : platform === 'app' ? '5.6 Sol' : 'gpt-5.6-sol ' + value.toLowerCase(); });
        root.querySelectorAll('[data-demo-effort]').forEach(label => { label.textContent = value; });
      } else if (action === 'set-permission') setPermission(value);
      else if (action === 'attach' || action === 'detach') {
        const attachment = root.querySelector('[data-demo-attachment]');
        if (attachment) attachment.hidden = action === 'detach';
      } else if (action === 'copy') copy(root.querySelector('.codex-context')?.textContent || t('先补空标题校验，再合并重复排序逻辑。', "Validate empty titles first, then deduplicate the sorting logic."), origin);
      else if (action === 'share') {
        const result = player.querySelector('[data-usage-result]');
        const link = result.hidden ? create('a', {href: player.querySelector('[data-usage-frame]').dataset.src}) : result.querySelector('.usage-result-toolbar a');
        showCopy(link.href || link.getAttribute('href'), origin);
      } else if (action === 'voice') {
        notice(t('本地演示不访问麦克风，可直接输入请求。', "This local demo does not access your microphone. Type your request instead.")); command('edit');
      } else {
        const messages = {
          notifications: t('暂无演示通知。', "No demo notifications."),
          'pull-request': t('本地演示未连接 GitHub，不会创建 Pull Request。', "This local demo is not connected to GitHub and will not create a pull request."),
          scheduled: t('当前没有演示计划任务。', "No scheduled demo tasks."),
          local: t('仅操作本页公开示例，不修改真实软件、仓库或账号。', "Only the public examples on this page are affected. Real apps, repositories, and accounts stay unchanged.")
        };
        if (messages[action]) notice(messages[action]);
      }
    }

    function resetWindow() {
      closePopup(); clearTimeout(toastTimer); toast.hidden = restore.hidden = true;
      delete root.dataset.demoWindow;
      delete root.dataset.demoNewSession;
      const title = root.querySelector('.codex-thread-title');
      if (title) title.textContent = t('整理审查报告', "Prepare review report");
      syncSidebar();
    }

    root.addEventListener('click', event => {
      if (root.hidden || player.dataset.platform !== platform) return;
      const menu = event.target.closest('[data-demo-menu]');
      const button = event.target.closest('[data-demo-action]');
      const file = event.target.closest('[data-demo-file]');
      if (menu && root.contains(menu)) openMenu(menu);
      else if (button && root.contains(button) && !button.disabled) act(button.dataset.demoAction, button.dataset.demoValue, button);
      else if (file && root.contains(file)) command('open', {file: file.dataset.demoFile});
      else if (!popup.contains(event.target)) closePopup();
    });
    root.addEventListener('keydown', event => {
      if (popup.hidden || event.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); closePopup(true); return; }
      if (event.key === 'Tab') { closePopup(); return; }
      const buttons = [...popup.querySelectorAll('button')].filter(button => !button.disabled);
      const index = buttons.indexOf(document.activeElement);
      let next;
      if (event.key === 'ArrowDown') next = (index + 1) % buttons.length;
      if (event.key === 'ArrowUp') next = (index + buttons.length - 1) % buttons.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = buttons.length - 1;
      if (next !== undefined && buttons.length) { event.preventDefault(); buttons[next].focus(); }
    });
    root.addEventListener('showcase-demo:menu', event => {
      if (event.detail?.cyclePermission) {
        setPermission(permissions[(permissions.indexOf(permission) + 1) % permissions.length]);
        return;
      }
      const name = event.detail?.menu;
      const target = root.querySelector(`[data-demo-menu="${name}"]`) || root.querySelector('[data-demo-edit]');
      if (name) openMenu(target, name);
    });
    root.addEventListener('showcase-demo:reset', resetWindow);
    document.addEventListener('pointerdown', event => { if (!root.contains(event.target)) closePopup(); });
    window.addEventListener('resize', () => { syncSidebar(); if (anchor && !popup.hidden) positionPopup(anchor); });
    syncSidebar();
  });
})();
