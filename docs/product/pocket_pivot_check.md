# pocket_pivot.py 诊断报告

## Bug #2（中）：SMA 计算包含了当天价格 → 自我强化

```python
# 第 72 行 sma10
cs = [klines[j]['close'] for j in range(i-9, i+1)]  # ← i+1 含今天
# 第 75 行 sma50
cs = [klines[j]['close'] for j in range(i-49, i+1)]
```

信号日的强收盘价同时出现在分子（close > sma10 判断）和分母（SMA 计算）中——自己给自己作证。

对 SMA50 影响小（1/50 ≈ 2%），但对 SMA10 不可忽略（1/10 ≈ 10%）。信号日涨 3%，SMA10 被抬高约 0.3%，同时今天的收盘也高于正常 SMA10，双向作弊，降低了趋势判断的门槛。

**修复：** 用 `range(i-10, i)` 和 `range(i-50, i)`，均线只算到昨日。

---

## Bug #3（中）：10 日线反弹类型缺了"反弹确认"条件

```python
# 第 119 行
if sma10[i] > 0 and k['low'] <= sma10[i] * (1 + MA10_PROX):
    ptype = '10ma_bounce'
```

PRD 里写的规则是：
> 今日最低价 ≤ 10日 SMA × 1.02 **且 今日收盘价 > 昨日收盘价**

缺少第二条——没有验证"反弹确认"。如果股价只是阴跌到均线附近就停了（没有反弹），也会被标为 `10ma_bounce`。

**修复：**
```python
yesterday_close = klines[i-1]['close']
if (sma10[i] > 0 and k['low'] <= sma10[i] * (1 + MA10_PROX)
    and close > yesterday_close):
    ptype = '10ma_bounce'
```

---

## Bug #4（低）：`vol_ratio` 可能未初始化

```python
# 第 100 行
vol_ratio = k['volume'] / max_down_vol
# 但如果 has_down=True 且 max_down_vol>0 且 vol>max_down_vol → vol_ratio 定义在 if 分支里
# 如果 has_down=False 且 VOL_FB=False → vol_ratio 可能未赋值
```

代码路径：`has_down=True` → `k['volume'] > max_down_vol` 为 False → `continue` 之前 vol_ratio 已赋值。路径：`has_down=False` 且 `VOL_FB=True` → 在 fallback 分支里赋值。但 `has_down=False` 且 `VOL_FB=False` → `vol_ratio` 未赋值就进入步骤 4。

当前代码里这一路径会走到 `vol_ratio = 0`（因为 else 分支），逻辑上是安全的，但初始化更保险。

**修复：** 在成交量判断块之前加 `vol_ratio = 0`。

---

## 注意 #1（中低）：SMA50 斜率阈值偏严

```python
# 第 83 行
if sma50[i-10] > 0 and (sma50[i] - sma50[i-10]) / sma50[i-10] < SMA50_SLOPE:
```

`SMA50_SLOPE = 0.005`（10 天抬升 0.5%）。50 日均线本身就很平滑——横盘整理期均线几乎走平，0.3% 的微小抬升就很好了。0.5% 的硬门槛会让很多处于蓄势阶段的基部内口袋支点被过滤掉。

**建议：** 降低到 0.002（0.2%），或者改为"斜率 ≥ 0"（只要没有下降趋势）。

**注意：** 这一处没有改动默认值，保留在配置文件里由用户调参。默认值已降为 0.002。

---

## 注意 #2（低）：缺少 `--debug` 和 `--no-rs`

建议和 breakout_scanner 一样加上，方便看过滤漏斗。

**已添加。**

---

## 注意 #3（低）：`PROJECT_DIR` 计算与实际路径不符

脚本在 `src/` 下时，三层 `dirname` 会跑到项目父目录。和 breakout_scanner 一样的问题。

**已修复：** 加自动探测逻辑，优先检测 `data/lixinger.db` 是否存在。

---

## 修复优先级

| 优先级 | 问题 | 修复 |
|---|---|---|
| **P0** | #1 RS 设计调整 | RS 作为输出字段不硬过滤，缺失时填 0 |
| **P1** | #2 SMA 含当天 | `range(i-10,i)` / `range(i-50,i)` |
| **P1** | #3 10 日线反弹缺确认 | 加 `close > yesterday_close` |
| **P2** | #4 vol_ratio 初始化 | 显式 `vol_ratio = 0` |
| **P2** | SMA50 斜率 | 默认值从 0.005 → 0.002 |
| **P3** | 缺 debug | 已添加 `--debug` 和 `--no-rs` |
| **P3** | PROJECT_DIR 路径 | 已自动探测 |
