# 小红书回测页面风格指南

> 用途：将此文档作为 prompt 上下文喂给任何 AI 模型，使其生成与现有回测看板一致的小红书风格页面。
> 参考实现：`web/distribution-day/` | `web/index-rs-backtest/` | `web/index-crowdedness/`

---

## 一、CSS 依赖（按顺序引入）

```html
<link rel="stylesheet" href="../shared/css/theme.css">
<link rel="stylesheet" href="../shared/css/base.css">
<link rel="stylesheet" href="../shared/css/xhs-cards.css">
<link rel="stylesheet" href="../shared/css/components.css">
<script src="../shared/js/theme.js"></script>
```

如需图表：
```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
```

---

## 二、HTML 骨架

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[模块名] · 投资手账本</title>
  <link rel="stylesheet" href="../shared/css/theme.css">
  <link rel="stylesheet" href="../shared/css/base.css">
  <link rel="stylesheet" href="../shared/css/xhs-cards.css">
  <link rel="stylesheet" href="../shared/css/components.css">
  <style>
    /* 页面特有样式写在这里 */
  </style>
</head>
<body>
  <!-- 手账装饰元素 -->
  <div class="journal-dots"></div>
  <div class="washi-tape washi-1"></div>
  <div class="washi-tape washi-2"></div>

  <div class="app-container">
    <!-- 导航栏 -->
    <nav class="top-nav">...</nav>

    <!-- 主内容区 -->
    ...

    <!-- 页脚 -->
    <footer class="page-footer">❤️ 投资手账本 · [模块名] · 量化你的直觉</footer>
  </div>

  <script src="../shared/js/theme.js"></script>
  <script>
    // 页面特有 JS
  </script>
</body>
</html>
```

---

## 三、导航栏

**结构固定不变。** 所有回测页面导航栏完全相同，只在当前页加 `active` 类。

```html
<nav class="top-nav">
  <div class="nav-brand">
    <span class="nav-fox">🦊</span>
    <span>[页面名称]</span>
    <span class="nav-greeting">[英文副标题]</span>
  </div>
  <div class="nav-links">
    <a href="../" class="nav-item">🏠 看板</a>
    <a href="../distribution-day/" class="nav-item">📉 抛盘日</a>
    <a href="../follow-through-day/" class="nav-item">📈 追盘日</a>
    <a href="../index-rs-backtest/" class="nav-item">🏆 指数强度</a>
    <a href="../index-crowdedness/" class="nav-item">📊 拥挤度</a>
    <a href="[当前页路径]" class="nav-item active">[当前页名称]</a>
    <button class="theme-toggle" onclick="toggleTheme()">🌙</button>
  </div>
</nav>
```

新增页面时，在所有已有页面的导航栏里也加上新页面的 `<a>` 链接。

---

## 四、页面布局：左侧配置 + 右侧结果

```html
<div class="bt-layout">
  <!-- 左侧参数面板 -->
  <div class="bt-left">
    <!-- 参数卡片 -->
  </div>

  <!-- 右侧结果区 -->
  <div class="bt-right">
    <!-- 结果表格/图表 -->
  </div>
</div>
```

CSS：
```css
.bt-layout { display:flex; gap:16px; align-items:flex-start; }
.bt-left { width:320px; flex-shrink:0; display:flex; flex-direction:column; gap:12px; }
.bt-right { flex:1; min-width:0; display:flex; flex-direction:column; gap:16px; }
@media (max-width:900px) { .bt-layout { flex-direction:column; } .bt-left { width:100%; } }
```

---

## 五、组件目录

### 5.1 通用内容卡片 `.xhs-card`

```html
<div class="xhs-card">
  <div class="xhs-card-header">
    <span class="xhs-card-label">📊 卡片标题</span>
  </div>
  <!-- 卡片内容 -->
</div>
```

### 5.2 可折叠参数卡片 `.param-card`

用于左侧配置面板。每张卡片含：彩色圆点 + 标题 + 开关按钮 + 可折叠参数区。

```html
<div class="param-card" id="card1">
  <div class="param-card-header" onclick="toggleCard('card1')">
    <span class="dot" style="background:#FE2C55"></span>
    <span class="title">🔴 卡片标题</span>
    <button class="toggle on" id="card1-toggle"
      onclick="event.stopPropagation();toggleCardEnabled('card1')"></button>
  </div>
  <div class="param-card-body" id="card1-body">
    <div class="slider-row">
      <span class="s-label">参数名</span>
      <input type="range" min="0" max="99" value="90"
        oninput="syncSliderVal('param-id')">
      <span class="s-val" id="param-id-v">90</span>
    </div>
  </div>
</div>
```

CSS：
```css
.param-card { background:var(--card-bg); border:1px solid var(--divider); border-radius:18px; overflow:hidden; }
.param-card-header { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; cursor:pointer; }
.param-card-header .dot { width:10px; height:10px; border-radius:50%; margin-right:8px; flex-shrink:0; }
.param-card-header .title { font-size:0.82rem; font-weight:800; flex:1; font-family:var(--font-display); }
.param-card-header .toggle { width:40px; height:22px; border-radius:11px; border:none; cursor:pointer; }
.param-card-header .toggle.on { background:#FE2C55; }
.param-card-header .toggle.off { background:#CCC; }
.param-card-body { padding:0 16px 14px; }
.param-card-body.collapsed { display:none; }

.slider-row { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.slider-row .s-label { width:72px; font-size:0.65rem; font-weight:600; color:var(--text-tertiary); flex-shrink:0; }
.slider-row input[type=range] { flex:1; height:4px; }
.slider-row .s-val { width:44px; text-align:right; font-size:0.7rem; font-weight:700; flex-shrink:0; }
```

JS：
```javascript
function toggleCard(id) {
  document.getElementById(id+'-body').classList.toggle('collapsed');
}
function toggleCardEnabled(id) {
  var btn = document.getElementById(id+'-toggle');
  btn.classList.toggle('on'); btn.classList.toggle('off');
}
function syncSliderVal(id) {
  document.getElementById(id+'-v').textContent = document.getElementById(id).value;
}
```

### 5.3 禁用卡片

当某功能暂不可用时，卡片整体降低透明度并禁用交互：

```html
<div class="param-card" style="opacity:0.55;">
  <div class="param-card-header">
    ...
    <button class="toggle off disabled"></button>
  </div>
  <div class="param-card-body disabled-body">
    <!-- disabled 的控件 -->
    <div style="font-size:0.6rem;color:var(--text-tertiary)">⏳ 待XX引擎就绪后启用</div>
  </div>
</div>
```

```css
.param-card-header .toggle.disabled { background:#E0E0E0; cursor:not-allowed; }
.param-card-body.disabled-body { opacity:0.4; pointer-events:none; }
```

### 5.4 操作按钮

```html
<button class="btn-run" id="btn-run">🔍 计算</button>
<button class="btn-save" id="btn-save">💾 保存配置</button>
```

```css
.btn-run { width:100%; padding:12px; background:#FE2C55; color:#FFF; border:none;
  border-radius:14px; font-size:1rem; font-weight:800; cursor:pointer;
  box-shadow:0 2px 8px rgba(254,44,85,0.18); font-family:var(--font-display); }
.btn-run:hover { opacity:0.88; }
.btn-run:disabled { background:#CCC; box-shadow:none; cursor:not-allowed; }
.btn-save { width:100%; padding:10px; background:var(--card-bg); color:#FE2C55;
  border:1px solid rgba(254,44,85,0.2); border-radius:14px;
  font-size:0.85rem; font-weight:700; cursor:pointer; font-family:var(--font-display); }
```

### 5.5 统计卡片组

```html
<div class="stat-cards">
  <div class="stat-card">
    <div class="stat-value" id="stat-total">—</div>
    <div class="stat-label">总计</div>
  </div>
</div>
```

```css
.stat-cards { display:flex; gap:8px; flex-wrap:wrap; }
.stat-card { flex:1; min-width:70px; background:var(--card-bg);
  border:1px solid var(--divider); border-radius:12px; padding:10px 12px; text-align:center; }
.stat-value { font-size:1.4rem; font-weight:900; font-family:var(--font-display); }
.stat-label { font-size:0.65rem; font-weight:600; color:var(--text-tertiary); }
```

### 5.6 数据表格 `.data-table`

表头可排序列加 `.sortable` 类：

```html
<div class="table-wrapper" id="table-id">
  <table class="data-table">
    <thead>
      <tr>
        <th class="sortable" data-col="0" data-type="number">列名</th>
        <th class="sortable" data-col="1" data-type="string">列名</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
</div>
```

```css
th.sortable { cursor:pointer; user-select:none; position:relative; padding-right:18px !important; }
th.sortable:hover { color:#FE2C55; }
th.sortable::after { content:'↕'; position:absolute; right:4px; font-size:0.6rem; opacity:0.3; }
th.sortable[data-indicator="asc"]::after { content:'↑'; opacity:1; color:#FE2C55; }
th.sortable[data-indicator="desc"]::after { content:'↓'; opacity:1; color:#FE2C55; }
```

排序JS：
```javascript
function sortTable(table, col, type, asc) {
  var tbody = table.querySelector('tbody');
  var rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort(function(a, b) {
    var va = a.children[col].textContent.trim();
    var vb = b.children[col].textContent.trim();
    if (type === 'number') { va = parseFloat(va.replace(/[^\d.\-]/g,''))||0; vb = parseFloat(vb.replace(/[^\d.\-]/g,''))||0; }
    return asc ? (va < vb ? -1 : va > vb ? 1 : 0) : (va > vb ? -1 : va < vb ? 1 : 0);
  });
  rows.forEach(function(r) { tbody.appendChild(r); });
}
```

### 5.7 模态弹窗

```html
<div class="modal-overlay" id="modal-id" style="display:none;">
  <div class="modal-content">
    <div class="modal-header">
      <span class="modal-title">标题</span>
      <button class="modal-close" onclick="closeModal('modal-id')">✕</button>
    </div>
    <div class="modal-body" id="modal-id-body"></div>
  </div>
</div>
```

```css
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:1000;
  display:flex; align-items:center; justify-content:center; }
.modal-content { background:var(--card-bg); border-radius:20px;
  max-width:720px; width:90%; max-height:80vh; display:flex; flex-direction:column;
  box-shadow:0 8px 40px rgba(0,0,0,0.2); }
.modal-header { display:flex; align-items:center; justify-content:space-between;
  padding:16px 20px; border-bottom:1px solid var(--divider); }
.modal-title { font-weight:800; font-size:0.9rem; font-family:var(--font-display); }
.modal-close { background:none; border:none; font-size:1.2rem; cursor:pointer;
  color:var(--text-tertiary); padding:4px 8px; border-radius:8px; }
.modal-body { padding:16px 20px; overflow-y:auto; }
```

### 5.8 日期选择器 + 下拉菜单

```html
<div class="date-field">
  <label>计算日期</label>
  <input type="date" id="rs-date">
</div>

<div class="pool-select-wrap">
  <label>指数池</label>
  <select id="pool-select"></select>
</div>
```

```css
.date-field label, .pool-select-wrap label { display:block;
  font-size:0.65rem; font-weight:600; color:var(--text-tertiary); margin-bottom:4px;
  font-family:var(--font-display); }
.date-field input, .pool-select-wrap select { width:100%; padding:8px 10px;
  border:1px solid var(--divider); border-radius:12px; font-size:0.8rem;
  background:var(--card-bg); color:var(--text-primary); box-sizing:border-box;
  font-family:var(--font-display); }
```

### 5.9 Tab切换

```html
<div class="pool-tabs">
  <span class="pool-tab active" data-pool="market">全市场</span>
  <span class="pool-tab" data-pool="sector_l1">一级行业</span>
</div>
```

```css
.pool-tabs { display:flex; gap:4px; flex-wrap:wrap; }
.pool-tab { padding:8px 14px; border-radius:12px; border:1px solid var(--divider);
  background:var(--card-bg); font-size:0.72rem; font-weight:700; cursor:pointer;
  color:var(--text-secondary); font-family:var(--font-display); }
.pool-tab.active { background:#FE2C55; color:#FFF; border-color:#FE2C55; }
.pool-tab:hover:not(.active) { border-color:#FE2C55; color:#FE2C55; }
```

---

## 六、API 调用约定

后端：`http://localhost:8788`
API响应为JSON，前端通过 `fetch` 调用。

参数保存到后端YAML配置的端点：
```
GET  /api/config?signal_type=xxx       → 读取配置
POST /api/config?signal_type=xxx       → 保存配置
```

---

## 七、主题切换

所有页面使用统一的 `theme.js`，通过 `data-theme` 属性控制明暗模式。
`theme-toggle` 按钮的 `onclick="toggleTheme()"` 由 `theme.js` 提供。
不要在页面内重复实现 `toggleTheme` 函数。

主题存储键：`localStorage.setItem('theme', 'dark'|'light')`

---

## 八、文件命名约定

```
web/[模块名]/
├── index.html    ← 主页面
└── js/
    └── main.js   ← 主逻辑（可选，简单页面可内联在 index.html 中）
```

---

## 九、新增页面的检查清单

- [ ] 引入 `theme.css` + `base.css` + `xhs-cards.css` + `components.css`
- [ ] 引入 `theme.js`
- [ ] `<body>` 内包含 `journal-dots` + `washi-tape` ×2
- [ ] 导航栏与其他页面一致（含所有互链）
- [ ] 当前页的 `<a>` 有 `active` 类
- [ ] 使用 `.bt-layout` 实现左配置右结果布局
- [ ] 配置卡片用 `.param-card` 结构
- [ ] 内容卡片用 `.xhs-card` 结构
- [ ] 表格用 `.data-table`，需排序列加 `.sortable`
- [ ] 按钮用 `.btn-run` / `.btn-save`
- [ ] 页脚 `page-footer`
- [ ] 所有已有页面的导航栏添加新页面链接
- [ ] 首页 `web/index.html` 添加新页面的导航卡片
