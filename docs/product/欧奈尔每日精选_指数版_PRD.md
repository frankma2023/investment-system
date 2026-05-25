# 欧奈尔每日精选（指数版）— 产品需求书 v1.0

## Problem Statement

用户已通过 `screener.py` 实现对 A 股的六层 O'Neil 精选，每日输出 TOP 20 股票。但在实际投资中，当对个股信心不足或市场风险偏好低时，用户会转向指数 ETF 降低风险。目前系统不具备指数筛选能力——无法回答"今天哪些指数最值得买入"。

用户拥有 407 只指数的日 K 线和 RS 数据（覆盖市场/一级行业/二级行业/主题/策略 5 个池），信号引擎 `base_breakout` 和 `pocket_pivot` 已支持 `mode=index` 模式。需要一个与股票精选并行的指数精选引擎。

## Solution

新增指数精选引擎 `index_screener.py`，采用简化的四层漏斗（指数无财报、无需行业共振），复用现有信号引擎和 K 线/RS 数据，输出每日 TOP 20 指数。

1. **四层筛选**：大盘闸门 → RS 强度 → 趋势健康 → 技术信号
2. **双维评分**：RPS_250 × 0.50 + 信号分 × 0.50
3. **前端集成**：精选页增加"股票/指数"切换标签
4. **快照落盘**：`discipline_screening_daily_index` 表，与股票回测结构对齐
5. **回测支持**：指数版回测 API + 页面

## User Stories

1. 作为交易员，我可以在精选页面切换到"指数"模式，查看当前最强的 20 只指数，以便在市场不确定时选择 ETF 替代个股
2. 作为交易员，我希望指数精选包含全部 5 个池（市场/一级行业/二级行业/主题/策略），以便不遗漏任何类别
3. 作为交易员，我希望指数精选门槛略低于股票（RS 放宽、无 CANSLIM），因为指数波动天然小于个股
4. 作为交易员，我希望看到每只精选指数的 RS 强度、信号摘要和买点价格，以便快速判断
5. 作为交易员，我可以通过回测页面选择日期，查看指数精选的历史表现（5/10/20 日收益和胜率）
6. 作为交易员，我希望指数精选支持 `--date` 参数指定历史日期，以便离线回溯
7. 作为开发者，我希望指数精选引擎复用 `base_breakout` 和 `pocket_pivot` 引擎的 index 模式，不重复开发信号逻辑
8. 作为开发者，我希望指数精选结果自动写入快照表，纳入每日更新流水线

## Implementation Decisions

### ID1: 四层筛选漏斗

| 层 | 名称 | 规则 | 淘汰条件 |
|----|------|------|---------|
| 1 | 大盘闸门 | 大盘阶段非"上升/确认/反弹"→ 提醒但不过滤 | — |
| 2 | RS 强度 | RPS_250 ≥ 75 且 RPS_20 ≥ 80 | 不满足则淘汰 |
| 3 | 趋势健康 | MA10 > MA20 > MA50，近 5 日均量 > 50 日均量 × 1.2 | 不满足则淘汰 |
| 4 | 技术信号 | 近 20 日内出现 ≥1 个 `base_breakout` 或 `pocket_pivot` | 不满足则淘汰 |

**RS 阈值说明**：指数波动小于个股，RPS_250 ≥ 75 即可进入前 25%，RPS_20 ≥ 80 确保短期动能充足。

**趋势健康说明**：替代股票的 CANSLIM 质量层。均线多头排列 = 上升趋势确认；量能放大 = 资金关注。

### ID2: 评分公式

```
Index_Score = RPS_250 × 0.50 + Signal_Score × 0.50
```

| 组件 | 满分 | 计算 |
|------|------|------|
| RPS_250 | 50 | `min(RPS_250, 100) / 100 × 50` |
| 信号分 | 50 | `min(信号分, 100) / 100 × 50` |

信号分计算规则**与股票精选完全一致**（PRD v2.0 ID2）：
- 最佳主信号分 = `max(base_breakout/pocket_pivot 的信号基础分 × 衰减)`
- 基础分 = 70，衰减 5日×1.0 / 10日×0.7 / 20日×0.4
- 额外加分：基部 +5（封顶 20），cdl/talib +2（封顶 10）
- 封顶 100

### ID3: 数据来源

| 数据项 | 来源 | 说明 |
|--------|------|------|
| K 线 | `index_daily_kline` | `WHERE stock_code=? AND kline_type='normal' ORDER BY date DESC LIMIT 400` |
| RS 强度 | `index_rs_daily` | 取最新日期数据 |
| 指数名称 | `index_style.yaml` 或 `stock_index` 表 | `load_index_names()` |
| 指数池 | `index_style.yaml` → `load_index_pools()` | 5 个池，共 407 只 |
| 信号 | `run_all_engines(klines, indicators)` | 引擎自动适配 index 模式 |

**关键差异**：指数不需要 `observation_pool` 中间表——直接从 `index_daily_kline` 和 `index_rs_daily` 读取，无需 `daily_update.py` 中的观察池步骤。

### ID4: 代码结构

```
src/discipline/index_screener.py   # 指数精选引擎（新增）
  ├── run(target_date=None)        # 主函数，返回 TOP 20
  ├── _compute_indicators()        # 技术指标（复用股票版）
  └── 自动写入 discipline_screening_daily_index

web/discipline/screening.html      # 修改：加股票/指数切换标签
web/discipline/screening-backtest-index.html  # 指数版回测页（新增）

src/discipline/trades_api.py       # 新增 API 端点
  ├── /api/discipline/screening?mode=index
  └── /api/discipline/screening-backtest-index?date=

data/schema.sql                    # 新增快照表
scripts/daily_update.py            # 新增步骤
```

### ID5: 指数快照表

表名：`discipline_screening_daily_index`

结构对齐股票版 `discipline_screening_daily`，去掉指数不适用的字段（`canslim_total`、`roe` 等，替换为 `rps_20`、`trend_score`）。

| 字段 | 类型 | 说明 |
|------|------|------|
| date | TEXT | PK(1) |
| rank | INTEGER | PK(2) |
| index_code | TEXT | 指数代码 |
| index_name | TEXT | 指数名称 |
| pool_name | TEXT | 所属池 |
| oneil_score | REAL | 综合得分 |
| rps_250 | REAL | RPS 250 |
| rps_20 | REAL | RPS 20 |
| signal_score | REAL | 信号分 |
| signal_count | INTEGER | 信号数 |
| signal_summary | TEXT | 信号摘要 |
| ideal_buy | REAL | 买点 |
| buy_signal_date | TEXT | 信号日 |
| buy_source | TEXT | 来源 |
| market_phase | TEXT | 大盘阶段 |

### ID6: API 端点

**股票/指数共用端点**：
```
GET /api/discipline/screening?mode=stock|index
```
`mode=stock` 调用 `discipline.screener.run()`（现有）
`mode=index` 调用 `discipline.index_screener.run()`（新增）

**指数回测端点**：
```
GET /api/discipline/screening-backtest-index?date=YYYY-MM-DD
```
返回结构对齐股票版，`items[].index_code` 替代 `stock_code`。

### ID7: 前端改造

精选页面 `screening.html` 顶部新增切换标签：
```
[📈 股票精选] [📊 指数精选]
```
切换时调用 `?mode=stock` 或 `?mode=index`，表格列头适配（`代码` → `指数代码`，`名称` → `指数名称`，移除 `CANSLIM/RPS250/ROE` 等股票专有列，新增 `所属池`、`RPS20` 列）。

指数回测页 `screening-backtest-index.html` 结构对齐股票版。

### ID8: 每日任务集成

`daily_update.py` 新增步骤 15：
```python
TASKS.append(("📊 指数精选", [PYTHON_EXE, "src/discipline/index_screener.py", "--date", today_str]))
```

指数精选依赖：指数 K 线（步骤 2）、指数 RS（步骤 6b），这些已在前面步骤完成。

## Testing Decisions

### 验收标准

1. `python src/discipline/index_screener.py` 输出 TOP 20 指数，含得分、信号、买点
2. 5 个指数池中均有指数可能上榜（不局限于单一池）
3. 信号分计算与股票版一致（BASE=70，衰减相同）
4. 指数回测页面可加载数据，5/10/20 日收益计算正确
5. `?mode=index` API 返回的 `items` 字段使用 `index_code`/`index_name`
6. 指定 `--date` 参数支持历史日期回测

### 测试方法

- 先运行 `python src/discipline/index_screener.py` 生成数据
- 浏览器访问 `http://localhost:8772/discipline/screening.html`，切换到"指数精选"
- 访问 `http://localhost:8772/discipline/screening-backtest-index.html`
- 交叉验证：某只指数的信号日在 K 线图上的收盘价与买点一致

## Out of Scope

- 不接入理杏仁 API 动态拉取新指数（维持现有 407 只配置）
- 不新增信号引擎（复用 `base_breakout` / `pocket_pivot`）
- 不修改 `index_style.yaml` 配置结构
- 不修改 `index_rs_daily` 表结构
- 不实现指数的多空/配对交易回测

## Further Notes

- 指数 K 线需包含 `kline_type='normal'` 以排除其他 K 线类型
- RPS 数据从 `index_rs_daily` 取最新的 `rs_20`、`rs_250` 字段
- 指数名称从 `load_index_names()` 获取（从 `index_style.yaml` 解析），回退到 `stock_index` 表
- 买点价格取值策略与股票版一致：`close` > `breakout_close` > `breakout_price` > `buy_point`
- 信号引擎通过 `run_all_engines()` 调用，引擎内部根据 K 线来源自动适配 `index` 模式
