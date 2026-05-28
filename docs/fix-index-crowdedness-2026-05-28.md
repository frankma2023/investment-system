# index-crowdedness 页面修复报告

> 日期：2026-05-28  
> 页面：`http://localhost:8772/index-crowdedness/`

## 背景

该页面在迁移到 `hanako-glass.css` 统一样式体系后出现多个问题。原始页面依赖旧版 CSS（`base.css`、`theme.css`、`xhs-cards.css`），迁移时仅替换为 `hanako-glass.css`，遗漏了必要的组件样式和变量映射。

## 问题及修复

### 1. 页面半透明蒙层 + 右上角"✕"符号

**现象**：页面被一层半透明黑色遮罩覆盖，右上角常驻一个关闭按钮"✕"。

**根因**：页面的成分股弹窗 `<div class="modal-overlay" id="constituent-modal">` 始终可见。`hanako-glass.css` 中 `.modal-overlay` 缺少 `display: none` 声明，导致模态层默认展示（`background: rgba(0,0,0,0.55)` 即为"蒙层"，关闭按钮即为"✕"）。

**修复**（`web/shared/css/hanako-glass.css` 第634行）：

```css
.modal-overlay {
  display: none;            /* ← 新增 */
  background: rgba(0,0,0,0.55);
  /* ... */
}
.modal-overlay.active {     /* ← 新增 */
  display: flex;
}
```

**影响范围**：统一了所有使用 `hanako-glass.css` 的页面的 modal 行为。

---

### 2. 所有组件样式缺失（卡片、滑块、按钮、统计卡片）

**现象**：页面的参数卡片、滑块、运行按钮、统计数字等全部无样式，布局混乱。

**根因**：页面大量使用 `.xhs-*` CSS class（`xhs-param`、`xhs-slider-row`、`xhs-btn-run`、`xhs-stat-card` 等），这些 class 的定义全部在 `web/shared/themes/xhs-backtest.css` 中，但页面未引用该文件。

**修复**（`web/index-crowdedness/index.html` `<head>`）：

```html
<link rel="stylesheet" href="../shared/css/hanako-glass.css">
<link rel="stylesheet" href="../shared/themes/xhs-backtest.css">  <!-- ← 新增 -->
```

---

### 3. 手账装饰元素残留

**现象**：导航栏上方有多余的空白区域。

**根因**：旧版 web 体系的手账装饰元素 `<div class="journal-dots">`、`<div class="washi-tape">` 仍在 HTML 中，但新版 CSS 未定义其样式，产生不可见但占位的空元素。

**修复**（`web/index-crowdedness/index.html` body）：

```diff
- <div class="journal-dots"></div>
- <div class="washi-tape washi-1"></div>
- <div class="washi-tape washi-2"></div>
```

---

### 4. 卡片底色为深棕色（而非深灰色）

**现象**：页面卡片（`.xhs-param`、`.xhs-stat-card`）的底色是暖棕色调，与其他页面的中性深灰不一致。

**根因**：`xhs-backtest.css` 的 dark 模式变量使用了两个独立问题：

**4a. 选择器不匹配**：dark 变量使用 `[data-theme="dark"]` 选择器，但页面使用 `<html class="dark">`（无 `data-theme` 属性），导致 dark 变量从未生效，fallback 到 `:root` 的亮色变量。

**4b. 变量值偏暖**：即使选择器修复后，原有的 dark 变量值（`--bg-card: #241c20`、`--bg-root: #1a1418`）为暖棕色调，与 `hanako-glass.css` 的中性灰（`#0f0f12`、`#1a1a1f`）不一致。

**修复**（`web/shared/themes/xhs-backtest.css`）：

```css
/* 修复前 */
[data-theme="dark"] {
  --bg-card: #241c20;       /* 深棕色 */
  --bg-root: #1a1418;       /* 深紫棕 */
  --color-accent: #FE2C55;  /* 小红书红 */
}

/* 修复后 */
html.dark,
html[data-theme="dark"] {
  --bg-card: #1a1a1f;                              /* 中性深灰 */
  --bg-root: #0f0f12;                              /* 与 --bg 一致 */
  --bg-surface: rgba(255,255,255,0.02);
  --border: rgba(255,255,255,0.06);
  --text-primary: #e4e4e7;
  --text-secondary: #a1a1aa;
  --text-tertiary: #8b8b90;
  --color-up: #10b981;                             /* 绿涨 */
  --color-down: #ef4444;                           /* 红跌 */
  --color-neutral: #f59e0b;
  --color-accent: #f59e0b;                         /* 统一金色主题 */
  --shadow-card: 0 1px 2px rgba(0,0,0,0.2), 0 4px 16px rgba(0,0,0,0.1);
}
```

---

## 涉及文件汇总

| 文件 | 修改内容 |
|------|---------|
| `web/index-crowdedness/index.html` | 添加 xhs-backtest.css 引用；移除 journal-dots/washi-tape 装饰元素 |
| `web/shared/css/hanako-glass.css` | `.modal-overlay` 添加 `display:none` 和 `.active` 状态 |
| `web/shared/themes/xhs-backtest.css` | 修复 dark 选择器为 `html.dark`；dark 变量统一为中性灰色调 |

## 经验教训

1. **迁移页面到统一 CSS 体系时**，必须检查页面使用的所有 CSS class 是否在目标体系中有定义
2. **CSS 变量命名空间**：不同 CSS 文件使用不同的变量名（如 `--bg` vs `--bg-root`），迁移时需建立映射或别名
3. **主题选择器一致性**：全站应统一使用同一种主题切换机制（`html.dark` / `html[data-theme="dark"]` / `html[data-theme="light"]`）
4. **旧版装饰元素**：迁移时需清理旧体系特有的 HTML 标记
