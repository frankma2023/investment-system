# CAN SLIM 财务数据采集指南

> 创建日期：2026-04-06
> 用途：记录 CAN SLIM C/A/I 因子所需的财务数据采集经验，避免重复踩坑

---

## 一、数据表结构

### 1. canslim_quarterly_eps（季度EPS — C/A因子核心）

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT | 股票代码 |
| report_date | TEXT | 报告期（如 2025-12-31） |
| eps_basic | REAL | 基本每股收益（累计） |
| eps_diluted | REAL | 稀释每股收益（暂未采集） |
| revenue_yoy | REAL | 营收单季同比（小数形式，0.25=25%） |
| net_profit_yoy | REAL | 归母净利润单季同比 |
| np_atoopc_yoy | REAL | 扣非归母净利润单季同比 |
| updated_at | TEXT | 更新时间 |

**数据来源**：理杏仁 API #27（`api_stock_fs.py` → `FinancialStatementAPI`）

**指标路径**：
- `q.ps.beps.t` → eps_basic
- `q.ps.beps.c_y2y` → EPS同比（暂未用）
- `q.ps.npatoshopc.c_y2y` → 归母净利润同比 → net_profit_yoy & np_atoopc_yoy
- `q.ps.toi.c_y2y` → 营收同比 → revenue_yoy

### 2. canslim_annual_eps（年度EPS — A因子需要多年计算增长率）

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT | 股票代码 |
| report_date | TEXT | 报告期（如 2025-12-31） |
| eps_basic | REAL | 年度基本每股收益 |
| eps_diluted | REAL | 稀释每股收益（暂未采集） |
| revenue | REAL | 年度营业收入 |
| net_profit | REAL | 年度净利润 |
| roe | REAL | 年度ROE |
| updated_at | TEXT | 更新时间 |

**指标路径**：
- `y.ps.beps.t` → eps_basic
- `y.ps.np.t` → net_profit
- `y.ps.toi.t` → revenue
- `y.m.roe.t` → roe

### 3. canslim_institutional（机构持股 — I因子）

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT | 股票代码 |
| report_date | TEXT | 报告期 |
| fund_count | INTEGER | 持仓基金家数 |
| total_holdings | REAL | 持仓总量（股） |
| total_market_cap | REAL | 持仓市值（元） |
| total_share_pct | REAL | 占流通股比例（小数） |
| updated_at | TEXT | 更新时间 |

**数据来源**：理杏仁 API #20（`api_stock_fund_shareholders.py` → `FundShareholdersAPI`）

---

## 二、采集脚本

| 脚本 | 功能 | 运行方式 | 耗时 |
|------|------|----------|------|
| `scheduler/canslim_fetch_eps.py` | 采集季度+年度EPS（批量模式） | `python scheduler/canslim_fetch_eps.py` | ~20min |
| `scheduler/canslim_fix_annual_eps.py` | **修复版**：逐只补采年度EPS | `python scheduler/canslim_fix_annual_eps.py` | ~20min |
| `scheduler/canslim_fetch_institutional.py` | 采集公募基金持股（逐只） | `python scheduler/canslim_fetch_institutional.py` | ~30min |

---

## 三、⚠️ 踩坑记录（重要！）

### 坑1：年度EPS不能批量采集

**现象**：使用 `api.get_by_date(codes, "latest", metrics)` 批量查询年度指标（`y.` 前缀）时，**无论传入多少只股票，API 只返回1只股票的数据**。

**验证**：
- 季度指标（`q.` 前缀）：批量50只 → 返回50只 ✅
- 年度指标（`y.` 前缀）：批量5只 → 只返回1只 ❌

**结论**：理杏仁 API #27 的年度数据**必须逐只股票查询**，不能批量。

**正确做法**：
```python
# ❌ 错误：批量查询年度数据，会丢失大部分股票
data = api.get_by_date(["000001", "600519", "300750"], "latest", ["y.ps.beps.t"])

# ✅ 正确：逐只查询
for code in stock_codes:
    data = api.get_by_date([code], "latest", ["y.ps.beps.t"])
```

### 坑1.5：latest 只返回已发布年报的股票

**现象**：使用 `"latest"` 查询年度数据时，只返回已发布最新年报的股票。在年报季（3-4月），大部分公司还没发布，所以返回很少。

**解决**：使用**指定日期**查询历史年度数据：
```python
# 查2024年年报
data = api.get_by_date([code], "2024-12-31", ["y.ps.beps.t"])
```

**推荐做法**：循环采集多个年度（如2023/2024/2025），每年一份。对于当前年报季还未发布的年份，API会返回空。

### 坑2：季度EPS可以批量50只

季度指标（`q.` 前缀）批量模式完全正常，50只一批效率很高。

### 坑3：年度EPS的字段路径是 `y.` 不是 `q.`

- 季度：`q.ps.beps.t`（q = quarterly）
- 年度：`y.ps.beps.t`（y = yearly）
- 注意：部分年度指标路径与季度不同，如 `y.m.roe.t`（ROE在 `y.m` 下而非 `y.ps` 下）

### 坑4：report_date 格式不一致

不同数据源的 `report_date` 格式可能不同：
- 部分返回 `2025-12-31`（纯日期）
- 部分返回 `2025-12-31T00:00:00+08:00`（带时区）
- 写入数据库前应统一格式

### 坑5：基金持股API逐只查询，速度慢

API #20 每次只能查1只股票，5000+只需约30分钟。无解，只能等。

### 坑6：基金持股各季度数据量差异大

截至2026-04-06的数据：
- 2025Q1: 40条（极少，可能大部分股票Q1无基金持仓报告）
- 2025Q2: 1527条
- 2025Q3: 299条（Q3也偏少）
- 2025Q4: 5222条（最完整）

**原因**：A股基金季报披露规则——季报只披露前十大持仓，半年报/年报披露全部持仓。Q2和Q4数据来自中报/年报，所以最全。

---

## 四、当前数据覆盖（2026-04-06）

| 表 | 股票数 | 报告期 | 备注 |
|----|--------|--------|------|
| canslim_quarterly_eps | 5313/5595 | 2025Q2-Q4 | 批量采集，覆盖率高 |
| canslim_annual_eps | 5313/5595 | 2022-2025 | 4年数据，2022-2024全覆盖，2025年报季进行中(1262只已发布) |
| canslim_institutional | 5242/5595 | 2025Q1-Q4 | Q4最全(5222条) |

---

## 五、限流说明

- API #27 限流：36次/2秒 → 保守用 **30次/2秒**（年度逐只时）或 **32次/2秒**（季度批量时）
- API #20 限流：36次/2秒 → 保守用 **30次/2秒**
- 触发429时：等待5秒后重试1次

### 坑7：INSERT 列数与 VALUES 占位符不匹配导致 `19 values for 20 columns`

**现象**：运行 `fetch_stock_financials.py` 采集年度数据时，部分股票（如 000501、000503、000504）报错 `19 values for 20 columns`，但大部分股票无报错。

**根因**：年度表的 INSERT 语句定义了 20 列，但 VALUES 只写了 19 个 `?` 占位符。API 只对已发布历史年报的股票返回数据，大部分股票返回空列表（不触发 INSERT），只有有数据的股票才会触发此错误。

**修复**：
```python
# ❌ 错误：19 个占位符
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

# ✅ 正确：20 个占位符
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

**教训**：新增字段后务必同步更新 INSERT 语句的占位符数量。建议写成常量或从列名列表动态生成。

### 坑8：进度日志藏在 `if raw:` 里导致静默运行

**现象**：脚本运行中终端完全没有进度输出，像卡住一样，但实际在正常工作（API 调用和数据库写入都在进行）。

**根因**：进度日志写在 `if raw:` 判断内。当 API 返回空列表时（如查询未来季度或未发布年报的年份），`raw` 为空，不打印任何进度。用户会看到终端长时间静默，误以为脚本卡死。

**修复**：
```python
# ❌ 错误：空数据时不打印进度
if raw:
    log.info(f"    [{i+len(batch)}/{len(all_codes)}] +{n} 条")

# ✅ 正确：无论有无数据都打印进度
log.info(f"    [{i+len(batch)}/{len(all_codes)}] +{n} 条")
```

### 坑9：年度逐只采集时双重限流

**现象**：`fetch_stock_financials.py` 年度采集速度比预期慢一倍。

**根因**：`fetch_annual_one` 内先调用了独立的 `ANNUAL_LIMITER.wait()`，然后 `api_post` 内部又调用了全局 `_limiter.wait()`。两个 RateLimiter 各限 30次/2秒，实际变成 15次/2秒。

**修复**：`api_post` 已内置限流，`fetch_annual_one` 不需要额外限流器。去掉 `ANNUAL_LIMITER` 即可。

---

## 六、每日更新建议

1. **季度EPS**：每日增量运行 `canslim_fetch_eps.py`，用 `latest` 参数获取最新季报
2. **年度EPS**：年报季（3-4月）运行 `canslim_fix_annual_eps.py` 逐只补采
3. **基金持股**：每日运行 `canslim_fetch_institutional.py`，用 `latest` 参数
4. 建议加入 `daily_pipeline.py` 作为步骤8

---

## 七、后续改进

- [ ] 年度EPS需要采集**多个年度**（不只latest），用于计算3年/5年复合增长率
- [ ] 可考虑用 API 的 `date` 参数指定年份，循环采集2020-2025年
- [ ] 季度EPS也应采集多个季度（不只是latest），用于计算TTM EPS
- [ ] 统一 report_date 格式（去掉时区后缀）
- [ ] 增加 eps_diluted 采集
