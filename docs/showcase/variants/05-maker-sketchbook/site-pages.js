// 整个宣传前端按章节翻页；嵌入HTML保留自己的阅读与交互。
(() => {
  'use strict';

  const track = document.querySelector('[data-site-pages]');
  const pages = track ? [...track.querySelectorAll(':scope > [data-site-page]')] : [];
  if (!track || !pages.length) return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const pageById = new Map(pages.map((page, index) => [page.id, index]));
  const pageLinks = [...document.querySelectorAll('a[href^="#"]')].filter(link => pageById.has(link.hash.slice(1)));
  let index = pageById.get(location.hash.slice(1)) ?? 0;
  let gestureLockedUntil = 0;
  let wheelTotal = 0;
  let wheelReset = 0;
  let touchStart = null;

  const clamp = value => Math.max(0, Math.min(pages.length - 1, value));
  const pageHash = page => `#${page.id}`;

  function syncLanguageLinks(hash) {
    document.querySelectorAll('[data-language-link]').forEach(link => {
      const base = link.getAttribute('href')?.split('#')[0];
      if (base) link.setAttribute('href', base + hash);
    });
  }

  function updateHistory(mode) {
    if (mode === 'none') return;
    const hash = pageHash(pages[index]);
    if (location.hash === hash) return;
    history[mode === 'replace' ? 'replaceState' : 'pushState'](null, '', hash);
    syncLanguageLinks(hash);
  }

  function updateNavigation() {
    const page = pages[index];
    pageLinks.forEach(link => {
      const current = link.hash === pageHash(page);
      if (current) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }

  function focusPage(page) {
    const heading = page.querySelector('h1,h2');
    if (!heading) return;
    heading.tabIndex = -1;
    heading.focus({preventScroll: true});
  }

  function showPage(nextIndex, options = {}) {
    const target = clamp(nextIndex);
    const changed = target !== index;
    index = target;
    track.style.setProperty('--site-page-index', String(index));
    track.style.setProperty('--site-page-offset', `${index * -100}%`);
    pages.forEach((page, pageIndex) => {
      const active = pageIndex === index;
      page.inert = !active;
      page.setAttribute('aria-hidden', String(!active));
      page.toggleAttribute('data-site-page-active', active);
    });
    updateNavigation();
    updateHistory(options.history || 'none');
    if (changed && options.focus) focusPage(pages[index]);
    if (changed) {
      gestureLockedUntil = performance.now() + (reduced.matches ? 160 : 540);
      window.dispatchEvent(new CustomEvent('showcase:site-page-change', {
        detail: {index, id: pages[index].id, label: pages[index].dataset.siteLabel || ''}
      }));
    }
  }

  function turn(delta, focus = true) {
    showPage(index + delta, {history: 'push', focus});
  }

  pageLinks.forEach(link => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    showPage(pageById.get(link.hash.slice(1)), {history: 'push', focus: true});
  }));

  // 不显示翻页按钮：滚轮/触控板和纵向触摸手势一次只推进一个完整场景。
  window.addEventListener('wheel', event => {
    if (event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
    const scale = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? innerHeight : 1;
    const delta = event.deltaY * scale;
    if (!delta) return;
    if (performance.now() < gestureLockedUntil) {
      event.preventDefault();
      return;
    }
    clearTimeout(wheelReset);
    wheelTotal += delta;
    wheelReset = setTimeout(() => { wheelTotal = 0; }, 150);
    if (Math.abs(wheelTotal) < 56) return;
    const direction = wheelTotal > 0 ? 1 : -1;
    wheelTotal = 0;
    if ((direction > 0 && index < pages.length - 1) || (direction < 0 && index > 0)) {
      event.preventDefault();
      turn(direction, false);
    }
  }, {passive: false});

  window.addEventListener('touchstart', event => {
    if (event.touches.length !== 1) { touchStart = null; return; }
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest('a,button,input,textarea,select,[contenteditable="true"],iframe')) { touchStart = null; return; }
    const touch = event.touches[0];
    touchStart = {x: touch.clientX, y: touch.clientY};
  }, {passive: true});
  window.addEventListener('touchend', event => {
    if (!touchStart || event.changedTouches.length !== 1 || performance.now() < gestureLockedUntil) { touchStart = null; return; }
    const touch = event.changedTouches[0];
    const dx = touch.clientX - touchStart.x;
    const dy = touch.clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(dy) < 54 || Math.abs(dy) < Math.abs(dx) * 1.2) return;
    const direction = dy < 0 ? 1 : -1;
    if ((direction > 0 && index < pages.length - 1) || (direction < 0 && index > 0)) turn(direction, false);
  }, {passive: true});
  window.addEventListener('touchcancel', () => { touchStart = null; }, {passive: true});

  window.addEventListener('keydown', event => {
    const target = event.target;
    if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.closest('[role="textbox"]'))) return;
    if (event.key === 'PageDown' || event.key === 'ArrowDown' || (event.key === ' ' && !event.shiftKey)) {
      event.preventDefault();
      turn(1);
    } else if (event.key === 'PageUp' || event.key === 'ArrowUp' || (event.key === ' ' && event.shiftKey)) {
      event.preventDefault();
      turn(-1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      showPage(0, {history: 'push', focus: true});
    } else if (event.key === 'End') {
      event.preventDefault();
      showPage(pages.length - 1, {history: 'push', focus: true});
    }
  });

  window.addEventListener('popstate', () => {
    showPage(pageById.get(location.hash.slice(1)) ?? 0, {history: 'none', focus: true});
  });
  window.addEventListener('hashchange', () => {
    showPage(pageById.get(location.hash.slice(1)) ?? 0, {history: 'none', focus: false});
  });

  showPage(index, {history: location.hash ? 'none' : 'replace', focus: false});
  syncLanguageLinks(pageHash(pages[index]));
  document.documentElement.dataset.sitePages = 'ready';
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.dataset.siteMotion = 'ready';
  }));
  reduced.addEventListener('change', () => track.toggleAttribute('data-reduced-motion', reduced.matches));
  track.toggleAttribute('data-reduced-motion', reduced.matches);
})();
