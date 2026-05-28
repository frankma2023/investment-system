# 项目交接文档

> 欧奈尔 CAN SLIM A股量化投资系统
> 路径：`D:\hanako\investment-system`
> 交接日期：2026-05-28

## 技术栈

Python Flask + SQLite(20G WAL) + 前端原生JS + ECharts 5.5

## 服务端口

| 服务 | 命令 | 端口 |
|------|------|:--:|
| API | `python src/server.py` | 8788 |
| 前端 | `python -m http.server 8772 --directory web` | 8772 |

## 全站导航

```
🏠 看板 | 回测 ▾ | 🔬 指数扫描 | 📈 指数估值 | 💎 个股扫描 | 📊 大盘扫描
```

回测下拉：📉抛盘日 / 📈追盘日 / 📦吸筹日 / 🏆指数RS强度 / 📊指数拥挤度 / 💪个股RS强度 / 🔍机构吸筹出货 / ⚠️指数背离 / ⭐最强指数 / 📐标准突破 / 🎯口袋支点 / 🅱双重底 / 📏扁平基部

## 开发铁律

1. 回测页面参数持久化：YAML ↔ `/api/config` ↔ 前端 ↔ 引擎
2. Python 命令是 `python` 不是 `python3`
3. 文件打开必须 `encoding='utf-8'`
4. 引擎计算结果存表，多页面共享（不重复计算）
5. 新回测看板参照 `docs/dev/回测看板开发标准.md`

## 引擎清单

| 引擎 | 文件 | 配置 YAML |
|------|------|------|
| 抛盘日 | `src/detectors/distribution_day.py` | `config/market/distribution_day.yaml` |
| 追盘日 | `src/detectors/follow_through_day.py` | `config/market/follow_through_day.yaml` |
| 吸筹日 | `src/detectors/accumulation_day.py` | `config/market/accumulation_day.yaml` |
| 指数RS | `src/scanners/index_rs.py` | — |
| 个股RS | `src/scanners/stock_rs.py` | — |
| 指数拥挤度 | `src/scanners/index_crowding.py` | — |
| 指数AD | `src/detectors/index_ad.py` | `config/index_ad.yaml` |
| 指数背离 | `src/detectors/divergence.py` | `config/divergence.yaml` |
| 最强指数 | —（读 `index_rs_daily`） | `config/market/strongest_index.yaml` |
| 标准突破 | `src/scanners/breakout_scanner.py` | `config/market/breakout.yaml` |
| 口袋支点 | `src/scanners/pocket_pivot.py` | `config/market/pocket_pivot.yaml` |
| 双重底 | `src/scanners/double_bottom.py` | `config/market/double_bottom.yaml` |
| 扁平基部 | `src/scanners/flat_base.py` | `config/market/flat_base.yaml` |
| 大盘健康度 | `src/scanners/market_health.py` | — |
| 大盘快照 | `scripts/compute_market_snapshot.py` | — |
| 缠论分析 | `src/scanners/chanlun.py` | `config/chanlun.yaml`(待建) |

## 看板页面

| 页面 | 路径 | 说明 |
|------|------|------|
| 缠论分析 | `/chanlun-backtest/` | 单周期+多周期双模式，中枢/背驰/买卖信号/共振 |
| 全市场形态扫描 | `/daily-pattern-scan/` | 静态HTML表格，客户端分页+筛选 |
| 股票精选回测 | `/discipline/screening-backtest.html` | 精选快照历史回测 |
| 指数精选回测 | `/discipline/screening-backtest-index.html` | 指数版精选回测+得分拆解弹窗 |

## 关键数据表

| 表 | 内容 |
|------|------|
| `daily_kline` | 个股日K线 |
| `index_daily_kline` | 指数日K线 |
| `fundamental_indicator` | 个股基本面(PE/PB/PS/市值等) |
| `stock_rs_daily` | 个股RS(RPS_20/RPS_250) |
| `index_rs_daily` | 指数RS(RS_20/60/120/250+MA+AD) |
| `stock_margin` | 融资融券 |
| `chanlun_bi` | 缠论笔记录 |
| `chanlun_fx` | 缠论分型记录 |
| `chanlun_zs` | 缠论中枢记录 |

## 设计系统

- **hanako-glass.css**：全站统一样式（41个页面共享），`max-width:1200px`，深浅双模式
- **nav.js**：全站统一导航栏，`BACKTEST_ITEMS` + `MAIN_ITEMS` 数组管理，增删页面只改一处
- **页面CSS铁律**：不覆盖 `.app-container`，不自定义全局布局，共享CSS是唯一真相源

## 每日更新

```bash
python scripts/daily_update.py
```
串行 9 步：股票状态 → 指数K线 → 个股K线 → 基本面 → 拥挤度 → 融资融券 → 大盘快照 → 大盘健康度 → 个股RS → 指数RS

## 已知问题

1. 个股RS回测"双强股"定义需修正：应为同时满足稳健龙头 AND 加速爆发，而非 OR
2. stock_rs_daily 历史 RS 数据稀疏（需回填）
3. 8788 端口偶有僵尸进程

## 唤起词

说「阶段收尾」→ 自动：更新进度 + 经验教训 + git commit + 更新导航 + 记录待办
