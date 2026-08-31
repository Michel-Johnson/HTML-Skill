// 05的轻量动效层：只呈现状态，不延迟或改变分类/播放器的业务逻辑。
(() => {
  'use strict';
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const animations = new Map();

  function cancel(node) {
    animations.get(node)?.cancel();
    animations.delete(node);
  }

  function animate(node, frames, duration) {
    cancel(node);
    if (reduced.matches || !node.animate) return;
    const animation = node.animate(frames, { duration, easing: 'cubic-bezier(.22,1,.36,1)' });
    animations.set(node, animation);
    animation.onfinish = () => {
      if (animations.get(node) === animation) animations.delete(node);
    };
  }

  // 工作台与预览短距离滑入，保持不透明；不缩放文字、不制造白色渐变闪屏。
  function enter(node) {
    if (node && !node.hidden) animate(node, [{ transform: 'translateX(24px)' }, { transform: 'translateX(0)' }], 180);
  }

  document.querySelectorAll('[data-motion-tabs]').forEach(group => {
    const indicator = group.querySelector('[data-motion-indicator]');
    const buttons = [...group.querySelectorAll('button[aria-pressed]')];
    if (!indicator || !buttons.length) return;
    let current = null;

    function move(smooth = true) {
      const selected = buttons.find(button => button.getAttribute('aria-pressed') === 'true');
      if (!selected || !selected.offsetWidth) return;
      const next = {
        transform: `translate(${selected.offsetLeft}px, ${selected.offsetTop}px)`,
        width: `${selected.offsetWidth}px`,
        height: `${selected.offsetHeight}px`
      };
      if (current && Object.keys(next).every(key => next[key] === current[key])) return;
      const previous = current && getComputedStyle(indicator);
      const from = previous && { transform: previous.transform, width: previous.width, height: previous.height };
      cancel(indicator);
      Object.assign(indicator.style, next);
      if (smooth && from) animate(indicator, [from, next], 220);
      current = next;
      group.dataset.motionReady = 'true';
    }

    new MutationObserver(() => move()).observe(group, {
      subtree: true, attributes: true, attributeFilter: ['aria-pressed']
    });
    const resize = new ResizeObserver(() => move(false));
    resize.observe(group);
    buttons.forEach(button => resize.observe(button));
    document.fonts?.ready.then(() => move(false));
    move(false);
  });

  reduced.addEventListener('change', () => {
    if (reduced.matches) [...animations.keys()].forEach(cancel);
  });
  window.ShowcaseMotion = Object.freeze({ enter });
})();
