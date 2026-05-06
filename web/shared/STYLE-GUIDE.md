# 看板样式系统 · 使用指南

## 文件结构

```
web/
├── shared/
│   ├── themes/
│   │   ├── bloomberg.css    ← Bloomberg 终端风 · 设计令牌
│   │   └── neo.css          ← NEO 全息终端风 · 设计令牌 + 特效
│   ├── css/
│   │   └── dashboard-base.css  ← 公共组件样式（不绑定主题）
│   └── js/
│       ├── echarts.min.js      ← ECharts 5.5.1 本地副本
│       └── dashboard-core.js   ← 公共 JS（主题切换/图表/表格/配置栏）
```

## 两种风格定位

| | Bloomberg | NEO |
|---|---|---|
| **关键词** | Knolling 秩序美学、数据密集、杂志级排版 | 深空网格、玻璃拟态、霓虹光效 |
| **默认模式** | 深色（炭黑+暖灰） | 深色（深空黑+霓虹青） |
| **浅色模式** | 奶油纸白 | 洁净实验室白 |
| **字体** | JetBrains Mono + Noto Sans SC | Orbitron(标题) + Share Tech Mono(数据) + Noto Sans SC(正文) |
| **卡片** | 实色卡片 + 微阴影 | 玻璃拟态 + 切角装饰 + 扫描线 |
| **适用场景** | 回测看板、持仓管理、数据扫描 | 大盘扫描、行业强度、形态信号 |

## 使用方式

### 方式一：零代码（推荐快速原型）

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <title>我的看板</title>
  <!-- 1. 选择主题 -->
  <link rel="stylesheet" href="../shared/themes/bloomberg.css">
  <!-- 2. 公共组件 -->
  <link rel="stylesheet" href="../shared/css/dashboard-base.css">
  <!-- 3. ECharts + 公共 JS -->
  <script src="../shared/js/echarts.min.js"></script>
  <script src="../shared/js/dashboard-core.js"></script>
</head>
<body>
  <!-- 使用 .card .nav .data-table .config-panel 等公共类 -->
</body>
</html>
```

### 方式二：自定义样式（需要深度定制时）

在 `dashboard-base.css` 之后引入自己的 `<style>` 块，只覆盖需要的部分。

## CSS 变量速查（Bloomberg 主题示例）

```css
/* 背景 */
--bg-root        /* 页面底色 */
--bg-card        /* 卡片底色 */
--bg-surface     /* 表头底色 */

/* 文字 */
--text-primary   /* 主文字 */
--text-secondary /* 辅助文字 */
--text-tertiary  /* 暗淡文字 */

/* 涨跌 */
--color-up       /* 红色（涨） */
--color-down     /* 绿色（跌） */

/* 边框 */
--border         /* 默认边框 */
--border-subtle   /* 淡化边框 */

/* 阴影 */
--shadow-card    /* 卡片阴影 */

/* 字体 */
--font-mono      /* 等宽字体（数据） */
--font-sans      /* 无衬线（正文） */
--font-display   /* 展示字体（标题） */
```

## 公共 CSS 类

| 类名 | 用途 |
|------|------|
| `.nav` `.nav-brand` `.nav-link` `.nav-link.active` | 导航栏 |
| `.stats-strip` `.stat-cell` `.stat-label` `.stat-value` | 状态条（8格） |
| `.section` `.section-header` `.section-title` `.section-badge` | 区块标题 |
| `.card` | 标准卡片 |
| `.grid-1` ~ `.grid-4` `.grid-21` | 响应式网格 |
| `.data-table` `.table-wrap` | 可排序表格 |
| `.config-panel` `.config-grid` `.config-item` `.config-slider` | 参数配置栏 |
| `.chart-container` | 图表容器 |
| `.warning-strip` | 警示条 |
| `.theme-btn` | 深浅模式按钮 |
| `.td-up` `.td-down` | 表格涨跌颜色 |
| `.badge-up` `.badge-down` `.badge-neutral` | 状态徽章 |

## 公共 JS API（Dashboard 对象）

```javascript
// 初始化主题（深色默认）
Dashboard.initTheme('dark');

// 切换主题
Dashboard.toggleTheme();

// 生成模拟K线数据（200个交易日）
var data = Dashboard.generateKline(3800);

// 计算移动平均
var ma20 = Dashboard.calcMA(data, 'close', 20);

// 渲染K线图
Dashboard.buildKline('klineChart', data, themeObj);

// 渲染状态条
Dashboard.renderStats('statsStrip', [
  {label:'市场阶段', value:'尝试反弹', cls:'stat-warn'},
  ...
]);

// 渲染表格
Dashboard.renderTable('tableContainer', columns, keys, data);

// 渲染配置栏
Dashboard.renderConfig('configGrid', configParams);
```

## 开发规范

1. **新看板优先使用公共类**：`.card` 而非手写卡片样式
2. **颜色只用 CSS 变量**：永远不硬编码色值
3. **深浅模式必须测试**：所有新页面必须在两种模式下验证
4. **图表用 Dashboard JS**：K线/表格/配置栏走公共 API，保持交互一致
5. **不修改主题文件**：如需新增变量，在页面内 `:root` 追加，待稳定后合并
