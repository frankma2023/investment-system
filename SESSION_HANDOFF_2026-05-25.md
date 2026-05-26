# 投资系统开发交接 — 2026-05-25

## 当前状态

### 运行环境
- **Flask**: `http://localhost:8788`（API）
- **前端**: `http://localhost:8772`（`python -m http.server`）
- **Python**: `C:\Program Files\Python312\python.exe`
- **工作区**: `D:\dstui`（DeepSeek TUI 运行目录）
- **项目目录**: `D:\hanako\investment-system`

### 数据库
- `data/lixinger.db`
- 观察池最新日期可能是 05-21（需重跑 `observation.py` 更新到 05-25）
- 指数精选快照已有 05-25 数据
- 股票精选快照可能停留在 05-21

## 已完成的核心功能

### 1. 股票精选（六层 O'Neil 筛选）
- **引擎**: `src/discipline/screener.py`
- **评分 PRD**: `docs/product/欧奈尔每日精选_评分引擎_PRD.md`
- **规则文档**: `docs/欧奈尔每日精选_六层筛选规则.html`
- **快照表**: `discipline_screening_daily`
- **前端**: `web/discipline/screening.html`（股票/指数切换标签）
- **评分公式**: `O'Neil = CANSLIM×0.30 + RPS250×0.30 + 信号×0.25 + 共振×0.15`
- **信号分**: 最佳主信号（base_breakout/pocket_pivot 基础分=70）+ 衰减 + 额外加分
- **买点取值链**: `close > breakout_close > breakout_price > buy_point`

### 2. 指数精选（四层筛选）
- **PRD**: `docs/product/欧奈尔每日精选_指数版_PRD.md`
- **引擎**: `src/discipline/index_screener.py`
- **快照表**: `discipline_screening_daily_index`
- **评分**: `RPS250×0.50 + 信号分×0.50`
- **信号引擎白名单**: `['base_breakout','pocket_pivot','cdl_engine','talib_engine']`（`engine_registry.py` `whitelist` 参数）
- **指数复核页**: `web/discipline/review-index.html`（K线+信号+四层拆解）

### 3. 回测看板
- **PRD**: `docs/product/精选回测看板_PRD.md`
- **股票回测**: `web/discipline/screening-backtest.html` + API `/api/discipline/screening-backtest`
- **指数回测**: `web/discipline/screening-backtest-index.html` + API `/api/discipline/screening-backtest-index`
- **回测指标**: 5/10/20 交易日收益 + 胜率
- **导航栏**: `web/shared/js/nav.js`（回测菜单含"精选回测""指数回测"，主导航含"精选"）

### 4. CANSLIM 评分引擎
- `src/scanners/canslim_score.py`（v3 版本，满分 100 归一化）
- 评分卡 PRD: `docs/product/CAN SLIM评分卡.md`
- 前端: `web/canslim-scorecard/`、`web/canslim-scores/`
- 默认降序排列（`app.js` 中 `sortDir=1`）

### 5. 形态检测引擎
- `base_breakout`, `pocket_pivot`, `cdl_engine`, `talib_engine` 四个核心引擎
- `engine_registry.py` 的 `run_all_engines` 支持 `whitelist` 参数

## 关键技术要点

### 易踩坑
1. **sqlite3.Row 不支持 `.get()`** — 必须用 `row['field']` 或 `dict(row)` 转换
2. **`.pyc` 缓存** — 改代码后清除 `__pycache__` 目录，否则 Flask 跑旧代码
3. **`indicators=None` 导致引擎崩溃** — 调用 `run_all_engines` 前必须先 `_compute_indicators(klines)`
4. **买点 ≠ 信号日收盘价** — base_breakout 的 `buy_point` 是基部前高+0.01，取值链用 `close` 优先
5. **精选 API 缓存** — `api_screening` 已改为优先读快照表，无数据时才实时计算
6. **`datetime.now()` 不应作为信号窗口基准** — 已全部改为 `target_dt`

### 经验教训（完整见 `web/progress.html` #39-44）
- #39: sqlite3.Row 不支持 .get()
- #40: 引擎崩溃静默吞错  
- #41: .pyc 缓存陷阱
- #42: K线图样式必须与已有页面一致
- #43: buy_point 语义陷阱
- #44: API 缓存策略

## 待处理

1. **股票精选数据过期**: `discipline_screening_daily` 只有 05-21 数据，需重跑 `observation.py` + `screener.py` 更新到 05-25
2. **指数引擎崩溃**: `base_breakout` 和 `pocket_pivot` 对部分指数仍报 `NoneType` 错误（被 whitelist 规避，仅影响信号数）
3. **每日精选推荐信**: 点击"精选理由"链接受限，多数股票无推荐内容

## 日更流水线（`scripts/daily_update.py`）

```
1-3: 股票/指数K线拉取
4: 基本面拉取
5-8: 指数拥挤度/融资融券/大盘健康度/快照
9a: 个股RS
9b: 指数RS
10: 全A形态扫描
11: 机构持股（周一）
12: 研报（周一）
13: 回购（周一）
14: CANSLIM评分
15: 观察池日更
16: 持仓监控
17: 股票精选
18: 指数精选
```

## 下次会话建议加载的 Skills
- `review` — 代码审查
- `to-prd` — 产品需求书
- `documents` / `presentations` — 文档/演示
