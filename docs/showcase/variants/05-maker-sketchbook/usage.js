(() => {
  'use strict';
  const {text: t, exampleUrl} = window.ShowcaseLocale;

  const player = document.querySelector('[data-usage-player]');
  if (!player) return;

  const element = (name) => player.querySelector(`[data-usage-${name}]`);
  const platforms = [...player.querySelectorAll('[data-usage-platform]')];
  const chapters = [...player.querySelectorAll('[data-usage-step]')];
  const ui = Object.fromEntries(['stage', 'result', 'frame', 'back', 'toggle', 'replay', 'progress', 'status'].map((name) => [name, element(name)]));
  const scrollbarProbe = element('scrollbar-probe');
  function fitPreviewScrollbars() {
    // 首屏与调用结果共用实测槽宽；首屏在88%缩放前补偿，避免漏改独立预览。
    const width = scrollbarProbe.offsetWidth - scrollbarProbe.clientWidth;
    document.documentElement.style.setProperty('--preview-scrollbar-width', `${Math.max(0, width)}px`);
  }
  fitPreviewScrollbars();
  window.addEventListener('resize', fitPreviewScrollbars);
  const fields = ['draft', 'placeholder', 'caret', 'sent', 'sent-text', 'working', 'work-label', 'answer', 'open', 'send', 'stop', 'scroll'];
  const views = new Map([...player.querySelectorAll('[data-workbench]')].map((root) => [
    root.dataset.workbench,
    {
      root,
      ...Object.fromEntries(fields.map((name) => [name, root.querySelector(`[data-flow-${name}]`)])),
      dock: root.querySelector('[data-result-dock]'),
      hideOnResult: [...root.querySelectorAll('[data-flow-hide-on-result]')],
      pointer: root.querySelector('[data-flow-pointer]'),
      sendPointer: root.querySelector('[data-flow-send-pointer]'),
      input: root.querySelector('[data-demo-input]'),
      editor: root.querySelector('[data-demo-editor]'),
      animatedInput: root.querySelector('[data-demo-edit]'),
      boundToken: root.querySelector('[data-demo-bound-token]'),
      manual: { draft: null, sent: null, editing: false, selected: false },
      skill: root.querySelector('[data-skill-picker]') ? Object.fromEntries(
        ['picker', 'choice', 'query', 'draft-token', 'request', 'sent-request'].map((name) => [name, root.querySelector(`[data-skill-${name}]`)])
      ) : null
    }
  ]));
  const modes = {
    app: {
      title: 'Codex App', token: '$html-reply', placeholder: t('随心输入', "Ask anything"), followup: t('随心输入', "Ask anything")
    },
    cli: {
      title: t('Codex 终端', "Codex CLI"), token: '$html-reply', terminal: true, placeholder: 'Ask Codex to do anything', followup: 'Ask Codex to do anything'
    },
    cursor: {
      title: 'Cursor App', token: '/html-reply', placeholder: 'Plan, Build, / for skills, @ for context', followup: 'Plan, Build, / for skills, @ for context'
    },
    claude: {
      title: 'Claude Code CLI', token: '/html-reply', terminal: true, placeholder: 'Try "explain this codebase"', followup: 'Try "what should I do next?"'
    }
  };
  const request = t(' 把这份审查结果整理成 HTML，先给结论，再列修改建议。', " Turn this review into HTML. Start with the conclusion, then list the suggested changes.");
  function writeText(node, text, terminal = false) {
    if (node.textContent === text) return;
    if (!terminal) { node.textContent = text; return; }
    node.replaceChildren(...(text.match(/[\u2e80-\u9fff\uf900-\ufaff\uff01-\uff60]+|[^\u2e80-\u9fff\uf900-\ufaff\uff01-\uff60]+/gu) || []).map(part => {
      const span = document.createElement('span');
      if (/^[\u2e80-\u9fff\uf900-\ufaff\uff01-\uff60]/u.test(part)) span.setAttribute('class', 'terminal-cjk');
      span.textContent = part;
      return span;
    }));
  }
  player.querySelectorAll('[data-terminal-copy]').forEach(node => {
    const text = node.textContent;
    node.textContent = '';
    writeText(node, text, true);
  });
  // 所有工作台走完同一条时间轴；外观和控件位置由独立DOM负责。
  const time = { typing: 200, token: 750, request: 850, typed: 2300, send: 2600, working: 3000, formatting: 3700, generating: 4400, ready: 5200, open: 6800, result: 7500, end: 11000 };
  // 候选选择占用原有输入阶段；不延长完整演示，不影响Cursor手动输入。
  const skillTime = { query: 200, filtered: 600, choosing: 1100, selected: 1350, request: 1400 };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let mode = player.dataset.platform in modes ? player.dataset.platform : 'cursor';
  let elapsed = 0;
  let intentToPlay = !reducedMotion.matches;
  let inView = false;
  let frameId = null;
  let previousTime = null;
  let lastPhase = '';
  let lastStage = -1;
  const cursor = views.get('cursor');
  const cursorInput = cursor.root.querySelector('[data-cursor-prompt]');
  const cursorAnimatedInput = cursor.root.querySelector('[data-cursor-animated-input]');
  const cursorSend = cursor.root.querySelector('[data-cursor-send]');
  const cursorResume = cursor.root.querySelector('[data-flow-resume]');
  const cliSeconds = views.get('cli').root.querySelector('[data-cli-seconds]');
  const claude = views.get('claude');
  const claudeTool = claude.root.querySelector('[data-claude-tool]');
  const claudeToolName = claude.root.querySelector('[data-claude-tool-name]');
  const claudeToolDetail = claude.root.querySelector('[data-claude-tool-detail]');
  const claudeSeconds = claude.root.querySelector('[data-claude-seconds]');
  let skillDismissed = false;
  let cursorDraft = null;
  let cursorSent = null;
  let editingCursor = false;
  let resultSource = ui.frame.dataset.src;
  let resultHistory = [resultSource];
  let resultIndex = 0;
  const resultTitles = {'review.html': t('审查报告', "Review report"), 'compare.html': t('方案对比', "Option comparison"), 'explain.html': t('理解缓存', "Understanding caching"), 'form.html': t('学习计划', "Learning plan"), 'history.html': t('回复历史总览', "Reply history")};
  let requestedSource = '';
  let readySource = '';
  let resultRequest = '';
  let resultSequence = 0;
  let resultTimeout = null;
  let resultMeasureRetry = null;
  let resultMeasureAttempts = 0;
  let resultFailed = false;
  let focusResultWhenReady = false;
  const setData = (node, key, value) => { if (node.dataset[key] !== String(value)) node.dataset[key] = String(value); };

  function syncResultNavigation() {
    element('forward').disabled = resultIndex >= resultHistory.length - 1;
    element('forward').setAttribute('aria-label', element('forward').disabled ? t('没有可前进的页面', "No page to go forward to") : t('前进到下一页', "Go to the next page"));
    ui.back.setAttribute('aria-label', resultIndex > 0 ? t('返回上一份 HTML', "Back to the previous HTML page") : t('返回演示对话', "Back to the demo conversation"));
  }

  function loadResult(force = false) {
    const title = resultTitles[resultSource.split('/').pop()];
    ui.frame.title = t('HTML Reply：', "HTML Reply: ") + title + t('（公开虚构示例）', " (fictional public example)");
    element('result-title').textContent = title + '.html';
    ui.result.querySelector('.usage-result-address').textContent = title + '.html';
    const link = ui.result.querySelector('.usage-result-toolbar a');
    link.setAttribute('href', resultSource);
    link.setAttribute('aria-label', t('在独立页面打开', "Open in a new tab: ") + title);
    syncResultNavigation();
    element('fallback').setAttribute('href', resultSource);
    if (!force && requestedSource === resultSource && ui.frame.getAttribute('src') === resultSource) return;
    clearTimeout(resultTimeout);
    clearTimeout(resultMeasureRetry);
    requestedSource = resultSource;
    readySource = resultRequest = '';
    resultMeasureAttempts = 0;
    resultFailed = false;
    ui.result.setAttribute('aria-busy', 'true');
    ui.frame.src = resultSource;
    resultTimeout = setTimeout(() => {
      if (readySource === requestedSource) return;
      clearTimeout(resultMeasureRetry);
      resultFailed = true;
      render(); syncPlayback();
    }, 10000);
  }

  function measureResult() {
    if (!requestedSource || readySource === requestedSource || ui.frame.getAttribute('src') !== requestedSource) return;
    if (!resultRequest) resultRequest = 'usage-result-' + (++resultSequence);
    ui.frame.contentWindow?.postMessage({type: 'html-reply-preview:measure', requestId: resultRequest}, '*');
    clearTimeout(resultMeasureRetry);
    if (++resultMeasureAttempts < 5) resultMeasureRetry = setTimeout(measureResult, 200);
  }
  ui.frame.addEventListener('load', measureResult);
  window.addEventListener('message', event => {
    const data = event.data;
    if (event.source !== ui.frame.contentWindow || !resultRequest || data?.type !== 'html-reply-preview:size' || data.requestId !== resultRequest) return;
    if (data.file !== requestedSource.split('/').pop() || !Number.isFinite(data.height) || data.height <= 0 || data.height > 32000) return;
    if (!Number.isFinite(data.width) || data.width <= 0 || Math.abs(data.width - ui.frame.clientWidth) > 2) return;
    if (readySource === requestedSource) return;
    readySource = requestedSource;
    resultFailed = false;
    clearTimeout(resultTimeout);
    clearTimeout(resultMeasureRetry);
    ui.result.setAttribute('aria-busy', 'false');
    render(); syncPlayback();
    if (focusResultWhenReady && !ui.result.hidden) { focusResultWhenReady = false; ui.back.focus(); }
  });
  window.addEventListener('resize', measureResult);
  element('retry').addEventListener('click', () => { loadResult(true); render(); });

  function resetResultNavigation() {
    resultSource = ui.frame.dataset.src;
    resultHistory = [resultSource];
    resultIndex = 0;
    focusResultWhenReady = false;
    syncResultNavigation();
  }

  function openResult(file = 'review.html', focus = false) {
    if (!Object.hasOwn(resultTitles, file)) return;
    const source = exampleUrl(file);
    if (source !== resultSource) {
      resultHistory = resultHistory.slice(0, resultIndex + 1);
      resultHistory.push(source);
      resultIndex = resultHistory.length - 1;
    }
    resultSource = source;
    focusResultWhenReady = focus;
    seek(time.result);
    if (focus && !ui.result.hidden) { focusResultWhenReady = false; ui.back.focus(); }
  }

  const clamp = (value) => Math.max(0, Math.min(1, value));
  const progressAt = (start, end) => clamp((elapsed - start) / (end - start));
  const prefixAt = (text, start, end) => text.slice(0, Math.floor(text.length * progressAt(start, end)));
  const shouldRun = () => intentToPlay && inView && !document.hidden && elapsed < time.end;
  const workLabel = () => elapsed < time.formatting ? t('正在读取 html-reply…', "Reading html-reply…") : elapsed < time.generating ? t('正在整理审查报告…', "Preparing the review report…") : t('正在生成 HTML…', "Generating HTML…");

  function positionPointer(pointer, visible, progress) {
    pointer.style.opacity = visible ? '1' : '0';
    pointer.style.transform = `translate(${Math.round(28 * (1 - progress))}px, ${Math.round(30 * (1 - progress))}px)`;
  }

  function render() {
    const view = views.get(mode);
    const config = modes[mode];
    const sent = elapsed >= time.working;
    const ready = elapsed >= time.ready;
    // 生成完成后预热；首次打开等正确文档就绪，保留对话直到交接。
    if (ready && (requestedSource !== resultSource || ui.frame.getAttribute('src') !== resultSource)) loadResult();
    const resultRequested = elapsed >= time.result;
    const result = resultRequested && (readySource === resultSource || !ui.result.hidden);
    setData(view.root, 'resultPreloading', ready && !result);
    const phase = result ? 'result' : elapsed >= time.open ? 'open' : ready ? 'ready' : sent ? 'working' : elapsed >= time.send ? 'send' : 'input';
    const stage = result ? 3 : sent ? 2 : elapsed >= time.send ? 1 : 0;
    const fullInput = reducedMotion.matches || elapsed >= time.send;
    const manual = view.manual;
    const manualInput = view.input && manual.draft !== null;
    const skillSelected = manualInput ? manual.selected : fullInput || elapsed >= skillTime.selected;
    const skillQuery = manualInput ? manual.draft : prefixAt(config.token.slice(0, 5), skillTime.query, skillTime.filtered);
    const skillRequest = manualInput ? manual.draft.slice(config.token.length) : fullInput ? request : prefixAt(request, skillTime.request, time.typed);
    let draft;
    if (view.skill) draft = manualInput ? manual.draft : skillSelected ? config.token + skillRequest : skillQuery;
    else if (cursorDraft !== null) draft = cursorDraft;
    else draft = fullInput ? config.token + request : prefixAt(config.token, time.typing, time.token) + prefixAt(request, time.request, time.typed);

    setData(player, 'phase', phase);
    setData(player, 'sent', sent);
    if (view.skill) {
      const skill = view.skill;
      const label = skill['draft-token'].querySelector('[data-skill-label]') || skill['draft-token'];
      const showPicker = !sent && !skillSelected && !skillDismissed && skillQuery.length > 0 && config.token.startsWith(skillQuery);
      view.root.dataset.skillPhase = showPicker ? !manualInput && elapsed >= skillTime.choosing ? 'choosing' : 'picker' : !sent && draft.length ? skillSelected ? 'selected' : 'draft' : 'idle';
      skill.picker.hidden = !showPicker;
      skill.query.textContent = sent || skillSelected ? '' : skillQuery;
      skill['draft-token'].hidden = sent || !skillSelected;
      label.textContent = sent || !skillSelected ? '' : mode === 'app' ? 'HTML Reply' : config.token;
      writeText(skill.request, sent || !skillSelected ? '' : skillRequest, config.terminal);
      const sentText = manual.sent ?? config.token + request;
      const hasSkill = sentText.startsWith(config.token);
      view.root.querySelector('[data-skill-sent-token]').hidden = !hasSkill;
      writeText(skill['sent-request'], hasSkill ? sentText.slice(config.token.length) : sentText, config.terminal);
    } else {
      view.draft.textContent = sent ? '' : draft;
    }
    writeText(view.placeholder, sent ? config.followup : config.placeholder);
    view.placeholder.hidden = !sent && draft.length > 0;
    view.caret.hidden = sent || draft.length === 0 || phase !== 'input';
    view.sent.hidden = !sent;
    if (!view.skill) view['sent-text'].textContent = mode === 'cursor' && cursorSent !== null ? cursorSent : config.token + request;
    view.working.hidden = !sent || ready;
    writeText(view['work-label'], mode === 'cli' ? 'Working' : workLabel());
    view.answer.hidden = !ready;
    view.send.hidden = sent && !ready;
    view.stop.hidden = !sent || ready;
    if (view.input) {
      view.editor.hidden = !manual.editing;
      view.animatedInput.hidden = manual.editing;
      if (view.boundToken) view.boundToken.hidden = !manual.selected;
      const inputValue = mode === 'app' && manual.selected ? (manual.draft ?? '').slice(config.token.length).trimStart() : manual.draft ?? '';
      if (manual.editing && view.input.value !== inputValue) { view.input.value = inputValue; sizeInput(view.input); }
      view.root.querySelectorAll('[data-demo-action="back"]').forEach(button => { button.disabled = !result; });
      view.root.querySelectorAll('[data-demo-action="forward"]').forEach(button => { button.disabled = !result || resultIndex >= resultHistory.length - 1; });
    }
    if (mode === 'cli') cliSeconds.textContent = String(Math.floor(Math.max(0, elapsed - time.working) / 1000));
    if (mode === 'claude') {
      claudeSeconds.textContent = String(Math.floor(Math.max(0, elapsed - time.working) / 1000));
      claudeTool.hidden = !sent;
      claudeToolName.textContent = elapsed < time.generating ? 'Skill(html-reply)' : 'HTML reply';
      claudeToolDetail.textContent = ready ? '⎿ Ready to open' : elapsed < time.formatting ? '⎿ Loading skill…' : elapsed < time.generating ? '⎿ Formatting review…' : '⎿ Preparing HTML…';
      view['work-label'].textContent = elapsed < time.formatting ? 'Working…' : elapsed < time.generating ? 'Composing…' : 'Writing…';
    }
    if (mode === 'cursor') {
      view.scroll.hidden = !sent;
      cursorAnimatedInput.hidden = editingCursor;
      cursorInput.hidden = !editingCursor;
      if (editingCursor && cursorInput.value !== cursorDraft) cursorInput.value = cursorDraft;
    }

    view.hideOnResult.forEach((node) => { node.hidden = result; });
    view.dock.hidden = !result;
    ui.result.hidden = !result;
    ui.result.inert = !result;
    if (result && lastPhase !== 'result') window.ShowcaseMotion?.enter(ui.result);
    element('load-feedback').hidden = !resultFailed;
    element('load-message').textContent = t('示例暂未加载，可重试或单独打开。', "The example has not loaded. Retry or open it in a new tab.");
    element('retry').hidden = !resultFailed;
    positionPointer(view.pointer, phase === 'open', progressAt(time.open, time.result - 250));
    positionPointer(view.sendPointer, phase === 'send', progressAt(time.send, time.working - 150));
    if (phase !== lastPhase && sent) view.scroll.scrollTop = view.scroll.scrollHeight;
    ui.progress.style.width = `${Math.min(100, elapsed / time.end * 100)}%`;

    if (stage !== lastStage) {
      chapters.forEach((button, index) => {
        if (index === stage) button.setAttribute('aria-current', 'step');
        else button.removeAttribute('aria-current');
      });
      ui.status.textContent = [
        t(`流程演示：在 ${config.title} 输入 ${config.token} 和请求。`, `Workflow demo: type ${config.token} and your request in ${config.title}.`),
        t('流程演示：发送请求，不会实际执行命令或请求模型。', "Workflow demo: sending a request. No real commands run and no model is called."),
        t('流程演示：整理内容并生成HTML；随后点击当前回复。', "Workflow demo: organizing the content and generating HTML, then opening the current reply."),
        t('已打开实际生成的公开HTML示例，可以滚动阅读或单独打开。', "A public HTML example is open. Scroll to read it, or open it in a new tab.")
      ][stage];
      lastStage = stage;
    }
    lastPhase = phase;
  }

  function syncPlayback() {
    const running = shouldRun();
    const ended = elapsed >= time.end;
    setData(player, 'running', running);
    ui.toggle.textContent = ended ? t('重播', "Replay") : intentToPlay ? t('暂停', "Pause") : t('播放', "Play");
    ui.toggle.setAttribute('aria-label', ended ? t('从头重播完整调用演示', "Replay the complete workflow from the start") : intentToPlay ? t('暂停调用演示', "Pause the workflow demo") : t('播放调用演示', "Play the workflow demo"));
    ui.replay.hidden = ended;
    if (mode !== 'cursor') {
      const view = views.get(mode);
      const working = elapsed >= time.working && elapsed < time.ready;
      const send = view.root.querySelector('[data-demo-action="send"]');
      if (send) {
        send.setAttribute('aria-label', working ? intentToPlay ? t('暂停生成演示', "Pause generation demo") : t('继续生成演示', "Resume generation demo") : t('发送演示请求', "Send demo request"));
        send.title = send.getAttribute('aria-label');
      }
      if (working && !intentToPlay) view['work-label'].textContent = modes[mode].terminal ? 'Paused' : t('已暂停', "Paused");
    }
    if (mode === 'cursor') {
      const working = elapsed >= time.working && elapsed < time.ready;
      cursorResume.hidden = !working || intentToPlay;
      cursorSend.setAttribute('aria-label', working ? intentToPlay ? t('暂停生成演示', "Pause generation demo") : t('继续生成演示', "Resume generation demo") : t('发送演示请求', "Send demo request"));
      cursorSend.title = cursorSend.getAttribute('aria-label');
      cursor.stop.textContent = intentToPlay ? '■' : '▶';
      if (working && !intentToPlay) cursor['work-label'].textContent = t('已暂停', "Paused");
      else if (working) cursor['work-label'].textContent = workLabel();
      const playButton = cursor.root.querySelector('[data-cursor-play]');
      playButton.setAttribute('aria-label', running ? t('暂停演示', "Pause demo") : t('播放演示', "Play demo"));
      playButton.title = running ? t('暂停演示', "Pause demo") : t('播放演示', "Play demo");
    }
    if (running && frameId === null) frameId = requestAnimationFrame(tick);
    if (!running && frameId !== null) {
      cancelAnimationFrame(frameId);
      frameId = null;
    }
    if (!running) previousTime = null;
  }

  function tick(now) {
    frameId = null;
    if (!shouldRun()) { syncPlayback(); return; }
    if (previousTime !== null) elapsed = Math.min(time.end, elapsed + now - previousTime);
    previousTime = now;
    if (elapsed >= time.end) intentToPlay = false;
    render();
    syncPlayback();
  }

  function seek(position, play = false) {
    elapsed = Math.max(0, Math.min(position, time.end));
    if (elapsed < time.result) focusResultWhenReady = false;
    previousTime = null;
    intentToPlay = play;
    render();
    syncPlayback();
  }

  function selectPlatform(value) {
    if (!views.has(value) || !(value in modes)) return;
    if (value === mode && lastPhase) return;
    mode = value;
    player.dataset.platform = mode;
    views.forEach((view, key) => {
      view.root.hidden = key !== mode;
      view.dock.hidden = true;
      setData(view.root, 'resultPreloading', false);
    });
    // 四个平台共享一个真实文档，避免重复iframe及互相污染的历史状态。
    views.get(mode).dock.append(ui.result);
    ui.frame.removeAttribute('src');
    clearTimeout(resultTimeout);
    clearTimeout(resultMeasureRetry);
    requestedSource = readySource = resultRequest = '';
    resultMeasureAttempts = 0;
    resultFailed = false;
    focusResultWhenReady = false;
    platforms.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.usagePlatform === mode)));
    cursorDraft = null;
    cursorSent = null;
    editingCursor = false;
    skillDismissed = false;
    views.forEach(view => {
      view.manual = { draft: null, sent: null, editing: false, selected: false };
      view.root.dispatchEvent(new CustomEvent('showcase-demo:reset'));
    });
    resetResultNavigation();
    closePreviewMenu();
    lastPhase = '';
    lastStage = -1;
    seek(reducedMotion.matches ? time.send - 1 : 0, !reducedMotion.matches);
    window.ShowcaseMotion?.enter(views.get(mode).root);
  }

  platforms.forEach((button, index) => {
    button.addEventListener('click', () => selectPlatform(button.dataset.usagePlatform));
    button.addEventListener('keydown', (event) => {
      let next;
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (index + 1) % platforms.length;
      if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (index + platforms.length - 1) % platforms.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = platforms.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      platforms[next].focus();
      platforms[next].click();
    });
  });
  views.forEach((view, key) => {
    if (!view.skill) return;
    const selectSkill = () => {
      if (mode !== key || view.skill.picker.hidden) return;
      // 选择只补全Skill，不发送；播放状态保持由用户控制。
      if (view.manual.editing) {
        view.manual.draft = modes[mode].token + ' ';
        view.manual.selected = true;
        render();
        view.input.focus();
        view.input.setSelectionRange(view.input.value.length, view.input.value.length);
        return;
      }
      seek(skillTime.selected, intentToPlay);
    };
    view.skill.choice.addEventListener('click', selectSkill);
    view.skill.choice.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !view.skill.picker.hidden) {
        event.preventDefault();
        skillDismissed = true;
        seek(elapsed);
        return;
      }
      if (event.key !== 'Tab' || event.shiftKey || view.skill.picker.hidden) return;
      event.preventDefault();
      selectSkill();
    });
    view.animatedInput.addEventListener('click', () => editDemo(view));
    view.animatedInput.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); editDemo(view); }
    });
    view.input.addEventListener('input', () => {
      view.manual.draft = key === 'app' && view.manual.selected ? modes[key].token + ' ' + view.input.value : view.input.value;
      view.manual.selected = view.manual.draft.startsWith(modes[key].token + ' ');
      skillDismissed = false;
      render();
      sizeInput(view.input);
    });
    view.input.addEventListener('keydown', event => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Tab' && !event.shiftKey && !view.skill.picker.hidden) {
        event.preventDefault(); selectSkill();
      } else if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!view.skill.picker.hidden) selectSkill();
        else sendDemo(view);
      } else if (event.key === 'Backspace' && mode === 'app' && view.manual.selected && view.input.selectionStart === 0 && view.input.selectionEnd === 0) {
        event.preventDefault();
        view.manual.selected = false;
        view.manual.draft = view.input.value;
        render();
      } else if (event.key === 'Tab' && event.shiftKey && mode === 'claude') {
        event.preventDefault();
        view.root.dispatchEvent(new CustomEvent('showcase-demo:menu', {detail: {cyclePermission: true}}));
      } else if (event.key === '?' && modes[key].terminal && !view.input.value) {
        event.preventDefault();
        view.root.dispatchEvent(new CustomEvent('showcase-demo:menu', {detail: {menu: 'shortcuts'}}));
      }
    });
    view.root.addEventListener('keydown', event => {
      if (event.defaultPrevented || event.isComposing || mode !== key || event.key !== 'Escape') return;
      if (view.root.querySelector('[data-demo-popup]')?.hidden === false) return;
      if (!view.skill.picker.hidden) { skillDismissed = true; intentToPlay = false; render(); syncPlayback(); }
      else if (view.manual.editing) { view.manual.editing = false; render(); view.animatedInput.focus(); }
      else if (elapsed >= time.working && elapsed < time.ready) { intentToPlay = false; syncPlayback(); }
      else return;
      event.preventDefault();
    });
  });
  const chapterTimes = [time.send - 1, time.send + 250, time.ready + 500, time.result];
  chapters.forEach((button, index) => button.addEventListener('click', () => {
    editingCursor = false;
    seek(chapterTimes[index]);
  }));
  function replay() {
    cursorDraft = null;
    cursorSent = null;
    editingCursor = false;
    skillDismissed = false;
    views.forEach(view => {
      view.manual = { draft: null, sent: null, editing: false, selected: false };
      view.root.dispatchEvent(new CustomEvent('showcase-demo:reset'));
    });
    resetResultNavigation();
    closePreviewMenu();
    cursor.root.dispatchEvent(new CustomEvent('cursor-demo:reset'));
    seek(0, true);
  }
  function playOrPause(forcePlay = false) {
    const view = views.get(mode);
    if (view.input && view.manual.editing) { sendDemo(view); return; }
    if (elapsed >= time.end || (mode === 'cursor' && cursorDraft === '' && (forcePlay || !intentToPlay))) { replay(); return; }
    if (mode === 'cursor' && editingCursor) {
      cursorSent = cursorDraft?.trim() || null;
      editingCursor = false;
    }
    intentToPlay = forcePlay || !intentToPlay;
    render();
    syncPlayback();
  }
  ui.toggle.addEventListener('click', () => {
    playOrPause();
  });
  ui.replay.addEventListener('click', replay);
  views.forEach((view) => view.open.addEventListener('click', () => {
    resetResultNavigation();
    openResult('review.html', true);
  }));
  ui.back.addEventListener('click', () => {
    if (ui.result.hidden) return;
    closePreviewMenu();
    if (resultIndex > 0) {
      resultSource = resultHistory[--resultIndex];
      seek(time.result);
    } else {
      seek(time.ready);
      views.get(mode).open.focus();
    }
  });
  element('forward').addEventListener('click', () => {
    if (ui.result.hidden || resultIndex >= resultHistory.length - 1) return;
    resultSource = resultHistory[++resultIndex];
    seek(time.result);
  });
  const previewMenu = element('file-menu');
  const previewMenuButton = element('preview-menu');
  function closePreviewMenu() {
    previewMenu.hidden = true;
    previewMenuButton.setAttribute('aria-expanded', 'false');
  }
  element('close').addEventListener('click', () => {
    closePreviewMenu();
    seek(time.ready);
    views.get(mode).open.focus();
  });
  previewMenuButton.addEventListener('click', () => {
    previewMenu.hidden = !previewMenu.hidden;
    previewMenuButton.setAttribute('aria-expanded', String(!previewMenu.hidden));
    if (!previewMenu.hidden) previewMenu.querySelector('button').focus();
  });
  previewMenu.querySelectorAll('[data-usage-file]').forEach(button => button.addEventListener('click', () => {
    const file = button.dataset.usageFile;
    if (ui.result.hidden || !Object.hasOwn(resultTitles, file)) return;
    closePreviewMenu();
    openResult(file);
    previewMenuButton.focus();
  }));
  ui.result.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !previewMenu.hidden) {
      event.preventDefault();
      closePreviewMenu();
      previewMenuButton.focus();
    }
  });
  element('refresh')?.addEventListener('click', () => {
    // 只重新加载当前公开示例，不重播调用动画、不操作原生浏览器。
    if (mode === 'app' && !ui.result.hidden) { loadResult(true); render(); }
  });
  const pauseForInteraction = () => { intentToPlay = false; syncPlayback(); };
  // 菜单、文件和面板操作不能偷偷暂停时间轴；只暂停明确的控制和结果阅读。
  ui.frame.addEventListener('focus', pauseForInteraction);
  ui.frame.addEventListener('showcase-preview:navigate', event => {
    event.preventDefault();
    const file = event.detail?.file;
    if (ui.result.hidden || ui.result.getAttribute('aria-busy') === 'true' || !Object.hasOwn(resultTitles, file)) return;
    openResult(file);
    pauseForInteraction();
  });
  cursorInput.addEventListener('input', () => { cursorDraft = cursorInput.value; });
  cursorInput.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendCursor();
    }
  });
  cursorResume.addEventListener('click', () => { intentToPlay = true; syncPlayback(); });

  function editCursor() {
    cursorDraft = elapsed >= time.working ? '' : cursorDraft ?? (cursor.draft.textContent || modes.cursor.token + request);
    editingCursor = true;
    seek(Math.min(elapsed, time.send - 1));
    cursorInput.focus();
  }

  function sendCursor() {
    if (elapsed >= time.working && elapsed < time.ready) {
      intentToPlay = !intentToPlay;
      syncPlayback();
      return;
    }
    const text = (cursorDraft ?? modes.cursor.token + request).trim();
    if (!text) { editCursor(); return; }
    cursorSent = text;
    editingCursor = false;
    resetResultNavigation();
    seek(time.working, true);
  }

  function editDemo(view, empty = false) {
    if (!view.input) return;
    const text = empty || elapsed >= time.working ? '' : view.manual.draft ?? view.draft.textContent;
    view.manual.draft = text;
    view.manual.selected = text.startsWith(modes[mode].token + ' ');
    view.manual.editing = true;
    skillDismissed = false;
    seek(Math.min(elapsed, time.send - 1));
    view.input.focus();
  }

  function sizeInput(input) {
    input.style.height = 'auto';
    input.style.height = Math.min(120, input.scrollHeight) + 'px';
  }

  function sendDemo(view) {
    if (elapsed >= time.working && elapsed < time.ready) { intentToPlay = !intentToPlay; render(); syncPlayback(); return; }
    const text = (view.manual.draft ?? modes[mode].token + request).trim();
    if (!text) { editDemo(view, true); return; }
    if (text === '/model' || text === '?' || text === '/help') {
      view.root.dispatchEvent(new CustomEvent('showcase-demo:menu', {detail: {menu: text === '/model' ? 'model' : 'shortcuts'}}));
      return;
    }
    view.manual.sent = text;
    view.manual.editing = false;
    resetResultNavigation();
    seek(time.working, true);
  }

  views.forEach((view, key) => {
    if (!view.input) return;
    view.root.addEventListener('showcase-demo:command', event => {
      if (mode !== key) return;
      const {action, file} = event.detail || {};
      if (action === 'edit') editDemo(view);
      else if (action === 'use-skill') {
        view.manual.draft = modes[key].token + ' ';
        view.manual.selected = view.manual.editing = true;
        skillDismissed = false;
        seek(time.send - 1);
        view.input.focus();
      }
      else if (action === 'new-session') { view.manual.sent = null; resetResultNavigation(); seek(0); editDemo(view, true); }
      else if (action === 'send') sendDemo(view);
      else if (action === 'pause') pauseForInteraction();
      else if (action === 'play') playOrPause(true);
      else if (action === 'replay') replay();
      else if (action === 'open') { view.manual.editing = false; openResult(file); }
      else if (action === 'back') ui.back.click();
      else if (action === 'forward') element('forward').click();
      else if (action === 'conversation') { view.manual.editing = false; seek(time.ready); }
      else if (action === 'preview') { if (ui.result.hidden) view.open.click(); else element('close').click(); }
    });
  });

  // 仅开放演示动作，不执行命令、不把输入发给模型。
  cursor.root.addEventListener('cursor-demo:command', event => {
    if (mode !== 'cursor') return;
    const action = event.detail?.action;
    if (action === 'send') sendCursor();
    else if (action === 'edit') editCursor();
    else if (action === 'new-agent') {
      cursorDraft = '';
      cursorSent = null;
      editingCursor = true;
      resetResultNavigation();
      seek(0);
      cursorInput.focus();
    } else if (action === 'play' || action === 'resume') playOrPause(action === 'resume');
    else if (action === 'pause') pauseForInteraction();
    else if (action === 'replay') replay();
    else if (action === 'ready') { editingCursor = false; seek(time.ready); }
    else if (action === 'back') seek(time.ready);
    else if (action === 'open') {
      editingCursor = false;
      openResult(event.detail.file === 'history' ? 'history.html' : 'review.html', true);
    }
  });
  document.addEventListener('visibilitychange', syncPlayback);
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) seek(elapsed < time.send ? time.send - 1 : elapsed);
  });

  selectPlatform(mode);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      syncPlayback();
    }, { threshold: 0 }).observe(ui.stage);
  } else {
    inView = true;
    syncPlayback();
  }
})();
