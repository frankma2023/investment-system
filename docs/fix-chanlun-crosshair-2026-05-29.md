# chanlun-backtest 十字线修复报告

> 日期：2026-05-29  
> 页面：`http://localhost:8772/chanlun-backtest/`  
> 后端：`src/scanners/chanlun.py` → `get_echarts_option()`

## 问题

K线图的十字线（crosshair）没有贯穿到成交量副图；修复贯穿后，又出现十字线在两个轴上指向不同日期（K线指向 03-11，成交量指向 03-20）。

## 排查过程

### 第一轮：轴线不贯穿

**现象**：鼠标在 K 线主图上移动时，十字线仅显示在主图区域，成交量副图无十字线。

**排查**：检查后端 `get_echarts_option()` 中 tooltip 的 `axisPointer` 配置：

```python
# chanlun.py 第803行（修复前）
"axisPointer": {"type": "cross", "crossStyle": {"color": axis_color},
                "link": [{"xAxisIndex": "all"}]},
```

`xAxisIndex: "all"` 是字符串，ECharts 5 中该字段仅接受数字数组 `[0, 1]`，字符串 `"all"` 被忽略。

**修复**：

```python
"link": [{"xAxisIndex": [0, 1]}]
```

### 第二轮：仍然不贯穿

**现象**：修改后用户反馈"还是没有生效"。

**排查**：

1. 直接调用 API 验证返回的 option：
```
curl -s "http://localhost:8788/api/chanlun/echarts?code=000985&freq=D&limit=5"
```
返回的 `tooltip.axisPointer.link` 已正确变为 `[{"xAxisIndex": [0, 1]}]`。

2. 检查是否缺少 option 顶层的 `axisPointer` 配置——ECharts 中，tooltip 内的 `link` 只影响 tooltip 触发时的 axisPointer 行为；全局 axisPointer 联动需要在 option 顶层也声明。

```python
# chanlun.py 第798行 return 语句中（缺失）
"axisPointer": {"link": [{"xAxisIndex": [0, 1]}]},
```

**修复**：在 option 顶层添加 `axisPointer` 配置。

3. Flask 进程（PID 37220）以管理员权限运行，无法通过 `taskkill` 远程重启。顶层 `axisPointer` 修改未能加载。

> 用户手动重启 Flask 后，底层 `link` 修改生效，十字线成功贯穿。

### 第三轮：贯穿但日期不对齐

**现象**：十字线贯穿了，但 K 线主图指向 03-11 时，成交量副图指向 03-20——两个轴的日期偏移了约 9 个交易日。

**排查**：

1. 确认两个 xAxis 使用相同的 `dates` 数组（日线模式下 `ohlc_df = df.copy()`，数据完全一致）。

2. 检查 `dataZoom` 配置：

```python
# chanlun.py 第832行（修复前）
"dataZoom": [
    {"type": "inside", "start": 70, "end": 100},
    {"type": "slider", "start": 70, "end": 100, "height": 16, "bottom": 4}
]
```

**`dataZoom` 未指定 `xAxisIndex`**。在 ECharts 中，不指定时默认只作用于第一个 `xAxis`（K 线主图）。当用户拖动滑块或使用滚轮缩放时，仅主图的 xAxis 范围发生变化，成交量副图的 xAxis 保持原范围。两个轴的可见数据窗口不同步，导致十字线（通过索引联动）在两个轴上指向不同日期。

**修复**：

```python
"dataZoom": [
    {"type": "inside",  "xAxisIndex": [0, 1], "start": 70, "end": 100},
    {"type": "slider",  "xAxisIndex": [0, 1], "start": 70, "end": 100, "height": 16, "bottom": 4}
]
```

## 根因总结

| 问题 | 根因 | 位置 |
|------|------|------|
| 十字线不贯穿 | `axisPointer.link.xAxisIndex` 使用了 ECharts 5 不支持的字符串 `"all"` | `tooltip.axisPointer.link` |
| 全局联动缺失 | option 顶层缺少 `axisPointer.link` 配置 | option 顶层 |
| 日期不对齐 | `dataZoom` 未指定 `xAxisIndex`，默认只缩放第一个 xAxis | `dataZoom[0]`、`dataZoom[1]` |

## 涉及文件

| 文件 | 修改内容 |
|------|---------|
| `src/scanners/chanlun.py` | `tooltip.axisPointer.link` 的 `xAxisIndex` 从 `"all"` 改为 `[0, 1]` |
| `src/scanners/chanlun.py` | option 顶层添加 `"axisPointer": {"link": [{"xAxisIndex": [0, 1]}]}` |
| `src/scanners/chanlun.py` | `dataZoom` 两个控件添加 `"xAxisIndex": [0, 1]` |

## 经验教训

1. **ECharts 5 类型严格**：`axisPointer.link.xAxisIndex` 不接受字符串 `"all"`，必须用数字数组 `[0, 1]`
2. **多层 axisPointer**：tooltip 内的 `link` + option 顶层的 `link` 都需要配置，分别控制 tooltip 触发和全局联动
3. **dataZoom 与多 grid**：多 grid 场景下，`dataZoom` 必须显式指定 `xAxisIndex` 覆盖所有轴，否则缩放不同步
4. **Flask 进程权限**：以管理员权限启动的 Flask 无法通过普通用户 `taskkill` 终止，需在启动终端手动重启
