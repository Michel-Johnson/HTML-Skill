# 工作台演示字体

## Codex App 中文

`NotoSansSC-UI.woff` 为 Noto Sans SC 2.04 的中文字符子集。来自本机已安装的开源可变字体，与用户同屏参照做字形比对后选用；上游为 [Google Fonts / Noto Sans SC](https://github.com/google/fonts/tree/main/ofl/notosanssc)。保留原字形及 100–900 字重轴，不包含用户截图或私人项目文字。

按 `index.html`、`usage.js` 和 `workbench.js` 现有文字收集 CJK 码点，使用 `python -m fontTools.subset` 生成 WOFF（`--name-IDs=* --name-languages=* --layout-features=*`）。当前子集含 472 个码点、155332 字节，覆盖新增菜单和输入反馈。保留字体名称和许可元数据；OFL 的保留名称是 `Source`，本子集未使用该保留名称。完整许可见 [OFL-NotoSansSC.txt](OFL-NotoSansSC.txt)。如果增加演示中文，需重建子集，避免缺字回退。

仅 `.codex-replica` 及 App 的预览栏使用此字体。侧栏/菜单中文取 `wght=600`，英文仍为 Segoe UI 常规体；聊天正文与预览栏由语义化 `font-weight` 决定字重，避免全局可变轴覆盖正文、标题的层级。不修改系统字体、不影响真实生成的 HTML 示例。

## Codex 终端

`CascadiaMono.woff2` 原样取自微软 [Cascadia Code v2407.24](https://github.com/microsoft/cascadia-code/releases/tag/v2407.24) 发布包的 `woff2/CascadiaMono.woff2`，仅供本页终端演示加载，不安装到系统，也不影响其他页面。

采用 SIL Open Font License 1.1，完整许可见 [LICENSE.txt](LICENSE.txt)。保留可变字重，不改字形、不拆分或转换字体。中文仍使用本机字体回退。
