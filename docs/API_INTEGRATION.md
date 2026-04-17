# 理杏仁 API 对接说明

> 基类：`src/core/base_api.py` — `LixingerBase`

---

## API 基础

- **Base URL**：`https://open.lixinger.com/api/cn`
- **认证方式**：每个请求 body 中带 `token` 字段
- **请求方式**：全部 POST，Content-Type: application/json
- **限流**：36次 / 2秒（代码中保守用 32次/2秒）
- **重试**：3次，间隔2秒（超时和连接错误重试，API业务错误不重试）
- **超时**：30秒
- **Token 配置**：`config/config.yaml` → `LIXINGER_TOKEN`

## 已对接 API 清单

### 个股 API

| API编号 | 模块文件 | 功能 | 数据写入表 | 已实现调度脚本 |
|---------|----------|------|-----------|--------------|
| #1 | `api_stock_company.py` | 股票基础信息 | `stock_basic` | ✅ `download_stock_basic.py` |
| #4 | `api_stock_candlestick.py` | 日K线(OHLCV) | `daily_kline` | ✅ `download_kline_500d.py` + `update_kline_daily.py` |
| #5 | `api_stock_shareholders_num.py` | 股东人数 | `shareholders_num` | ❌ 仅测试 |
| #6 | `api_stock_senior_share_change.py` | 高管增减持 | 无 | ❌ 仅测试 |
| #7 | `api_stock_major_share_change.py` | 大股东增减持 | 无 | ❌ 仅测试 |
| #8 | `api_stock_trading_abnormal.py` | 龙虎榜 | 无 | ❌ 仅测试 |
| #13 | `api_stock_indices.py` | 所属指数 | `stock_index` | ✅ `download_industries_indices.py` |
| #14 | `api_stock_industries.py` | 所属行业 | `stock_industry` + `stock_sw_industry` | ✅ `download_sw_industry.py` + `download_industries_indices.py` |
| #18 | `api_stock_majority_shareholders.py` | 前十大股东 | 无 | ❌ 仅测试 |
| #19 | `api_stock_nolimit_shareholders.py` | 前十大流通股东 | 无 | ❌ 仅测试 |
| #20 | `api_stock_fund_shareholders.py` | 公募基金持股 | 无 | ❌ 仅测试 |
| #22 | `api_stock_dividend.py` | 分红送转 | 无 | ❌ 仅测试 |
| #26 | `api_stock_fundamental.py` | 基本面(PE/PB等) | `fundamental_indicator` | ❌ 仅测试 |
| #27 | `api_stock_fs.py` | 财报数据 | `financial_statement` | ❌ 仅测试 |

### 指数 API

| 模块文件 | 功能 | 数据写入表 | 已实现调度脚本 |
|----------|------|-----------|--------------|
| `api_index_candlestick.py` | 指数日K线(normal/全收益) | `index_daily_kline` | ✅ `download_index_kline.py` |
| `api_index_constituents.py` | 指数成分股 | `index_constituents` | ✅ `download_index_constituents.py` |
| `api_index_constituent_weightings.py` | 成分股权重 | `index_constituent_weightings` | ✅ `download_constituent_weightings.py` |
| `api_index_fundamental.py` | 指数基本面(PE/PB/分位点) | 无 | ❌ 仅测试 |
| `api_index_info.py` | 指数基础信息 | 无 | ❌ 仅测试 |

---

## 未对接但可能需要的 API

- API #2 股票复权因子
- API #3 分时数据
- API #9 股票概念/主题
- API #10 股票公告
- API #11 股票研报
- API #12 股票关联
- API #15 股票可转债
- API #16 股票限售解禁
- API #17 股票定增
- API #21 股票融资融券
- API #23 股票配股
- API #24 股票回购
- API #25 股票业绩预告
- API #28-31 更多财务衍生数据

---

## 批量下载策略

### 个股K线 (`batch_download`)

- **方式**：按日期并发拉取全市场（无需逐只股票请求）
- **并发**：MAX_WORKERS=5
- **限流**：在 `api_stock_candlestick.py` 内部通过 `_request_with_limit` 控制
- **预估耗时**：500个交易日约 25-35 分钟
- **增量更新**：查询 db 最新日期，只下载 new_date+1 到 today

### 指数K线

- **方式**：逐指数请求，1000交易日，normal + total_return
- **限流**：每个指数间 sleep 0.1s
- **总请求**：31 × 2 = 46 次，约 3 秒

### 申万行业（串行）

- **方式**：逐股票请求 IndustriesAPI，筛选 source=sw
- **限流**：32次/2秒（严格串行）
- **预估耗时**：~10分钟
