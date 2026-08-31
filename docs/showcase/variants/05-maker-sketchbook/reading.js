// 阅读段只推进HTML；sticky负责固定外框，正文读完后由原生页面滚动自然释放。
(() => {
  'use strict';
  const track = document.querySelector('[data-reading-track]');
  const pin = track?.querySelector('[data-reading-pin]');
  const stage = track?.querySelector('[data-preview-stage]');
  if (!pin || !stage) return;

  const panes = [...stage.querySelectorAll('[data-preview-pane]')];
  const inset = 24;
  let pane = null;
  let contentHeight = 0;
  let start = 0;
  let range = 0;
  let pinned = false;
  let paint = null;

  const offset = () => Math.max(0, Math.min(range, window.scrollY - start));
  const reading = () => pinned && window.scrollY >= start && window.scrollY <= start + range;
  const movePage = top => window.scrollTo({top, left: window.scrollX, behavior: 'instant'});

  function render() {
    if (!pane) return;
    // 独立translate不覆盖分类切换的水平transform动画。
    pane.style.translate = pinned ? `0 ${-offset()}px` : '';
  }

  function layout() {
    if (!pane) return;
    const keepPosition = reading();
    const previousOffset = offset();
    const chromeHeight = stage.getBoundingClientRect().top - pin.getBoundingClientRect().top;
    const viewport = Math.floor(window.innerHeight - inset * 2 - chromeHeight - 2);
    // 极矮窗口中不强行固定，避免把导航或正文挤出可用区域。
    pinned = viewport >= 240;
    track.dataset.readingPinned = String(pinned);
    stage.style.height = (pinned ? viewport : contentHeight) + 'px';
    const pinHeight = Math.ceil(pin.getBoundingClientRect().height);
    if (pinned && pinHeight > window.innerHeight - inset * 2 + 1) {
      pinned = false;
      track.dataset.readingPinned = 'false';
      stage.style.height = contentHeight + 'px';
    }
    range = pinned ? Math.max(0, contentHeight - viewport) : 0;
    start = track.getBoundingClientRect().top + window.scrollY - inset;
    track.style.height = pinned ? pinHeight + range + 'px' : '';
    if (!pinned) panes.forEach(item => { item.style.translate = ''; });
    // 仅尺寸变化时保住当前阅读位置；普通滚动绝不拦截或改写scrollY。
    if (keepPosition && pinned) {
      const next = start + Math.min(previousOffset, range);
      if (Math.abs(next - window.scrollY) > 1) movePage(next);
    }
    render();
  }

  window.ShowcaseReading = {
    get pinned() { return pinned; },
    setContent(nextPane, height, restart = false) {
      // 新页就绪才复位；旧页保留原阅读位移，继续完成水平滑出。
      if (restart && reading()) movePage(start);
      pane = nextPane;
      contentHeight = height;
      layout();
    }
  };

  window.addEventListener('scroll', () => {
    if (paint === null) paint = requestAnimationFrame(() => { paint = null; render(); });
  }, {passive: true});
  window.addEventListener('resize', layout);
  window.addEventListener('load', layout);
  document.fonts?.ready.then(layout);
})();
