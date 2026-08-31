// 两个候选只共享交互行为；布局和视觉样式各自独立。
(() => {
  const examples = {
    review: { title: '审查报告', file: 'review.html', prompt: '$html-reply 请审查这个模块，先给结论，再列问题和修改建议。', note: '结论先行、问题分组、代码高亮。示例内容虚构，没有修改真实项目。' },
    compare: { title: '方案对比', file: 'compare.html', prompt: '$html-reply 用表格对比这三个方案，并说明各自适合什么情况。', note: '把同一组维度放在一张表里，再给出简短的选择建议。' },
    explain: { title: '概念讲解', file: 'explain.html', prompt: '$html-reply 用具体例子解释缓存，并给一段简短代码。', note: '先讲一个例子，再拆步骤，最后用代码说明。' },
    form: { title: '交互表单', file: 'form.html', prompt: '$html-reply 把需要我确认的内容做成可填写的选项。', note: '真实表单：选择选项或离开文字输入框会下载 JSON。请只填演示内容；若嵌入预览的下载被拦截，可单独打开示例。' },
    history: { title: '历史回看', file: 'history.html', prompt: '打开回复右上角的「历史」，再进入「完整历史总览」。', note: '试着搜索“缓存”或“方案”。这是四条虚构回复组成的同一演示会话。' }
  };

  document.querySelectorAll('[data-demo-viewer]').forEach(viewer => {
    // 05由双缓冲控制器管理加载、导航与提醒；04保持原来的即时切换。
    if (viewer.hasAttribute('data-reading-viewer')) return;
    const frame = viewer.querySelector('iframe');
    const links = viewer.querySelectorAll('[data-example-link]');
    const prompt = viewer.querySelector('[data-example-prompt]');
    const note = viewer.querySelector('[data-example-note]');
    const buttons = [...viewer.querySelectorAll('[data-example]')];
    function select(button) {
      const example = examples[button.dataset.example];
      if (!example) return;
      buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      const url = '../../examples/' + example.file;
      frame.src = url;
      frame.title = 'HTML Reply 真实输出：' + example.title;
      links.forEach(link => { link.href = url; });
      if (prompt) prompt.textContent = example.prompt;
      const isForm = button.dataset.example === 'form';
      note.hidden = false;
      note.textContent = example.note;
      note.classList.toggle('download-notice', isForm);
      const label = viewer.querySelector('[data-example-filename]');
      if (label) label.textContent = example.file;
    }
    buttons.forEach(button => button.addEventListener('click', () => select(button)));
  });

  document.querySelectorAll('[data-tabs]').forEach(group => {
    const list = group.querySelector('[role="tablist"]');
    const buttons = [...list.querySelectorAll('[role="tab"]')];
    function select(button, focus) {
      buttons.forEach(item => {
        const selected = item === button;
        item.setAttribute('aria-selected', String(selected));
        item.tabIndex = selected ? 0 : -1;
        document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
      });
      if (focus) button.focus();
    }
    buttons.forEach((button, index) => {
      button.addEventListener('click', () => select(button, false));
      button.addEventListener('keydown', event => {
        let next = index;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % buttons.length;
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + buttons.length - 1) % buttons.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = buttons.length - 1;
        else return;
        event.preventDefault();
        select(buttons[next], true);
      });
    });
  });

  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.dataset.copy);
      const status = button.closest('[data-copy-block]').querySelector('[data-copy-status]');
      try {
        if (!navigator.clipboard) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(target.textContent.trim());
        status.textContent = '已复制';
      } catch (_) {
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = '已选中文字，请按 Ctrl+C（Mac：⌘C）复制。';
      }
    });
  });
})();
