// 05双缓冲：新页在后台完成加载和测量后才接替旧页，不读取跨源DOM。
(() => {
  'use strict';
  const {text: t, exampleUrl} = window.ShowcaseLocale;
  const viewer = document.querySelector('[data-reading-viewer]');
  if (!viewer) return;
  const stage = viewer.querySelector('[data-preview-stage]');
  const reading = window.ShowcaseReading;
  const error = viewer.querySelector('[data-preview-error]');
  const buttons = [...viewer.querySelectorAll('[data-example]')];
  const links = [...viewer.querySelectorAll('[data-example-link]')];
  const examples = new Map(buttons.map(button => [button.dataset.example, button.textContent.trim()]));
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const slots = [...stage.querySelectorAll('[data-preview-pane]')].map(pane => ({
    pane, frame: pane.querySelector('iframe'), note: pane.querySelector('[data-example-note]'),
    file: '', expected: null, ready: false, requestId: '', width: 0, breaks: []
  }));
  let active = slots[0];
  active.file = 'review';
  let desired = active.file;
  let pending = null;
  let transition = null;
  let sequence = 0;
  let timeout = null;
  let paintFrame = null;
  let lastWidth = 0;

  const urlFor = key => exampleUrl(key + '.html');
  const busy = value => stage.setAttribute('aria-busy', String(value));
  // 分页会给pane补足视口高度；实际文档高度只取提醒和iframe，避免短页继承上一页的min-height。
  const heightOf = slot => Math.ceil(slot.frame.getBoundingClientRect().height + (slot.note.hidden ? 0 : slot.note.getBoundingClientRect().height));
  const sizeStage = (slot, restart = false) => {
    const height = heightOf(slot);
    const noteHeight = slot.note.hidden ? 0 : slot.note.getBoundingClientRect().height;
    const breaks = slot.breaks.map(value => value + noteHeight);
    if (reading) reading.setContent(slot.pane, height, restart, breaks);
    else stage.style.height = height + 'px';
  };
  const selectButton = key => buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.example === key)));

  function prepare(slot, key) {
    slot.frame.title = t('HTML Reply 真实输出：', "HTML Reply output: ") + examples.get(key);
    slot.note.hidden = key !== 'form';
    slot.note.textContent = key === 'form' ? t('选择选项或离开输入框会下载 JSON，请只填写演示内容。', "Selecting an option or leaving a text field downloads JSON. Use demo content only.") : '';
  }

  function accessibility(slot, enabled) {
    slot.pane.inert = !enabled;
    slot.pane.setAttribute('aria-hidden', String(!enabled));
    slot.pane.style.pointerEvents = enabled ? 'auto' : 'none';
    slot.frame.tabIndex = enabled ? 0 : -1;
  }

  function clearWait() {
    clearTimeout(timeout);
    cancelAnimationFrame(paintFrame);
    timeout = null;
    paintFrame = null;
  }

  function measure(slot) {
    slot.requestId = String(++sequence);
    slot.frame.contentWindow?.postMessage({type: 'html-reply-preview:measure', requestId: slot.requestId}, '*');
  }

  function fail() {
    if (!pending) return;
    pending.ready = false;
    pending.requestId = '';
    pending = null;
    clearWait();
    desired = active.file;
    selectButton(desired);
    busy(false);
    error.hidden = false;
  }

  function finish() {
    if (!transition) return;
    const {from, to, incoming, outgoing, height} = transition;
    transition = null;
    from.pane.style.opacity = '0';
    from.pane.style.zIndex = '0';
    to.pane.style.opacity = '1';
    to.pane.style.zIndex = '1';
    [from, to].forEach(slot => {
      slot.pane.style.transform = '';
      slot.pane.style.minHeight = '';
      slot.pane.style.willChange = '';
    });
    active = to;
    active.expected = null;
    accessibility(from, false);
    accessibility(to, true);
    sizeStage(to);
    incoming?.cancel();
    outgoing?.cancel();
    height?.cancel();
    links.forEach(link => { link.href = urlFor(active.file); });
    if (desired !== active.file) loadDesired();
    else busy(false);
  }

  function handover(slot) {
    if (pending !== slot || slot.file !== desired || !slot.ready) return;
    clearWait();
    pending = null;
    const fromHeight = stage.getBoundingClientRect().height;
    const toHeight = heightOf(slot);
    const from = active;
    accessibility(from, false);
    accessibility(slot, false);
    // 两页始终不透明；按分类顺序一起滑动，避免交接时文字叠在一起。
    from.pane.style.opacity = '1';
    from.pane.style.zIndex = '1';
    slot.pane.style.opacity = '1';
    slot.pane.style.zIndex = '2';
    sizeStage(slot, true);
    transition = {from, to: slot};
    if (reduced.matches || !slot.pane.animate) { finish(); return; }
    const order = [...examples.keys()];
    const direction = order.indexOf(slot.file) > order.indexOf(from.file) ? 1 : -1;
    // 补齐较短页的背景，不拉伸iframe正文；结束时还原自然高度。
    [from, slot].forEach(item => {
      item.pane.style.minHeight = Math.max(fromHeight, toHeight) + 'px';
      item.pane.style.willChange = 'transform';
    });
    const options = {duration: 320, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both'};
    if (!reading?.pinned) transition.height = stage.animate([{height: fromHeight + 'px'}, {height: toHeight + 'px'}], options);
    transition.outgoing = from.pane.animate([{transform: 'translateX(0%)'}, {transform: `translateX(${-direction * 100}%)`}], options);
    transition.incoming = slot.pane.animate([{transform: `translateX(${direction * 100}%)`}, {transform: 'translateX(0%)'}], options);
    transition.incoming.onfinish = finish;
  }

  function afterPaint(slot) {
    cancelAnimationFrame(paintFrame);
    paintFrame = requestAnimationFrame(() => {
      paintFrame = requestAnimationFrame(() => {
        paintFrame = null;
        if (Math.abs(slot.width - slot.frame.clientWidth) <= 2) handover(slot);
      });
    });
  }

  function loadDesired() {
    clearWait();
    if (pending) pending.requestId = '';
    pending = null;
    error.hidden = true;
    if (desired === active.file) { busy(false); return; }
    const slot = slots.find(item => item !== active);
    pending = slot;
    slot.expected = desired;
    busy(true);
    if (slot.ready && slot.file === desired && Math.abs(slot.width - slot.frame.clientWidth) <= 2) {
      afterPaint(slot);
    } else {
      slot.ready = false;
      slot.requestId = '';
      prepare(slot, desired);
      // 只替换后台iframe；当前页的src、可见性和高度保持原样。
      slot.frame.src = urlFor(desired);
    }
    timeout = setTimeout(fail, 10000);
  }

  function select(key) {
    if (!examples.has(key)) return;
    if (key === desired && (pending || transition || key === active.file)) return;
    desired = key;
    selectButton(key);
    // 过渡中只记录最后一次点击，避免拆掉正在显示的两个图层。
    if (!transition) loadDesired();
    if (!reading?.pinned && viewer.getBoundingClientRect().top < -160) {
      viewer.scrollIntoView({block: 'start', behavior: reduced.matches ? 'instant' : 'smooth'});
    }
  }

  window.addEventListener('message', event => {
    const slot = slots.find(item => item.frame.contentWindow === event.source);
    const data = event.data;
    if (!slot || !slot.requestId || data?.type !== 'html-reply-preview:size' || data.requestId !== slot.requestId) return;
    if (!Number.isFinite(data.height) || data.height <= 0 || data.height > 32000) return;
    if (!Number.isFinite(data.width) || data.width <= 0 || Math.abs(data.width - slot.frame.clientWidth) > 2) return;
    const key = [...examples.keys()].find(value => value + '.html' === data.file);
    if (!key || (slot.expected && slot.expected !== key)) return;
    const navigated = slot.file !== key;
    slot.file = key;
    slot.width = data.width;
    slot.breaks = Array.isArray(data.breaks) ? [...new Set(data.breaks
      .filter(value => Number.isFinite(value) && value > 0 && value < data.height)
      .map(value => Math.round(value)))].sort((a, b) => a - b) : [];
    slot.frame.style.height = Math.ceil(data.height) + 2 + 'px';
    slot.ready = true;
    prepare(slot, key);
    if (slot === active && !transition) {
      sizeStage(slot, navigated);
      links.forEach(link => { link.href = urlFor(key); });
      // iframe内的历史导航同步分类，但不覆盖仍在等待的用户选择。
      if (!pending) { desired = key; selectButton(key); }
    }
    if (slot === pending && key === desired) afterPaint(slot);
  });

  slots.forEach(slot => {
    slot.frame.addEventListener('showcase-preview:navigate', event => {
      event.preventDefault();
      if (slot !== active || transition) return;
      const key = [...examples.keys()].find(value => value + '.html' === event.detail?.file);
      if (!key) return;
      if (key === active.file) {
        desired = key;
        selectButton(key);
        loadDesired();
        sizeStage(active, true);
      } else select(key);
    });
    slot.frame.addEventListener('load', () => {
      slot.ready = false;
      if (slot === active && !transition) slot.expected = null;
      measure(slot);
    });
    slot.frame.addEventListener('error', () => { if (slot === pending) fail(); });
    accessibility(slot, slot === active);
  });

  buttons.forEach((button, index) => {
    button.addEventListener('click', () => select(button.dataset.example));
    button.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowDown') next = (index + 1) % buttons.length;
      else if (event.key === 'ArrowUp') next = (index + buttons.length - 1) % buttons.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = buttons.length - 1;
      else return;
      event.preventDefault();
      buttons[next].focus();
      buttons[next].click();
    });
  });

  new ResizeObserver(([entry]) => {
    const width = Math.round(entry.contentRect.width);
    if (width === lastWidth) return;
    lastWidth = width;
    slots.forEach(slot => {
      if (!slot.frame.getAttribute('src')) return;
      slot.ready = false;
      measure(slot);
    });
  }).observe(stage);
  reduced.addEventListener('change', () => { if (reduced.matches) finish(); });
  // defer接管前首个iframe可能已加载；只请求尺寸，不重新加载或播放切换动画。
  measure(active);
  window.addEventListener('load', () => { if (!active.ready) measure(active); }, {once: true});
})();
