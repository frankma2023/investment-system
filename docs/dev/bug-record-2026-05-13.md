# 形态识别看板 — Bug 记录

> 日期：2026-05-13  
> 来源：前端页面联调 + 数据验证中发现

---

## Bug 1：`_sanitize_indicators` 截取方向错误（严重）

**影响范围**：`/api/pattern-scan` 返回的全部技术指标（BB 上中下轨、SMA 全系列、RSI、MACD、ATR、VOL_MA50）

**文件**：`src/server.py` → `_sanitize_indicators()`

**现象**：K 线图上布林带数值与同花顺/东方财富等外部软件相差近一倍。以 002648（卫星化学）2026-05-13 为例：

| 指标 | 外部软件 | 修复前（错位） | 修复后 |
|------|---------|---------------|--------|
| BB 上轨 | 30.25 | ~20.25 | 30.37 |
| BB 中轨 | 27.98 | ~18.30 | 27.98 |
| BB 下轨 | 25.63 | ~16.30 | 25.60 |

**根因**：

```python
# 修复前
else:
    arr = arr[:target_len]   # 取头部 → 与 klines_out（尾部）错位
```

`api_pattern_scan()` 的工作流：
1. 从数据库取完整历史 K 线（含 start 前 ~750 天）→ 计算全部 TA-Lib 指标
2. 按 `date >= start` 过滤 → 只保留尾部
3. `_sanitize_indicators` 应取指标数组的**尾部**与 K 线对齐，但取了**头部**

导致所有指标值偏移 600+ 天，显示的是两年前的历史值。

**修复**：

```python
# 修复后
else:
    arr = arr[-target_len:]   # 取尾部 → 与 klines_out 对齐
```

---

## Bug 2：`bb_squeeze` 百分位方向反转（中等）

**影响范围**：所有历史 `bb_squeeze`（布林带带宽收缩）信号

**文件**：`src/scanners/talib_engine.py` 第 199 行

**现象**：002929（润建股份）2026-05-13 触发 `bb_squeeze` 信号，描述为"布林带带宽收缩至历史低位，可能酝酿大幅波动"。但从 K 线图观察，布林带上轨和下轨呈喇叭口状**持续放大**，与信号描述完全相反。

当日 BB 宽度 = 60.75%，近 10 天最高值；真正最窄出现在 05-06（32.90%）。

**根因**：

```python
# 修复前（错误）
pct_rank = sum(1 for w in widths_sorted if w > current_width) / len(widths)
```

这段代码统计"有多少历史宽度**大于**当前宽度"：
- 当前宽度 60.75%（极大）→ 几乎没有历史宽度大于它 → `pct_rank ≈ 0.0 < 0.10` → **误触发**
- 当前宽度 10%（极窄）→ 大量历史宽度大于它 → `pct_rank` 很大 → **不触发**

逻辑与预期完全相反——信号实际触发在 BB **扩张**时。

**修复**：

```python
# 修复后（正确）
pct_rank = sum(1 for w in widths_sorted if w < current_width) / len(widths)
```

统计"有多少历史宽度**小于**当前宽度"。当前宽度越窄，满足条件的越少，`pct_rank < 0.10` 才触发"收缩至历史低位"信号。

**影响**：修复后，所有历史的 `bb_squeeze` 信号需重新生成。之前触发该信号的日期实际处于 BB 扩张阶段，信号不可信。

---

## Bug 3：`flat_base.py` BB 宽度百分位方向反转（中等）

**影响范围**：`flat_base.py` 中所有 BB 带宽收缩检查

**文件**：`src/scanners/flat_base.py` 第 98 行

**根因**：与 Bug 2 完全相同。

```python
# 修复前（错误）
better = sum(1 for h in bb_history[...] if h > bb_w)
```

统计"有多少历史宽度大于当前宽度"——当前宽度越窄，满足条件的越多 → `bb_p` 越大 → `bb_ok = False` → **窄 BB 被拒绝，宽 BB 通过**。与设计意图完全相反。

意图是：BB 收窄到历史低位 → 扁平基部形成 → 通过过滤。但代码实际行为：BB 越窄越不过。

**修复**：

```python
# 修复后（正确）
better = sum(1 for h in bb_history[...] if h < bb_w)
```

**影响**：修复后，`flat_base` 引擎才能正确识别 BB 收窄的扁平基部。此前该条件实际反向工作，可能漏掉了真正扁平基部，误收了高波动横盘。

---

## 变更清单

| 文件 | 改动 | 行号 |
|------|------|------|
| `src/server.py` | `_sanitize_indicators`: `arr[:target_len]` → `arr[-target_len:]` | ~2055 |
| `src/scanners/talib_engine.py` | `bb_squeeze` 百分位: `w > current_width` → `w < current_width` | 200 |
| `src/scanners/flat_base.py` | BB 宽度百分位: `h > bb_w` → `h < bb_w` | 98 |
