// 语言由当前文档显式决定；交互共用实现，公开示例按语言独立保存。
(() => {
  'use strict';
  const english = document.documentElement.getAttribute('lang')?.toLowerCase().startsWith('en') === true;
  window.ShowcaseLocale = Object.freeze({
    language: english ? 'en' : 'zh-CN',
    text: (zh, en) => english ? en : zh,
    exampleUrl: file => (english ? '../../examples/en/' : '../../examples/') + file
  });

  // 切换语言保留当前章节；无脚本时仍能通过普通链接打开另一版本。
  function syncLanguageLinks() {
    const target = english ? 'index.html' : 'index.en.html';
    document.querySelectorAll('[data-language-link]').forEach(link => {
      link.setAttribute('href', target + (window.location?.hash || ''));
    });
  }
  syncLanguageLinks();
  window.addEventListener('hashchange', syncLanguageLinks);
})();
