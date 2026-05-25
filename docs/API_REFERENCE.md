# 后端 API 参考

> 服务器：Flask `http://localhost:8788`
> 更新时间：2026-05-21
> 总端点数：74（Flask 主应用 58 + 知行 Blueprint 16）

---

## 一、知行系统 `/api/discipline/`（16 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/observation` | GET | 观察池列表，`?date=` 查历史 |
| `/lookup-name` | GET | 代码名称查询 |
| `/review/<code>` | GET | 单标的全量复核 |
| `/watchlist` | GET | 自选池列表 |
| `/watchlist` | POST | 从观察池加入自选 |
| `/watchlist/manual` | POST | 手动添加自选 |
| `/watchlist/<code>` | DELETE | 移出自选池 |
| `/precheck` | POST | 买入前 6 项规则检查 |
| `/trades` | GET | 交易列表，`?status=holding\|closed` |
| `/trades` | POST | 录入买入 |
| `/trades/<id>` | GET | 单笔交易详情 |
| `/trades/<id>` | PUT | 录入卖出 |
| `/summary` | GET | 盈亏汇总 |
| `/config` | GET/PUT | 系统配置（总资产等） |
| `/checklist` | GET/PUT | 买入检查清单模板 |
| `/monitor` | GET | 持仓列表（现价/市值/告警灯） |
| `/monitor/scan` | POST | 手动触发扫描 |
| `/monitor/alerts/<id>/acknowledge` | PUT | 标记告警已知晓 |
| `/monitor/price` | PUT | 手工录入当日现价 |

---

## 二、回测看板（22 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/backtest` | POST | 回测运行 |
| `/api/backtest/list` | GET | 回测记录列表 |
| `/api/backtest/save` | POST | 保存回测结果 |
| `/api/backtest/compare` | GET | 多策略对比 |
| `/api/backtest/<id>/signals` | GET | 回测信号明细 |
| `/api/double-bottom` | POST | 双重底回测 |
| `/api/flat-base` | POST | 扁平基部回测 |
| `/api/cup-handle` | GET | 杯柄形态回测 |
| `/api/cup-handle/diag` | GET | 杯柄诊断 |
| `/api/saucer-base` | GET | 碟形基部回测 |
| `/api/saucer-base/scan` | GET | 碟形基部扫描 |
| `/api/base-breakout` | GET | 基部突破回测 |
| `/api/base-breakout/diag` | GET | 诊断信息 |
| `/api/pocket-pivot` | POST | 口袋支点回测 |
| `/api/pocket-pivot-rs` | GET | 口袋支点RS |
| `/api/volume-divergence` | GET | 量价背离回测 |
| `/api/volume-divergence/diag` | GET | 量价背离诊断 |
| `/api/railroad-tracks` | GET | 铁轨线回测 |
| `/api/railroad-tracks/diag` | GET | 铁轨线诊断 |
| `/api/climax-top` | GET | 高潮见顶回测 |
| `/api/climax-top/diag` | GET | 高潮见顶诊断 |
| `/api/top-pattern` | GET | 头部形态回测 |
| `/api/top-pattern/diag` | GET | 头部形态诊断 |
| `/api/breakout-failure` | GET | 突破失败回测 |
| `/api/breakout-failure/diag` | GET | 突破失败诊断 |

---

## 三、大盘环境（5 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/market-health` | GET | 大盘健康度 |
| `/api/market-health/breakouts` | GET | 大盘突破信号 |
| `/api/distribution-day` | GET | 抛盘日分析 |
| `/api/distribution-day/diag` | GET | 抛盘日诊断 |
| `/api/distribution-day/joint` | GET | 多指数联合抛盘日 |

---

## 四、指数分析（8 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/indices` | GET | 指数列表 |
| `/api/index-rs` | GET | 指数RS强度+三级池 |
| `/api/index-constituents` | GET | 指数成分股 |
| `/api/index-ad` | GET | 机构吸筹/出货 |
| `/api/index-divergence` | GET | 指数背离 |
| `/api/strongest-index` | GET | 最强指数 |
| `/api/crowding/latest` | GET | 拥挤度最新 |
| `/api/crowding/indices` | GET | 拥挤度指数列表 |
| `/api/crowding/backtest` | POST | 拥挤度回测 |
| `/api/crowding/config` | GET/POST | 拥挤度配置 |

---

## 五、市场全景（2 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/market-panorama` | GET | 市场全景数据 |
| `/api/market-panorama/compute` | POST | 全景计算 |

---

## 六、个股分析（10 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/kline` | GET | K线数据 |
| `/api/stock-name` | GET | 股票/指数名称查询 |
| `/api/stock-rs` | GET | 个股RS强度 |
| `/api/stock-rs/double-strong` | GET | 双强股列表 |
| `/api/stock-rs/rs-line` | GET | RS曲线数据 |
| `/api/stock-analysis` | GET | DCF+可比+盈利+三表 |
| `/api/stock-valuation` | GET | 估值指标（PE/PB/PS/股息率/市值）|
| `/api/stock-financials` | GET | 年度财务数据+负债结构 |
| `/api/quarterly-fcf` | GET | 季度自由现金流（单季拆分）|
| `/api/fundamental-deterioration` | GET | 基本面恶化检测 |

---

## 七、形态识别（1 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/pattern-scan` | GET | 全引擎统一形态扫描 |

---

## 八、估值 & CANSLIM（2 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/canslim-score` | GET/POST | CANSLIM 单只评分 |
| `/api/canslim-scores` | GET | 全市场CANSLIM评分 |

---

## 九、基础设施（3 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET/POST | 通用配置读写 |
| `/api/valuation` | GET | 估值分析 |
| `/api/valuation/fs` | GET | 估值-财报 |
| `/<path:subpath>` | GET | 静态文件服务（web/ 目录）|
