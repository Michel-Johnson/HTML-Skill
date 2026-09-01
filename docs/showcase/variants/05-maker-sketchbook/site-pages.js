// 整个宣传前端按章节翻页；嵌入HTML保留自己的阅读与交互。
(() => {
  'use strict';

  const track = document.querySelector('[data-site-pages]');
  const pager = document.querySelector('[data-site-pager]');
  const pages = track ? [...track.querySelectorAll(':scope > [data-site-page]')] : [];
  const previous = pager?.querySelector('[data-site-prev]');
  const next = pager?.querySelector('[data-site-next]');
  const label = pager?.querySelector('[data-site-label]');
  const status = pager?.querySelector('[data-site-status]');
  if (!track || !pager || !previous || !next || !label || !status || !pages.length) return;

  const english = document.documentElement.lang.toLowerCase().startsWith('en');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const pageById = new Map(pages.map((page, index) => [page.id, index]));
  const pageLinks = [...document.querySelectorAll('a[href^="#"]')].filter(link => pageById.has(link.hash.slice(1)));
  let index = pageById.get(location.hash.slice(1)) ?? 0;

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

  function updateControls() {
    const page = pages[index];
    document.documentElement.dataset.siteTone = page.classList.contains('privacy') ? 'dark' : 'light';
    previous.disabled = index === 0;
    next.disabled = index === pages.length - 1;
    previous.setAttribute('aria-disabled', String(previous.disabled));
    next.setAttribute('aria-disabled', String(next.disabled));
    label.textContent = page.dataset.siteLabel || page.id;
    status.textContent = english ? `Page ${index + 1} of ${pages.length}` : `第 ${index + 1} / ${pages.length} 页`;
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
    updateControls();
    updateHistory(options.history || 'none');
    if (changed && options.focus) focusPage(pages[index]);
    if (changed) {
      window.dispatchEvent(new CustomEvent('showcase:site-page-change', {
        detail: {index, id: pages[index].id, label: pages[index].dataset.siteLabel || ''}
      }));
    }
  }

  function turn(delta, focus = true) {
    showPage(index + delta, {history: 'push', focus});
  }

  previous.addEventListener('click', () => turn(-1));
  next.addEventListener('click', () => turn(1));
  pageLinks.forEach(link => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    showPage(pageById.get(link.hash.slice(1)), {history: 'push', focus: true});
  }));

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
