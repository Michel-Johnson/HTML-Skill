// 示例窗口保持固定，长HTML只在自身iframe中阅读；整站章节由site-pages.js翻页。
(() => {
  'use strict';
  const track = document.querySelector('[data-reading-track]');
  const stage = track?.querySelector('[data-preview-stage]');
  if (!track || !stage) return;

  let activePane = null;

  window.ShowcaseReading = {
    // preview.js借此跳过内容高度动画；外层章节不依赖示例文档高度。
    get pinned() { return true; },
    setContent(pane) {
      activePane = pane;
      track.dataset.readingNative = 'true';
      stage.querySelectorAll('[data-preview-pane]').forEach(item => {
        item.style.translate = '';
        item.style.minHeight = '';
      });
      activePane.style.height = '100%';
    }
  };
})();
