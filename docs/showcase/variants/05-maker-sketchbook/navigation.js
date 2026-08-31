// 只接管已握手的公开预览；不开放跨源DOM、顶层跳转或任意文件路径。
(() => {
  'use strict';
  const files = new Set(['review.html', 'compare.html', 'explain.html', 'form.html', 'history.html']);
  const frames = ['.hero-frame', '[data-example-frame]', '[data-usage-frame]'].flatMap(selector => [...document.querySelectorAll(selector)]);
  const connections = new Map();
  let sequence = 0;

  function connect(frame) {
    const token = `preview-${++sequence}`;
    connections.set(frame, token);
    frame.contentWindow?.postMessage({type: 'html-reply-preview:connect', token}, '*');
  }

  frames.forEach(frame => {
    frame.addEventListener('load', () => connect(frame));
    connect(frame);
  });
  window.addEventListener('load', () => frames.forEach(connect));
  window.addEventListener('message', event => {
    const data = event.data;
    if (data?.type !== 'html-reply-preview:navigate' || !files.has(data.file)) return;
    const frame = frames.find(item => item.contentWindow === event.source);
    if (!frame || data.token !== connections.get(frame)) return;
    const navigation = new CustomEvent('showcase-preview:navigate', {detail: {file: data.file}, cancelable: true});
    // 阅读区与工作台各自同步状态；首屏直接切换自身iframe。
    if (frame.dispatchEvent(navigation)) frame.src = window.ShowcaseLocale.exampleUrl(data.file);
  });
})();
