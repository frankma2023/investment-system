# 数据库表结构

> 引擎：SQLite，WAL 模式，PRAGMA synchronous=NORMAL

---

## 1. stock_basic — 股票基础信息

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK**，股票代码，如 `300750` |
| name | TEXT | 股票名称 |
| market | TEXT | 市场，`a`=A股 |
| exchange | TEXT | 交易所，`sh`/`sz`/`bj` |
| area_code | TEXT | 地区代码 |
| listing_status | TEXT | 上市状态，`normally_listed`/`delisted`/... |
| ipo_date | TEXT | 上市日期 |
| delisted_date | TEXT | 退市日期（可空） |
| fs_table_type | TEXT | 财报类型，`non_financial`/`bank`/`insurance`/... |
| mutual_market_flag | INTEGER | 是否陆股通标的，0/1 |
| updated_at | TEXT | 更新时间 |

**数据量**：~5595 条
**数据来源**：理杏仁 API #1 股票信息
**写入脚本**：`scheduler/download_stock_basic.py`
**读取场景**：获取股票名称、上市天数筛选、排除ST

---

## 2. daily_kline — 个股日K线

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)**，股票代码 |
| date | TEXT | **PK(2)**，交易日期 YYYY-MM-DD |
| open | REAL | 开盘价 |
| close | REAL | 收盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| volume | INTEGER | 成交量 |
| amount | REAL | 成交额 |
| change_pct | REAL | 涨跌幅(%) |
| turnover_rate | REAL | 换手率 |
| complex_factor | REAL | 复权因子 |

**数据量**：~304万条
**索引**：`idx_daily_kline_date(date)`, `idx_daily_kline_stock(stock_code)`
**数据来源**：理杏仁 API #4 K线数据
**写入脚本**：
- 首次全量：`scheduler/download_kline_500d.py`
- 每日增量：`scheduler/update_kline_daily.py`
**读取场景**：RS计算、技术指标计算、内部共振验证

---

## 3. stock_industry — 所属行业（多源）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)** |
| industry_code | TEXT | **PK(2)** |
| industry_name | TEXT | 行业名称 |
| source | TEXT | **PK(3)**，来源：`sw`/`sw_2021`/`cni`/... |
| updated_at | TEXT | 更新时间 |

**数据量**：~17141 条
**数据来源**：理杏仁 API #14 所属行业
**写入脚本**：`scheduler/download_industries_indices.py`
**读取场景**：获取股票行业分类

---

## 4. stock_index — 所属指数

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)** |
| index_code | TEXT | **PK(2)** |
| index_name | TEXT | 指数名称 |
| source | TEXT | 来源：`csi`/`cni`/`hsi`/`usi`/`lxri` |
| updated_at | TEXT | 更新时间 |

**数据量**：~19865 条
**数据来源**：理杏仁 API #13 所属指数
**写入脚本**：`scheduler/download_industries_indices.py`
**读取场景**：确认股票所属指数

---

## 5. stock_sw_industry — 申万一级行业映射

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK**，股票代码 |
| industry_name | TEXT | 申万一级行业名称，如"电子"、"食品饮料" |
| industry_code | TEXT | 申万一级行业指数代码，如 `931494` |
| updated_at | TEXT | 更新时间 |

**数据量**：~5500 条
**数据来源**：理杏仁 API #14 所属行业（筛选 source=sw）
**写入脚本**：`scheduler/download_sw_industry.py`
**读取场景**：
- `IndustryMapper.load_from_db()` 读取，结合 `rs_config.yaml` 的 `industry_index_map` 生成股票→中证行业指数映射
- 个股RS计算时用于匹配行业基准
- ⚠️ **注意**：不存在 `sw_industry` 或 `stock_sw_industry_list` 表，就是这张表

---

## 6. fundamental_indicator — 基本面指标（key-value）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)** |
| date | TEXT | **PK(2)** |
| metric_code | TEXT | **PK(3)**，如 `pe_ttm`/`pb`/`mc`/`pe_ttm.y3.cvpos` |
| value | REAL | 指标值 |

**数据量**：~15 条（仅测试数据）
**索引**：`idx_fundamental_stock_date(stock_code, date)`, `idx_fundamental_metric(metric_code)`
**数据来源**：理杏仁 API #26 基本面数据
**写入脚本**：`DBManager.upsert_fundamental()`
**设计说明**：key-value 结构，指标由 API 的 `metricsList` 参数动态决定

---

## 7. financial_statement — 财报数据（key-value）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)** |
| report_date | TEXT | **PK(2)**，财报日期 |
| announce_date | TEXT | 公告日期 |
| metric_code | TEXT | **PK(3)**，如 `q.ps.toi.t`/`q.bs.ta.t`/`q.m.roe.t` |
| value | REAL | 指标值 |

**数据量**：~10 条（仅测试数据）
**索引**：`idx_financial_stock_date(stock_code, report_date)`, `idx_financial_metric(metric_code)`
**数据来源**：理杏仁 API #27 财报数据
**写入脚本**：`DBManager.upsert_financial()`
**metric_code 编码规则**：`[粒度].[报表].[字段].[计算类型]`
- 粒度：q(季度), hy(半年), y(年)
- 报表：bs(资产负债表), ps(利润表), cf(现金流量表), m(财务指标)
- 计算类型：t(当期), c(单季), ttm, t_y2y(同比), c_y2y(单季同比)

---

## 8. shareholders_num — 股东人数

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)** |
| date | TEXT | **PK(2)** |
| total | INTEGER | 股东人数 |
| change_rate | REAL | 变化比例 |
| price_change | REAL | 股价涨跌幅 |

**数据量**：~4 条（仅测试数据）
**数据来源**：理杏仁 API #5 股东人数
**写入脚本**：`DBManager.upsert_shareholders_num()`

---

## 9. index_daily_kline — 指数日K线

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)**，指数代码 |
| date | TEXT | **PK(2)**，交易日期 |
| kline_type | TEXT | **PK(3)**，`normal`(正常点位)/`total_return`(全收益点位) |
| open | REAL | 开盘价 |
| close | REAL | 收盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| volume | INTEGER | 成交量 |
| amount | REAL | 成交额 |
| change | REAL | 涨跌幅(%) |

**数据量**：~61183 条（31个指数 × 1000天 × 2种点位）
**数据来源**：理杏仁指数K线API
**写入脚本**：
- 首次全量：`scheduler/download_index_kline.py`（1000交易日）
- 每日更新：`scheduler/update_index_kline_daily.py`（与 download_index_kline.py 代码相同）
**读取场景**：RS计算的行业/市场基准、行业技术指标(MA200/涨跌幅/成交量)

---

## 10. index_constituents — 指数成分股

| 字段名 | 类型 | 说明 |
|--------|------|------|
| index_code | TEXT | **PK(1)**，指数代码 |
| stock_code | TEXT | **PK(2)**，成分股代码 |
| date | TEXT | **PK(3)**，成分股生效日期 |
| updated_at | TEXT | 更新时间 |

**数据量**：~13624 条
**索引**：`idx_idx_const_idx(index_code)`, `idx_idx_const_stock(stock_code)`, `idx_idx_const_date(date)`
**数据来源**：理杏仁指数成分股API
**写入脚本**：`scheduler/download_index_constituents.py`
**读取场景**：
- 行业RS v3.0：构建 `{stock_code: industry_index_code}` 映射
- 内部共振验证：获取行业成分股列表
- `DataFetcher.load_constituents()` 和 `DataFetcher.load_constituent_rs_median()`

---

## 11. index_constituent_weightings — 指数成分股权重

| 字段名 | 类型 | 说明 |
|--------|------|------|
| index_code | TEXT | **PK(1)** |
| stock_code | TEXT | **PK(2)** |
| date | TEXT | **PK(3)** |
| weighting | REAL | 权重比例 |
| updated_at | TEXT | 更新时间 |

**数据量**：~310 条
**索引**：`idx_icw_index(index_code)`, `idx_icw_stock(stock_code)`
**数据来源**：理杏仁成分股权重API
**写入脚本**：`scheduler/download_constituent_weightings.py`
**读取场景**：`DataFetcher.load_constituents()` 优先使用权重排序取 top_n 成分股

---

## 12. rs_daily — 个股RS每日计算结果

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)** |
| date | TEXT | **PK(2)**，YYYY-MM-DD |
| industry_code | TEXT | 行业指数代码（来自 stock_sw_industry + rs_config.yaml 映射） |
| industry_name | TEXT | 行业名称 |
| rs_mkt_long | REAL | 相对市场长期 RPS (250日)，0-99 |
| rs_mkt_mid | REAL | 相对市场中期 RPS (120日)，0-99 |
| rs_mkt_short | REAL | 相对市场短期 RPS (20日)，0-99 |
| rs_ind_long | REAL | 相对行业长期 RPS (250日)，0-99 |
| rs_ind_mid | REAL | 相对行业中期 RPS (120日)，0-99 |
| rs_ind_short | REAL | 相对行业短期 RPS (20日)，0-99 |
| pattern | TEXT | 双强模式：`Steady Leader`/`Accelerating`/NULL |
| long_days | INTEGER | 长期周期天数（配置值，默认250） |
| mid_days | INTEGER | 中期周期天数（配置值，默认120） |
| short_days | INTEGER | 短期周期天数（配置值，默认20） |
| updated_at | TEXT | 更新时间 |

**数据量**：~173865 条
**写入脚本**：`scheduler/daily_rs_calculation.py`
**计算引擎**：`src/strategies/rs_engine.py` → `RSEngine.calculate_all()`
**读取场景**：
- 行业RS v3.0：`DataFetcher.load_constituent_rs_median()` 聚合为行业RS中位数
- CSV 导出：`output/rs_daily_YYYYMMDD.csv` + `output/double_strong_YYYYMMDD.csv`
- Web 看板 API

---

## 13. sector_rs_daily — 行业板块RS每日结果

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | PK, 自增 |
| date | TEXT | 计算日期 YYYY-MM-DD |
| sector_code | TEXT | 行业指数代码 |
| sector_name | TEXT | 行业名称 |
| rs_ratio | REAL | RS Ratio（行业指数收盘 / 基准指数收盘） |
| score_20 | REAL | 20日动量得分(%) |
| score_120 | REAL | 120日动量得分(%) |
| score_250 | REAL | 250日动量得分(%) |
| rps_20 | INTEGER | 20日 RPS 排名（成分股RS中位数排名） |
| rps_120 | INTEGER | 120日 RPS 排名 |
| rps_250 | INTEGER | 250日 RPS 排名 |
| price_vs_ma200 | REAL | 收盘价/MA200 |
| ma200_trend | TEXT | MA200 趋势：UP/DOWN |
| daily_change_pct | REAL | 当日涨跌幅(%) |
| vol_ratio_20 | REAL | 当日成交量/20日均量 |
| vol_ratio_5 | REAL | 当日成交量/5日均量 |
| rs20_trend_up | INTEGER | 近20日 RPS 趋势是否上升，1/0/NULL |
| is_leading | INTEGER | L1 绝对强势池，1/0 |
| is_momentum | INTEGER | L2 短期爆发池，1/0 |
| is_setup | INTEGER | L3 潜在共振池，1/0 |
| is_compact | INTEGER | 紧凑整理形态，1/0 |
| internal_status | TEXT | 内部共振状态：高置信度领涨/中等置信度/弱势领涨/无共振/成分股缺失 |
| internal_count | INTEGER | 通过共振验证的个股数 |
| internal_weighted | REAL | 通过个股的权重占比 |
| top_stocks | TEXT | Top5 通过个股的 JSON（code/weighting/signal） |
| created_at | TEXT | 创建时间 |

**数据量**：~960 条
**UNIQUE**：`(date, sector_code)`
**索引**：`idx_srs_date(date)`, `idx_srs_leading(date, is_leading)`, `idx_srs_momentum(date, is_momentum)`
**写入脚本**：`scheduler/run_sector_rs.py`
**计算引擎**：`src/strategies/sector_rs/` 模块
- `data_fetcher.py` → 加载数据
- `filter.py` → 三层筛选
- `internal_check.py` → 内部共振验证
- `output_writer.py` → CSV + DB
**读取场景**：CSV 导出 `output/sector_rs_report_YYYYMMDD.csv`、Web 看板

---

## 14. market_direction_daily — 大盘方向每日分析

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | **PK**，自增 |
| date | TEXT | 计算日期 YYYY-MM-DD |
| market_phase | TEXT | 市场阶段：Confirmed Rally/Uptrend Under Pressure/Correction/Downtrend |
| market_phase_confidence | TEXT | 阶段置信度 |
| risk_level | TEXT | 风险等级 |
| suggested_position_size | REAL | 建议仓位比例 |
| distribution_days_25d | INTEGER | 近25日抛盘日数 |
| distribution_days_10d | INTEGER | 近10日抛盘日数 |
| distribution_trend | TEXT | 抛盘日趋势 |
| distribution_warning | INTEGER | 抛盘日预警，0/1 |
| ftd_exists | INTEGER | 是否存在追盘日，0/1 |
| ftd_date | TEXT | 追盘日日期 |
| ftd_day_count | INTEGER | 追盘日第N天 |
| ftd_index_code | TEXT | 追盘日指数代码 |
| ftd_index_name | TEXT | 追盘日指数名称 |
| ftd_gain_pct | REAL | 追盘日涨幅(%) |
| ftd_volume_ratio | REAL | 追盘日量比 |
| accumulation_days_10d | INTEGER | 近10日吸筹日数 |
| standard_accumulation | INTEGER | 标准吸筹日数 |
| special_accumulation | INTEGER | 特殊吸筹日数 |
| breakout_accumulation | INTEGER | 突破吸筹日数 |
| accumulation_vs_distribution | REAL | 吸筹/抛盘比 |
| divergence_pattern | TEXT | 分歧形态 |
| style_divergence | TEXT | 风格分歧 |
| sector_rotation_summary | TEXT | 板块轮动摘要(JSON) |
| leading_index_code | TEXT | 最强指数代码 |
| leading_index_name | TEXT | 最强指数名称 |
| leading_index_rs | INTEGER | 最强指数RS值 |
| top_indices | TEXT | Top指数排名(JSON) |
| market_health_score | INTEGER | 市场健康度评分(0-100) |
| health_score_components | TEXT | 健康度分项(JSON) |
| advance_decline_ratio | REAL | 涨跌比 |
| new_high_new_low_ratio | REAL | 新高新低比 |
| above_ma50_ratio | REAL | MA50上方个股占比 |
| summary | TEXT | 总结 |
| action_suggestion | TEXT | 操作建议 |
| warnings | TEXT | 风险提示(JSON) |
| focus | TEXT | 关注方向 |
| avoid | TEXT | 回避方向 |
| stop_loss | TEXT | 止损建议 |
| strengths | TEXT | 优势(JSON) |
| weaknesses | TEXT | 劣势(JSON) |
| opportunities | TEXT | 机会(JSON) |
| risks | TEXT | 风险(JSON) |
| created_at | TEXT | 创建时间 |

**写入脚本**：`scheduler/run_market_direction.py`
**计算引擎**：`src/strategies/market_direction/`
**读取场景**：Web 看板（大盘扫描页）

---

## 15. distribution_days_detail — 抛盘日明细

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | **PK**，自增 |
| date | TEXT | 日期 |
| index_code | TEXT | 指数代码 |
| index_name | TEXT | 指数名称 |
| close | REAL | 收盘价 |
| change_pct | REAL | 涨跌幅(%) |
| volume | INTEGER | 成交量 |
| prev_volume | INTEGER | 前日成交量 |
| volume_ratio | REAL | 量比 |
| is_distribution | INTEGER | 是否抛盘日，0/1 |
| distribution_type | TEXT | 抛盘日类型 |
| decline_threshold_used | REAL | 使用的跌幅阈值 |
| market_phase_at_date | TEXT | 当日市场阶段 |
| is_high_position | INTEGER | 是否高位，0/1 |
| created_at | TEXT | 创建时间 |

**写入脚本**：`scheduler/run_market_direction.py`
**读取场景**：大盘方向分析

---

## 16. follow_through_days — 追盘日

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | **PK**，自增 |
| ftd_date | TEXT | 追盘日日期 |
| low_point_date | TEXT | 低点日期 |
| low_point_value | REAL | 低点值 |
| day_count | INTEGER | 低点后第N天 |
| index_code | TEXT | 指数代码 |
| index_name | TEXT | 指数名称 |
| close | REAL | 收盘价 |
| gain_pct | REAL | 涨幅(%) |
| volume | INTEGER | 成交量 |
| prev_volume | INTEGER | 前日成交量 |
| volume_ratio | REAL | 量比 |
| is_valid | INTEGER | 是否仍有效，0/1 |
| invalidated_date | TEXT | 失效日期 |
| invalidated_reason | TEXT | 失效原因 |
| follow_up_5d_return | REAL | 后5日收益(%) |
| follow_up_20d_return | REAL | 后20日收益(%) |
| created_at | TEXT | 创建时间 |

**写入脚本**：`scheduler/run_market_direction.py`
**读取场景**：大盘方向分析

---

## 17. accumulation_days_detail — 吸筹日明细

| 字段名 | 类型 | 说明 |
|--------|------|------|
| date | TEXT | **PK(1)**，日期 |
| index_code | TEXT | **PK(2)**，指数代码 |
| index_name | TEXT | 指数名称 |
| close | REAL | 收盘价 |
| change_pct | REAL | 涨跌幅(%) |
| volume | INTEGER | 成交量 |
| prev_volume | INTEGER | 前日成交量 |
| volume_ratio | REAL | 量比 |
| amplitude | REAL | 振幅 |
| close_position | REAL | 收盘位置(0-1) |
| is_accumulation | INTEGER | 是否吸筹日，0/1 |
| is_standard_acc | INTEGER | 标准吸筹日，0/1 |
| is_special_acc | INTEGER | 特殊吸筹日，0/1 |
| is_breakout_acc | INTEGER | 突破吸筹日，0/1 |
| accumulation_type | TEXT | 吸筹日类型 |
| created_at | TEXT | 创建时间 |

**UNIQUE**：`(date, index_code)`
**写入脚本**：`scheduler/run_market_direction.py`
**读取场景**：大盘方向分析

---

## 18. buy_signals_daily — 每日买点信号

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | **PK**，自增 |
| date | TEXT | 信号日期 |
| stock_code | TEXT | 股票代码 |
| stock_name | TEXT | 股票名称 |
| signal_type | TEXT | 信号类型 |
| subtype | TEXT | 信号子类型 |
| entry_price | REAL | 入场价 |
| entry_price_high | REAL | 入场价(最高) |
| stop_loss_price | REAL | 止损价 |
| target_price | REAL | 目标价 |
| confidence | TEXT | 置信度 |
| strength_score | INTEGER | 强度评分 |
| suggested_position_pct | REAL | 建议仓位 |
| details_json | TEXT | 信号详情(JSON) |
| created_at | TEXT | 创建时间 |

**写入脚本**：`canslim_pro/screener.py`
**读取场景**：CANSLIM 看板

---

## 19. sector_internal_strength — 行业内部强度明细

| 字段名 | 类型 | 说明 |
|--------|------|------|
| date | TEXT | **PK(1)**，日期 |
| sector_code | TEXT | **PK(2)**，行业代码 |
| sector_name | TEXT | 行业名称 |
| constituent_count | INTEGER | 成分股数量 |
| rs_mean_20 | REAL | 20日RS均值 |
| rs_mean_120 | REAL | 120日RS均值 |
| rs_mean_250 | REAL | 250日RS均值 |
| rs_std_120 | REAL | 120日RS标准差 |
| above_ma50_count | INTEGER | MA50上方个股数 |
| above_ma200_count | INTEGER | MA200上方个股数 |
| bull_alignment_count | INTEGER | 多头排列个股数 |
| volume_surge_count | INTEGER | 放量个股数 |
| breakout_count | INTEGER | 突破个股数 |
| breakout_stocks | TEXT | 突破个股列表(JSON) |
| fund_flow_intensity | REAL | 资金流强度 |
| strong_ratio | REAL | 强势股占比 |
| above_ma50_ratio | REAL | MA50上方占比 |
| rs_dist_score | REAL | RS分布得分 |
| trend_score | REAL | 趋势得分 |
| money_flow_score | REAL | 资金流得分 |
| resonance_score | REAL | 共振得分 |

**UNIQUE**：`(date, sector_code)`
**写入脚本**：`scheduler/run_sector_rs.py`
**读取场景**：行业扫描

---

## 20. sector_rotation — 行业轮动记录

| 字段名 | 类型 | 说明 |
|--------|------|------|
| date | TEXT | **PK(1)**，日期 |
| sector_code | TEXT | **PK(2)**，行业代码 |
| sector_name | TEXT | 行业名称 |
| momentum_delta_5d | REAL | 5日动量变化 |
| rps_delta_5d | REAL | 5日RPS变化 |
| rotation_signal | TEXT | 轮动信号 |

**UNIQUE**：`(date, sector_code)`
**写入脚本**：`scheduler/run_sector_rs.py`
**读取场景**：行业扫描

---

## 21. stock_margin — 融资融券数据

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT PK | 股票代码 |
| date | TEXT PK | 日期 |
| mtaslb | REAL | 融资融券余额 |
| mtaslb_fb | REAL | 融资余额 |
| mtaslb_sb | REAL | 融券余额 |
| mtaslb_mc_r | REAL | 融资买入额 |
| npa_o_f_d1~d240 | REAL | 1/5/10/20/60/120/240日净买入额 |
| fb_mc_rc_d1~d240 | REAL | 1/5/10/20/60/120/240日融资偿还率 |

## 22. shareholders_num_v2 — 股东人数V2

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT PK | 股票代码 |
| date | TEXT PK | 日期 |
| shnc_rln | INTEGER | 最新股东人数 |
| shnc_d10~d90 | REAL | 10/20/30/60/90日变化率 |
| shnc_qln | REAL | 上期股东人数 |
| shnc_q1~q3 | REAL | 1/2/3季度变化 |
| shnc_y1~y2 | REAL | 1/2年变化 |

## 23. stock_candidates_daily — 个股扫描每日结果

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT PK | 股票代码 |
| date | TEXT PK | 日期 |
| stock_name | TEXT | 股票名称 |
| industry_name | TEXT | 行业 |
| rs_score | REAL | RS维度评分 |
| rs_mkt_long | REAL | 原始RS值 |
| fundamental_score | REAL | 基本面维度评分 |
| eps_ttm, eps_yoy, revenue_yoy, roe, debt_ratio | REAL | 基本面指标 |
| vol_price_score | REAL | 量价维度评分 |
| price_vs_ma50, price_vs_ma200, dist_from_high | REAL | 量价指标 |
| avg_volume_20d | REAL | 20日均量 |
| volume_trend, ma_trend | TEXT | 趋势描述 |
| pattern_score | REAL | 形态维度评分 |
| pattern_health, pattern_type | TEXT | 形态分析 |
| composite_score | REAL | 综合评分 |
| grade | TEXT | 等级(A/B/C/D) |
| is_watchlist | INTEGER | 是否自选 |

## 24. watchlist — 自选股

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT PK | 股票代码 |
| stock_name | TEXT | 股票名称 |
| added_at | TEXT | 添加时间 |
| removed_at | TEXT | 移除时间(NULL=有效) |
| note | TEXT | 备注 |

---

## 25. canslim_quarterly_eps — CANSLIM季度EPS

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)**，股票代码 |
| report_date | TEXT | **PK(2)**，财报日期 |
| eps_basic | REAL | 基本每股收益 |
| eps_diluted | REAL | 稀释每股收益 |
| revenue_yoy | REAL | 营收同比增长率(%) |
| net_profit_yoy | REAL | 净利润同比增长率(%) |
| np_atoopc_yoy | REAL | 归母净利润同比增长率(%) |
| updated_at | TEXT | 更新时间 |

**写入脚本**：`scheduler/canslim_fetch_eps.py`
**读取场景**：CANSLIM 看板（C季度盈利、A年度盈利判断）

---

## 26. canslim_annual_eps — CANSLIM年度EPS

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)**，股票代码 |
| report_date | TEXT | **PK(2)**，财报日期 |
| eps_basic | REAL | 基本每股收益 |
| eps_diluted | REAL | 稀释每股收益 |
| revenue | REAL | 营收 |
| net_profit | REAL | 净利润 |
| roe | REAL | 净资产收益率(%) |
| updated_at | TEXT | 更新时间 |

**写入脚本**：`scheduler/canslim_fetch_eps.py`、`scheduler/canslim_backfill_annual_eps.py`
**读取场景**：CANSLIM 看板（A年度盈利判断）

---

## 27. canslim_institutional — CANSLIM基金持股

| 字段名 | 类型 | 说明 |
|--------|------|------|
| stock_code | TEXT | **PK(1)**，股票代码 |
| report_date | TEXT | **PK(2)**，财报日期 |
| fund_count | INTEGER | 持股基金数 |
| total_holdings | REAL | 持股总量 |
| total_market_cap | REAL | 持股市值 |
| total_share_pct | REAL | 占总股本比例(%) |
| updated_at | TEXT | 更新时间 |

**写入脚本**：`scheduler/canslim_fetch_institutional.py`
**读取场景**：CANSLIM 看板（I机构认同判断）

---

## 28. canslim_scores — CANSLIM七维度评分

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INTEGER | **PK**，自增 |
| date | TEXT | 筛选日期 |
| stock_code | TEXT | 股票代码 |
| stock_name | TEXT | 股票名称 |
| total_score | INTEGER | 总分 |
| pass_count | INTEGER | 通过维度数 |
| C_score | INTEGER | C(季度盈利)得分 |
| C_pass | INTEGER | C是否通过，0/1 |
| C_detail | TEXT | C详情(JSON) |
| A_score | INTEGER | A(年度盈利)得分 |
| A_pass | INTEGER | A是否通过，0/1 |
| A_detail | TEXT | A详情(JSON) |
| N_score | INTEGER | N(新高新产品)得分 |
| N_pass | INTEGER | N是否通过，0/1 |
| N_detail | TEXT | N详情(JSON) |
| S_score | INTEGER | S(供需)得分 |
| S_pass | INTEGER | S是否通过，0/1 |
| S_detail | TEXT | S详情(JSON) |
| L_score | INTEGER | L(领涨)得分 |
| L_pass | INTEGER | L是否通过，0/1 |
| L_detail | TEXT | L详情(JSON) |
| I_score | INTEGER | I(机构认同)得分 |
| I_pass | INTEGER | I是否通过，0/1 |
| I_detail | TEXT | I详情(JSON) |
| M_score | INTEGER | M(大盘)得分 |
| M_pass | INTEGER | M是否通过，0/1 |
| M_detail | TEXT | M详情(JSON) |
| has_base | INTEGER | 是否有基部，0/1 |
| breakout | INTEGER | 是否突破，0/1 |
| created_at | TEXT | 创建时间 |

**写入脚本**：`canslim_pro/screener.py`
**读取场景**：CANSLIM 看板
