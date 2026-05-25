# 欧奈尔 CAN SLIM A 股量化投资系统

基于威廉·欧奈尔 CAN SLIM 投资体系的 A 股全流程量化投资系统。覆盖大盘环境判断、指数扫描、个股基本面分析、买入/卖出形态识别、CAN SLIM 评分、持仓管理等完整投资决策链。

## 核心功能

| 模块 | 功能 | 页面 |
|------|------|------|
| **大盘环境** | 抛盘日/追盘日/吸筹日检测 + 大盘健康度评分 | `market-scan` |
| **指数扫描** | 407个指数多周期RS强度 + 三级强势池 + 拥挤度 + 机构吸筹出货 | `index-rs-backtest`、`index-scan`、`index-valuation` |
| **个股基本面** | 估值仪表/盈利质量/财务健康/市场强度 + DCF估值 + 三表联动 + 基本面恶化检测 | `stock-valuation` |
| **买入形态** | Layer 1 统一基部突破引擎 + 口袋支点 + 双重底 + 扁平基部 + 碟形基部 | `pattern-scan`、`base-breakout` |
| **卖出信号** | 高潮见顶/铁轨线/头部形态/量价背离/突破失败/基本面恶化 | 各独立回测看板 |
| **CAN SLIM 评分** | 七维评分卡（C/A/N/S/L/I）v3.0，全市场5300+只自动评分 | `canslim-scores`、`canslim-scorecard` |
| **回测体系** | 19个回测看板，YAML配置持久化，左参数卡+右信号表统一布局 | 各回测看板 |
| **知行系统** | 观察池/自选池/交易记录/持仓监控/买入前检查清单 | `discipline` |
| **每日更新** | 9步自动化：K线→财务→基本面→RS→拥挤度→机构→CANSLIM→形态扫描 | `daily_update.py` |

## 技术架构

```
python src/server.py          # Flask API (端口 8788, 74个端点)
python -m http.server 8772 --directory web/   # 静态前端 (端口 8772)
```

- **后端**: Python Flask + SQLite (20GB, WAL 模式)
- **前端**: 原生 JavaScript + ECharts 5.5.1
- **数据源**: 理杏仁开放 API
- **引擎自动发现**: `src/scanners/` 下任何实现 `detect()` + `ENGINE_META` 的模块自动注册
- **共享基础设施**: `nav.js` (全站导航) / `kline-chart.js` (K 线图) / `components.css` (UI 组件)
- **风格**: 小红书手账风格 (`theme.css` + `base.css` + `xhs-cards.css`)

## 项目结构

```
investment-system/
├── config/           ← YAML 配置文件 (canslim_scorecard / 各引擎参数)
├── src/
│   ├── server.py     ← Flask API 入口 (58 端点)
│   ├── engine_registry.py  ← 引擎自动发现
│   ├── scanners/     ← 15+ 形态检测引擎
│   ├── detectors/    ← 信号检测器
│   ├── analysis/     ← 财务分析 (基本面恶化/DCF/可比公司)
│   ├── discipline/   ← 知行系统 (观察池/交易/持仓)
│   └── backtest/     ← 回测引擎
├── web/              ← 前端 (30+ 页面)
│   ├── shared/       ← 共享 CSS/JS (导航/K线图/组件)
│   ├── market-scan/  ← 大盘扫描
│   ├── stock-valuation/  ← 个股全维度分析
│   ├── index-rs-backtest/  ← 指数RS强度
│   ├── pattern-scan/ ← 统一形态扫描
│   ├── canslim-scores/ ← CAN SLIM 全市场评分
│   ├── discipline/   ← 知行系统
│   └── */            ← 19 个回测看板
├── scripts/          ← 数据拉取 + 批量计算 (20+ 脚本)
├── docs/product/     ← 产品需求文档
└── data/             ← SQLite 数据库
```

## 快速开始

```bash
cd investment-system

# 1. 启动 API
python src/server.py

# 2. 启动前端
python -m http.server 8772 --directory web/

# 3. 访问
# http://localhost:8772
```

## 开发约定

- Python 命令用 `python` (非 `python3`)，文件 `encoding='utf-8'`
- 开发前 → `to-prd` 出需求文档；开发后 → `review` 对照验收
- `git commit` = `add -A + commit + push`
- 回测看板铁律：保存 → YAML 配置 + 加载 → 填充控件
- 引擎规范：`ENGINE_META` + `detect()` + `load_params()`
- 数据铁律：严禁兜底/估算值，缺失数据须通过 API 拉取

## 相关文档

- [项目全貌](./docs/PROJECT_OVERVIEW.md)
- [API 参考](./docs/API_REFERENCE.md)
- [数据库 Schema](./docs/DATABASE_SCHEMA.md)
- [工作交接](./docs/dev/HANDOVER.md)
- [产品需求文档](./docs/product/)
