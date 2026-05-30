# 蹩脚猫 A 股量化投资系统 (biejiaomao)

基于威廉·欧奈尔 CAN SLIM 投资体系的 A 股全流程量化投资系统，集成缠论技术分析作为平行维度。覆盖大盘环境判断、指数扫描、个股基本面分析、买入/卖出形态识别、缠论分析、CAN SLIM 评分、持仓管理等完整投资决策链。

## 核心功能

| 模块 | 功能 | 页面 |
|------|------|------|
| **大盘环境** | 抛盘日/追盘日/吸筹日检测 + 大盘健康度评分卡 | `market-scan` |
| **指数扫描** | 407个指数多周期RS强度 + 最强指数 + 拥挤度 + 机构吸筹出货 + 估值分位 | `index-scan`、`index-valuation`、`strongest-index` |
| **个股基本面** | 估值仪表/盈利质量/财务健康/DCF估值/三表联动/基本面恶化检测 | `stock-valuation` |
| **买入形态** | 基部突破 + 口袋支点 + 双重底 + 扁平基部 + 碟形基部 + 杯柄形态 | `pattern-scan`、`base-breakout` |
| **卖出信号** | 高潮见顶/铁轨线/头部形态/量价背离/突破失败/基本面恶化 | 各独立回测看板 |
| **缠论分析** | 分型→笔→中枢→背驰→买卖信号 + 日/周/月多周期联立 + 共振评分 | `chanlun-backtest` |
| **CAN SLIM 评分** | 七维评分卡（C/A/N/S/L/I/M）v3.0，全市场 5300+ 只自动评分 | `canslim-scores`、`canslim-scorecard` |
| **回测体系** | 21 个回测看板，YAML 配置持久化，左参数卡+右信号表统一布局 | 各回测看板 |
| **知行系统** | 每日精选 + 观察池 + 自选池 + 交易记录 + 持仓监控 + 买入前检查清单 | `discipline` |
| **全市场扫描** | 每日双强股形态扫描（内嵌 4000+ 股票数据，客户端分页筛选）| `daily-pattern-scan` |
| **每日更新** | 自动化数据流水线：K线→财务→基本面→RS→拥挤度→机构→CANSLIM→形态扫描 | `scripts/daily_update.py` |

## 技术架构

```
python src/server.py                              # Flask API (端口 8788)
python -m http.server 8772 --directory web/        # 静态前端 (端口 8772)
```

- **后端**: Python Flask + SQLite（20GB，WAL 模式）
- **前端**: 原生 JavaScript + ECharts 5.5.1
- **数据源**: 理杏仁开放 API
- **缠论核心**: CZSC（Rust 实现，分型/笔计算）+ 自研中枢/背驰/信号引擎
- **引擎自动发现**: `src/` 下实现 `detect()` + `ENGINE_META` 的模块自动注册
- **共享基础设施**: `nav.js`（全站导航） / `kline-chart.js`（通用 K 线图） / `hanako-glass.css`（全站设计系统）
- **风格**: hanako-glass 玻璃拟态设计系统（深浅双模式，41 页统一）

## 项目结构

```
investment-system/
├── config/              ← YAML 配置文件（引擎参数/回测）
├── src/
│   ├── server.py        ← Flask API 入口
│   ├── engine_registry.py ← 引擎自动发现
│   ├── scanners/        ← 形态检测引擎（含 chanlun.py 缠论）
│   ├── detectors/       ← 信号检测器
│   ├── analysis/        ← 财务分析（基本面恶化/DCF/可比公司）
│   ├── discipline/      ← 知行系统（观察池/交易/持仓/精选）
│   └── backtest/        ← 回测引擎
├── web/                 ← 前端（41 页面）
│   ├── shared/          ← 共享 CSS/JS（hanako-glass.css / nav.js / kline-chart.js）
│   ├── market-scan/     ← 大盘扫描
│   ├── stock-valuation/ ← 个股全维度分析
│   ├── chanlun-backtest/← 缠论分析看板
│   ├── pattern-scan/    ← 统一形态扫描
│   ├── canslim-scores/  ← CAN SLIM 全市场评分
│   ├── daily-pattern-scan/ ← 全市场形态扫描
│   ├── discipline/      ← 知行系统 + 精选回测
│   └── */               ← 21 个回测看板
├── scripts/             ← 数据拉取 + 批量计算
├── docs/
│   ├── product/         ← 产品需求文档（20+ 篇）
│   └── dev/             ← 开发标准 + 交接文档
└── data/                ← SQLite 数据库（lixinger.db）
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

- Python 命令用 `python`（非 `python3`），文件 `encoding='utf-8'`
- 开发前 → `to-prd` 出需求文档；开发后 → `review` 对照验收
- `git commit` = `add -A + commit + push` 一条龙
- 回测看板铁律：保存 → YAML 配置 + 加载 → 填充控件
- 引擎规范：`ENGINE_META` + `detect()` + `load_params()`
- 数据铁律：严禁兜底/估算值，缺失数据须通过 API 拉取
- 样式铁律：`hanako-glass.css` 是唯一真相源，页面不覆盖 `.app-container`

## 相关文档

- [项目全貌](./docs/PROJECT_OVERVIEW.md)
- [API 参考](./docs/API_REFERENCE.md)
- [数据库 Schema](./docs/DATABASE_SCHEMA.md)
- [工作交接](./docs/dev/HANDOVER.md)
- [产品需求文档](./docs/product/)
- [缠论分析引擎 PRD](./docs/product/缠论分析引擎_产品需求书.md)
- [缠论回测看板 PRD](./docs/product/缠论回测看板_产品需求书.md)
