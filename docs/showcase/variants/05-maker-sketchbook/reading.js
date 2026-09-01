// 阅读段使用离散整屏翻页；外页只负责进入或离开示例区，不再按scrollY连续推进正文。
(() => {
  'use strict';
  const track = document.querySelector('[data-reading-track]');
  const pin = track?.querySelector('[data-reading-pin]');
  const stage = track?.querySelector('[data-preview-stage]');
  const pager = track?.querySelector('[data-reading-pager]');
  const previous = pager?.querySelector('[data-reading-prev]');
  const next = pager?.querySelector('[data-reading-next]');
  const status = pager?.querySelector('[data-reading-status]');
  if (!pin || !stage || !previous || !next || !status) return;

  const panes = [...stage.querySelectorAll('[data-preview-pane]')];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const english = document.documentElement.lang.toLowerCase().startsWith('en');
  const inset = 24;
  const minimumPageHeight = 240;
  let pane = null;
  let contentHeight = 0;
  let page = 0;
  let pages = 1;
  let pageHeight = 0;
  let pageOffsets = [0];
  let semanticBreaks = [];
  let fitted = false;
  let initialized = false;
  let resizeFrame = null;
  let motionTimer = null;

  const pageLabel = () => english ? `Page ${page + 1} of ${pages}` : `第 ${page + 1} / ${pages} 页`;

  function updateControls() {
    previous.disabled = page === 0;
    next.disabled = page >= pages - 1;
    previous.setAttribute('aria-disabled', String(previous.disabled));
    next.setAttribute('aria-disabled', String(next.disabled));
    status.textContent = pageLabel();
  }

  function offsetFor(index) {
    return pageOffsets[index] ?? 0;
  }

  function render(animate = false) {
    if (!pane) return;
    clearTimeout(motionTimer);
    panes.forEach(item => item.removeAttribute('data-page-motion'));
    if (animate && !reduced.matches) {
      pane.setAttribute('data-page-motion', 'true');
      motionTimer = setTimeout(() => pane?.removeAttribute('data-page-motion'), 240);
    }
    pane.style.translate = `0 ${-offsetFor(page)}px`;
    updateControls();
  }

  function alignViewer() {
    const rect = pin.getBoundingClientRect();
    const availableBottom = window.innerHeight - inset;
    if (rect.top >= inset - 2 && rect.bottom <= availableBottom + 2) return;
    const top = window.scrollY + rect.top - inset;
    window.scrollTo({top, left: window.scrollX, behavior: reduced.matches ? 'auto' : 'smooth'});
  }

  function layout() {
    if (!pane || !contentHeight) return;
    const currentStageHeight = Math.max(1, stage.getBoundingClientRect().height);
    const fixedHeight = Math.max(0, pin.getBoundingClientRect().height - currentStageHeight);
    const available = Math.floor(window.innerHeight - inset * 2 - fixedHeight);
    fitted = available >= minimumPageHeight;
    pageHeight = fitted ? available : minimumPageHeight;
    stage.style.height = pageHeight + 'px';
    panes.forEach(item => { item.style.minHeight = Math.max(contentHeight, pageHeight) + 'px'; });
    const candidates = [...new Set(semanticBreaks
      .filter(value => value > 0 && value < contentHeight - 16)
      .map(value => Math.round(value)))].sort((a, b) => a - b);
    pageOffsets = [0];
    let current = 0;
    while (contentHeight - current > pageHeight + 1) {
      const minimum = current + pageHeight * .55;
      const target = current + pageHeight;
      const ceiling = current + pageHeight * 1.15;
      const before = candidates.filter(value => value >= minimum && value <= target).at(-1);
      const after = candidates.find(value => value > target && value <= ceiling);
      const offset = before ?? after ?? Math.min(target, contentHeight - 1);
      if (offset <= current + 1) break;
      pageOffsets.push(offset);
      current = offset;
    }
    pages = pageOffsets.length;
    page = Math.min(page, pages - 1);
    track.dataset.readingPaged = 'true';
    track.dataset.readingFitted = String(fitted);
    render(false);
  }

  function turn(delta) {
    const target = Math.max(0, Math.min(pages - 1, page + delta));
    if (target === page) return;
    page = target;
    alignViewer();
    render(true);
  }

  window.ShowcaseReading = {
    // preview.js沿用此能力判断，含义改为当前阅读区已适配视口。
    get pinned() { return fitted; },
    get page() { return page; },
    get pages() { return pages; },
    setContent(nextPane, height, restart = false, breaks = []) {
      const changed = pane !== nextPane;
      pane = nextPane;
      contentHeight = Math.max(1, Math.ceil(height));
      semanticBreaks = Array.isArray(breaks) ? breaks : [];
      if (restart || changed) page = 0;
      layout();
      if (restart || (!initialized && location.hash === '#examples')) requestAnimationFrame(alignViewer);
      initialized = true;
    }
  };

  previous.addEventListener('click', () => turn(-1));
  next.addEventListener('click', () => turn(1));
  pager.addEventListener('keydown', event => {
    if (event.key === 'PageUp') { event.preventDefault(); turn(-1); }
    else if (event.key === 'PageDown') { event.preventDefault(); turn(1); }
  });
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(layout);
  });
  window.addEventListener('load', layout);
  window.addEventListener('hashchange', () => { if (location.hash === '#examples') alignViewer(); });
  document.fonts?.ready.then(layout);
  reduced.addEventListener('change', () => render(false));
})();
