# Lixinger Database Schema

> 数据库: `data/lixinger.db`  
> SQLite3 (WAL mode)  
> 最后更新: 2026-05-06

---

## 概览

| 分类 | 表数 | 说明 |
|------|------|------|
| 行情数据 | 4 | 个股日K线、周K线、指数日K线、融资融券 |
| 指数基本面 | 1 | 指数估值/量价/融资/分位点（拥挤度计算依赖） |
| 指数拥挤度 | 1 | 五维度拥挤度指标 + 复合得分 |
| 指数成分 | 2 | 成分股 + 权重（408个指数） |
| 财务基本面 | 7 | 季报、年报、估值指标（含 CANSLIM 专用表） |
| 股东数据 | 2 | 股东人数 v1/v2 |
| 分类体系 | 3 | 行业分类、指数归属、申万一级行业 |
| RS 强度 | 2 | 个股 RS 日评、行业 RS 日评 |
| 行业分析 | 3 | 行业内部强度、行业轮动、行业强度 |
| 市场方向 | 6 | 市场状态、抛盘日、追盘日、吸筹日、扫描结果 |
| 候选与信号 | 3 | 股票候选、买入信号、CANSLIM 评分 |
| 投资组合 | 4 | 持仓、信号、7周法则、自选股 |
| 回测 | 3 | 分布日回测运行/信号/统计 |
| 分布日特征 | 1 | 个股抛盘日特征工程表 |

---

## 1. 行情数据

### stock_basic — 股票基础信息
```
stock_code     TEXT PRIMARY KEY    -- 股票代码
name           TEXT                -- 股票名称
market         TEXT                -- a: A股
exchange       TEXT                -- sh/sz/bj
area_code      TEXT
listing_status TEXT                -- normally_listed / delisted / special_treatment / ...
ipo_date       TEXT
delisted_date  TEXT
fs_table_type  TEXT                -- non_financial / bank / insurance / ...
mutual_market_flag INTEGER DEFAULT 0  -- 陆股通标的
updated_at     TEXT
```
**数据量**: 5,595 只股票（5,391 正常上市，92 ST，87 退市风险警示）  
**更新脚本**: `scripts/fetch_stock_basic.py`

### daily_kline — 个股日K线
```
stock_code, date  PRIMARY KEY
open, close, high, low  REAL
volume, amount           -- 成交量、成交额
change_pct, turnover_rate -- 涨跌幅(%), 换手率(%)
complex_factor           -- 复权因子
adj_open, adj_high, adj_low, adj_close  -- 后复权价格
```
**数据量**: 17.94M 行 | **范围**: 1996-01-02 ~ 2026-04-30  
**更新脚本**: `scripts/fetch_daily_kline.py`

### weekly_kline — 个股周K线（从日K线聚合）
```
stock_code, week_start_date  PRIMARY KEY
week_end_date, year_week
open, close, high, low  REAL
volume, amount           -- 周总成交量/额（日值求和）
change_pct               -- 周涨跌幅(%)
turnover_rate            -- 周换手率（日换手率求和）
trade_days               -- 该周交易日数
adj_open, adj_high, adj_low, adj_close
```
**数据量**: 2.22M 行 | **范围**: 2016-10-10 ~ 2026-04-16  
**更新脚本**: `scripts/build_weekly_kline.py`

### index_daily_kline — 指数日K线
```
stock_code, date, kline_type  PRIMARY KEY
  -- kline_type: normal / total_return
open, close, high, low  REAL
volume, amount
change                   -- 涨跌幅(%)
```
**数据量**: 1.42M 行（normal: 1.37M, total_return: 46.9K）  
**范围**: 2000-01-04 ~ 2026-04-30  
**覆盖**: 409 个指数（来自 `config/index_rs.yaml`，共 5 大类：market/sector_l1/sector_l2/sector_l3/style）  
**更新脚本**: `scripts/fetch_index_kline.py`

### index_fundamental_daily — 指数基本面日数据（拥挤度计算依赖）
```
stock_code, date  PRIMARY KEY
mc           REAL    -- 总市值
tv           REAL    -- 成交量
ta           REAL    -- 成交额
to_r         REAL    -- 换手率 (%)
pe_ttm       REAL    -- PE-TTM 市值加权
pe_ttm_pct   REAL    -- PE 10年分位点 (0~1)
pb           REAL    -- PB 市值加权
pb_pct       REAL    -- PB 10年分位点 (0~1)
dyr          REAL    -- 股息率 (%)
dyr_pct      REAL    -- 股息率 10年分位点 (0~1)
fpa          REAL    -- 融资买入金额
fb           REAL    -- 融资余额
ecmc         REAL    -- 自由流通市值
updated_at   TEXT    -- 更新时间
```
**数据量**: 795,912 行 | **范围**: 2016-01-01 ~ 2026-05-05
**覆盖**: 407 个指数
**更新脚本**: `scripts/fetch_index_fundamental.py`
**用途**: 指数拥挤度计算（交易热度/资金流向/估值水位维度）

### index_crowding_daily — 指数拥挤度日数据
```
stock_code, date  PRIMARY KEY
-- 交易热度 (35%)
turnover_ratio      REAL    -- 成交额占比（指数成交额/全市场成交额）
turnover_ratio_pct  REAL    -- 成交额占比滚动分位点 (0~1)
turnover_rate_pct   REAL    -- 换手率滚动分位点 (0~1)
heat_score          REAL    -- 交易热度维度得分 (0~100)
-- 资金流向 (25%)
margin_balance_ratio REAL   -- 融资余额/自由流通市值
margin_balance_pct  REAL    -- 融资余额占比分位点 (0~1)
margin_buy_ratio    REAL    -- 融资买入额/成交额
margin_buy_pct      REAL    -- 融资买入额占比分位点 (0~1)
flow_score          REAL    -- 资金流向维度得分 (0~100)
-- 估值水位 (25%)
pe_pct              REAL    -- PE 十年分位点 (0~1)
pb_pct              REAL    -- PB 十年分位点 (0~1)
dyr_pct             REAL    -- 股息率十年分位点 (0~1)
valuation_score     REAL    -- 估值水位维度得分 (0~100)
-- 机构行为 (15%)
fund_holding_pct    REAL    -- 基金重仓分位点（暂无数据）
institution_score   REAL    -- 机构行为维度得分
-- 综合
composite_score     REAL    -- 复合拥挤度得分 (0~100)
crowd_level         TEXT    -- 拥挤等级: 低拥挤/正常/偏高/高拥挤
updated_at          TEXT    -- 更新时间
```
**数据量**: 794,426 行 | **范围**: 2016-01-01 ~ 2026-05-05
**覆盖**: 406 个指数
**计算脚本**: `src/scanners/index_crowding.py`
**依赖**: `index_fundamental_daily`

### stock_margin — 融资融券数据
```
stock_code, date  PRIMARY KEY
mtaslb, mtaslb_fb, mtaslb_sb    -- 融资融券余额 / 融资余额 / 融券余额
mtaslb_mc_r                      -- 融资买入额
npa_o_f_d1 ~ npa_o_f_d240        -- 净买入额（1/5/10/20/60/120/240日）
fb_mc_rc_d1 ~ fb_mc_rc_d240      -- 融资偿还率
```
**数据量**: 5,023 行 | **范围**: 2026-04-01 ~ 2026-04-22  
**更新脚本**: `scripts/fetch_margin.py`

---

## 2. 指数成分

### index_constituents — 指数成分股
```
index_code, stock_code, date  PRIMARY KEY
updated_at
```
**数据量**: 622,990 行 | **范围**: 2025-06-01 ~ 2026-05-01  
**覆盖**: 407 个指数（每月成分股快照）  
**更新脚本**: `scripts/fetch_index_constituents.py`

### index_constituent_weightings — 指数成分股权重
```
index_code, stock_code, date  PRIMARY KEY
weighting     REAL
updated_at
```
**数据量**: 1.19M 行 | **范围**: 2025-06-02 ~ 2026-04-30  
**覆盖**: 406 个指数  
**更新脚本**: `scripts/fetch_index_constituents.py`

---

## 3. 财务基本面

### fundamental_indicator — 估值与市场指标（理杏仁指标接口）
```
stock_code, date, metric_code  PRIMARY KEY
value     REAL
```
**指标类型**（33种）:
| 指标 | 含义 | 数据量 |
|------|------|--------|
| dyr | 股息率 | 4.86M |
| ecmc | 企业价值/市值 | 4.86M |
| mc | 总市值 | 4.86M |
| sp | 股价 | 4.86M |
| ta | 总资产 | 4.86M |
| to_r | 换手率 | 4.86M |
| tv | 总成交量 | 4.86M |
| pe_ttm | 滚动市盈率 | 4.85M |
| pb | 市净率 | 4.85M |
| pb_wo_gw | 剔除商誉 PB | 4.85M |
| ps_ttm | 滚动市销率 | 4.85M |
| pcf_ttm | 滚动市现率 | 4.85M |
| ... | （还有 20 种） | |
**更新脚本**: `scripts/fetch_fundamental_nonfinancial.py`

### financial_statement — 财报原始数据
```
stock_code, report_date, metric_code  PRIMARY KEY
announce_date  TEXT
value          REAL
```
**指标**: q.ps.toi.t（营收）, q.bs.ta.t（总资产）, 等 9 种  
**数据量**: 28,378 行 | **范围**: 2025-06-30 ~ 2026-03-31

### stock_financials_quarterly — 季度财务数据（结构化）
```
stock_code, report_date  PRIMARY KEY
announce_date
revenue_single, revenue_yoy, revenue_qoq
net_profit_single, net_profit_margin, net_profit_yoy, net_profit_qoq
net_profit_adj_single, net_profit_adj_margin, net_profit_adj_yoy, net_profit_adj_qoq
gross_margin_single, roe_single
free_cash_flow
asset_liability_ratio, interest_bearing_debt_ratio
current_ratio, quick_ratio
receivables_turnover, inventory_turnover
updated_at
```
**数据量**: 161,627 行 | **范围**: 2012-03-31 ~ 2026-03-31

### stock_financials_annual — 年度财务数据（结构化）
```
stock_code, report_date  PRIMARY KEY
announce_date
revenue, revenue_yoy
net_profit, net_profit_yoy, net_profit_adj
gross_margin, roe, roe_adj
operating_cash_flow, free_cash_flow, free_cash_flow_yoy
asset_liability_ratio, interest_bearing_debt_ratio
current_ratio, quick_ratio
receivables_turnover, inventory_turnover
updated_at
```
**数据量**: 57,010 行 | **范围**: 2012-12-31 ~ 2025-12-31

### canslim_quarterly_eps — CANSLIM 季度 EPS 快照
```
stock_code, report_date  PRIMARY KEY
eps_basic, revenue_yoy, net_profit_yoy, np_atoopc_yoy
revenue_ps_oi, revenue_ps_oi_yoy, revenue_ps_toi, revenue_ps_toi_yoy
net_profit_attributable, net_profit_attributable_yoy
net_profit_adjusted, net_profit_adjusted_yoy
gross_margin_ps, gross_margin_m, roe_m, roe_weighted, roe_adjusted_weighted
roe_attributable, roe_adjusted_attributable
operating_cash_flow, free_cash_flow
asset_liability_ratio, interest_bearing_debt_ratio, current_ratio, quick_ratio
receivables_turnover, inventory_turnover
revenue_single, net_profit_attributable_single, net_profit_adjusted_single
gross_margin_single, roe_single
net_profit_margin, adjusted_net_profit_margin
updated_at
```
**数据量**: 97,713 行 | **范围**: 2015-03-31 ~ 2026-03-31

### canslim_annual_eps — CANSLIM 年度 EPS 快照
```
stock_code, report_date  PRIMARY KEY
eps_basic, net_profit, roe
revenue_ps_oi, revenue_ps_toi
net_profit_attributable, net_profit_adjusted
gross_margin_ps, gross_margin_m
roe_weighted, roe_adjusted_weighted, roe_attributable, roe_adjusted_attributable
operating_cash_flow, free_cash_flow
asset_liability_ratio, interest_bearing_debt_ratio, current_ratio, quick_ratio
receivables_turnover, inventory_turnover
updated_at
```
**数据量**: 17,781 行 | **范围**: 2021-12-31 ~ 2025-12-31

### canslim_institutional — CANSLIM 机构持仓
```
stock_code, report_date  PRIMARY KEY
fund_count        INTEGER    -- 基金数量
total_holdings    REAL       -- 总持仓
total_market_cap  REAL       -- 总市值
total_share_pct   REAL       -- 持股比例
updated_at
```
**数据量**: 7,088 行 | **范围**: 2025-03-31 ~ 2025-12-31

---

## 4. 股东数据

### shareholders_num — 股东人数 v1（原始版）
```
stock_code, date  PRIMARY KEY
total         INTEGER    -- 股东人数
change_rate   REAL       -- 变化比例
price_change  REAL       -- 股价涨跌幅
```

### shareholders_num_v2 — 股东人数 v2（多周期版）
```
stock_code, date  PRIMARY KEY
shnc_rln      INTEGER    -- 最新股东人数
shnc_d10/20/30/60/90     -- 10/20/30/60/90日变化率
shnc_qln                 -- 上期股东人数
shnc_q1/2/3              -- 1/2/3季度变化
shnc_y1/2                -- 1/2年变化
```
**数据量**: 5,168 行 | **范围**: 2021-12-31 ~ 2026-04-02

---

## 5. 分类体系

### stock_industry — 股票行业分类
```
stock_code, industry_code, source  PRIMARY KEY
industry_name  TEXT
source         TEXT    -- sw / cni / sw_2021
updated_at
```

### stock_index — 股票指数归属
```
stock_code, index_code  PRIMARY KEY
index_name  TEXT
source      TEXT    -- csi / cni / hsi / usi / lxri
updated_at
```

### stock_sw_industry — 申万一级行业（每只股票一个行业）
```
stock_code     PRIMARY KEY
industry_name  TEXT    -- 申万一级行业名称
industry_code  TEXT    -- 行业指数代码
updated_at
```
**数据量**: 5,500 只股票

---

## 6. RS 强度

### rs_daily — 个股 RS 日评
```
stock_code, date  PRIMARY KEY
industry_code, industry_name
rs_mkt_long, rs_mkt_mid, rs_mkt_short   -- 相对市场（中证全指 000985）
rs_ind_long, rs_ind_mid, rs_ind_short   -- 相对行业
pattern           TEXT   -- 双强标记
long_days, mid_days, short_days         -- 计算参数
updated_at
```
**数据量**: 5.27M 行 | **范围**: 2022-02-07 ~ 2026-04-16

### sector_rs_daily — 行业 RS 日评
```
id  PRIMARY KEY AUTOINCREMENT
date, sector_code  UNIQUE
sector_name
rs_ratio, score_20, score_120, score_250
rps_20, rps_120, rps_250
price_vs_ma200, ma200_trend
is_leading, is_momentum, is_setup, is_compact
internal_status, internal_count, internal_weighted
top_stocks
daily_change_pct, vol_ratio_20, vol_ratio_5
rs20_trend_up, momentum_score, momentum_accel, momentum_trend
rs_dist_score, trend_score, money_flow_score, resonance_score
health_score, health_grade
strong_ratio, above_ma50_ratio, fund_flow_intensity
rotation_signal
created_at
```
**数据量**: 3,330 行 | **范围**: 2025-10-31 ~ 2026-04-16

---

## 7. 行业分析

### sector_internal_strength — 行业内部强度
```
date, sector_code  PRIMARY KEY
sector_name
constituent_count, rs_mean_20, rs_mean_120, rs_mean_250, rs_std_120
above_ma50_count, above_ma200_count, bull_alignment_count
volume_surge_count, breakout_count, breakout_stocks
fund_flow_intensity, strong_ratio, above_ma50_ratio
rs_dist_score, trend_score, money_flow_score, resonance_score
```
**数据量**: 3,330 行 | **范围**: 2025-10-31 ~ 2026-04-16

### sector_rotation — 行业轮动
```
date, sector_code  PRIMARY KEY
sector_name
momentum_delta_5d, rps_delta_5d
rotation_signal
```
**数据量**: 3,330 行

### industry_strength_results — 行业强度结果
```
date, industry_code  PRIMARY KEY
industry_name, rs_20d, rs_60d, rs_120d, composite_rs
rank, category, trend, signals
created_at
```
**数据量**: 1 行（最新: 2026-04-16）

### sector_strength_results — 板块强度结果
```
id  PRIMARY KEY AUTOINCREMENT
analysis_date, sector_code  UNIQUE
sector_name, category, return_20d, rank
created_at
```
**数据量**: 5 行

### index_divergence_results — 指数背离分析
```
id  PRIMARY KEY AUTOINCREMENT
analysis_date  UNIQUE
market_state, action, focus
leading_style_code, leading_style_name
market_divergence_type, style_divergence_type, sector_divergence_type
results_json
created_at
```
**数据量**: 1 行

---

## 8. 市场方向

### market_direction_daily — 市场方向日评
```
date  PRIMARY KEY
market_phase, market_phase_confidence      -- 上升趋势/震荡盘整/下降趋势/尝试反弹
risk_level                                 -- 正常/警戒/危险
suggested_position_size
distribution_days_25d, distribution_days_10d, distribution_trend, distribution_warning
ftd_exists, ftd_date, ftd_day_count, ftd_index_code, ftd_index_name, ftd_gain_pct, ftd_volume_ratio
accumulation_days_10d, standard_accumulation, special_accumulation, breakout_accumulation
accumulation_vs_distribution
divergence_pattern, style_divergence, sector_rotation_summary
leading_index_code, leading_index_name, leading_index_rs, top_indices
market_health_score, health_score_components
advance_decline_ratio, new_high_new_low_ratio, above_ma50_ratio
summary, action_suggestion, warnings
focus, avoid, stop_loss
strengths, weaknesses, opportunities, risks
created_at
```
**数据量**: 313 行 | **范围**: 2024-12-27 ~ 2026-04-16

### distribution_days_detail — 抛盘日明细
```
date, index_code  UNIQUE
index_name, close, change_pct, volume, prev_volume, volume_ratio
is_distribution, distribution_type   -- 标准抛盘日/高位抛盘日/连续抛盘日
decline_threshold_used
market_phase_at_date, is_high_position
created_at
```
**数据量**: 330 行 | **范围**: 2024-11-18 ~ 2026-03-30

### market_distribution_days — 市场抛盘日（备用表）
```
date, index_code  PRIMARY KEY
is_distribution, dist_type
change_pct, volume_ratio, close_position, upper_shadow_ratio
created_at
```
**数据量**: 436 行 | **范围**: 2022-02-11 ~ 2026-04-02

### accumulation_days_detail — 吸筹日明细
```
date, index_code  UNIQUE
index_name, close, change_pct, volume, prev_volume, volume_ratio
amplitude, close_position
is_accumulation, is_standard_acc, is_special_acc, is_breakout_acc, accumulation_type
created_at
```
**数据量**: 10 行 | **范围**: 2026-03-17 ~ 2026-03-30

### follow_through_days — 追盘日
```
ftd_date  PRIMARY KEY
low_point_date, low_point_value, day_count
index_code, index_name, close, gain_pct, volume, prev_volume, volume_ratio
is_valid, invalidated_date, invalidated_reason
follow_up_5d_return, follow_up_20d_return
created_at
```
**数据量**: 13 行

### daily_distribution_summary — 每日抛盘汇总
```
date  PRIMARY KEY
total_indices, distribution_count
standard_distribution_count, special_distribution_count
reversal_distribution_count, heavy_distribution_count
confirmation_count, canceled_count, weighted_distribution_sum
market_status
created_at
```

### market_scan_results — 市场扫描结果
```
date, index_code  UNIQUE
close, open, high, low, volume, amount, prev_close, prev_volume
change_pct, volume_ratio
is_flat_day, is_standard_distribution, is_special_distribution
is_intraday_reversal, is_heavy_distribution
distribution_type, distribution_weight
is_confirmation_day, is_canceled, canceled_by_date
distribution_count_25d, standard_count_25d, special_count_25d
reversal_count_25d, heavy_count_25d, canceled_count_25d
market_status
ma5, ma10, ma20, ma50, ma120, ma250
calculated_at, updated_at
```
**数据量**: 201 行 | **范围**: 2026-01-05 ~ 2026-04-16

### market_scan_parameters — 扫描参数集
```
parameter_set_name  UNIQUE
description
std_decline_threshold, std_volume_increase
special_max_gain, special_min_intraday_gain, special_volume_ratio
special_upper_shadow_entity_ratio, special_upper_shadow_amplitude_ratio
reversal_volume_ratio, reversal_min_intraday_gain
reversal_upper_shadow_entity_ratio, reversal_close_position
heavy_decline_threshold, heavy_volume_ratio
confirmation_gain_threshold
flat_day_threshold
rolling_window_days, pressure_threshold, bear_threshold
require_multiple_indices, min_indices_confirm
is_default, created_at, updated_at
```

---

## 9. 候选与信号

### stock_candidates_daily — 每日股票候选
```
stock_code, date  PRIMARY KEY
stock_name, industry_name
-- RS维度
rs_score, rs_mkt_long
-- 基本面维度
fundamental_score, eps_ttm, eps_yoy, revenue_yoy, roe, debt_ratio
-- 量价维度
vol_price_score, price_vs_ma50, price_vs_ma200, dist_from_high
avg_volume_20d, volume_trend, ma_trend
-- 形态维度
pattern_score, pattern_health, pattern_type
-- 综合
composite_score, grade
is_watchlist
created_at
```
**数据量**: 5,220 行 | **范围**: 2026-04-02 ~ 2026-04-16

### buy_signals_daily — 买入信号
```
date, stock_code, signal_type  UNIQUE
stock_name, subtype
entry_price, entry_price_high, stop_loss_price, target_price
confidence, strength_score, suggested_position_pct
details_json
created_at
```
**数据量**: 0 行（表已建，无数据）

### canslim_scores — CANSLIM 评分
```
date, stock_code  UNIQUE
stock_name, total_score, pass_count
C_score, C_pass, C_detail
A_score, A_pass, A_detail
N_score, N_pass, N_detail
S_score, S_pass, S_detail
L_score, L_pass, L_detail
I_score, I_pass, I_detail
M_score, M_pass, M_detail
has_base, breakout
created_at
```
**数据量**: 0 行（表已建，无数据）

---

## 10. 投资组合

### portfolio_holdings — 持仓记录
```
stock_code, batch_id, buy_date, buy_price  UNIQUE
stock_name, market, qty, note
created_at, updated_at
```
**数据量**: 12 条

### portfolio_signals — 持仓信号
```
scan_date, stock_code, batch_id  UNIQUE
stock_name, buy_price, buy_date, qty
current_price, pnl_pct, hold_days
signal_level, signal_rule, signal_detail
status, updated_at, created_at
```
**数据量**: 44 条

### seven_week_state — 持仓 7 周法则追踪
```
stock_code  PRIMARY KEY
stock_name, first_batch_date
has_broken_10d, signal_fired
updated_at
```
**数据量**: 7 条

### watchlist — 自选股
```
stock_code  PRIMARY KEY
stock_name, added_at, removed_at, note
```

---

## 11. 回测

### backtest_runs — 回测运行记录
```
id  PRIMARY KEY AUTOINCREMENT
name, signal_type, stock_code, start_date, end_date
params     TEXT (JSON)
created_at
```
**数据量**: 0 行（表已建，待填充）

### backtest_signals — 回测信号
```
id  PRIMARY KEY AUTOINCREMENT
run_id     REFERENCES backtest_runs(id) ON DELETE CASCADE
stock_code, date, signal_type   -- standard / heavy / stealth / reversal
score, open, high, low, close, change_pct, volume, amount
vol_5d, vol_10d, vol_20d
ma5, ma10, ma20, ma50, ma120, ma250
volume_score, decline_score, position_score, gap_score, special_score, total_score
close_position, upper_shadow_pct, lower_shadow_pct
volume_ratio, volume_ratio_ma5
```
**数据量**: 0 行

### backtest_stats — 回测统计
```
run_id  PRIMARY KEY REFERENCES backtest_runs(id) ON DELETE CASCADE
total_days, signal_count, standard_count, heavy_count, stealth_count
reversal_count, weighted_count
avg_vol_10d, avg_volume_ratio
```
**数据量**: 0 行

---

## 12. 分布日特征

### distribution_day_features — 个股抛盘日特征工程表
```
stock_code, date  PRIMARY KEY
open, high, low, close, volume, amount
change_pct, prev_close
volume_ratio, volume_ratio_ma5, volume_score
decline_score, stagnation_flag, is_stealth_dist
close_position, upper_shadow_pct, lower_shadow_pct, body_pct
position_score
gap_down_flag, gap_filled_flag, gap_score
total_score, is_dist_day
fwd_max_dd_5d, fwd_max_dd_10d, fwd_return_5d, fwd_return_10d
label_dd_gt_2pct
dist_count_20d, dist_count_15d
```
**数据量**: 12,339 行 | **范围**: 2016-01-04 ~ 2024-12-31  
**用途**: 训练抛盘日识别模型的特征数据

---

## 数据更新脚本索引

| 脚本 | 目标表 | 频率 |
|------|--------|------|
| `scripts/fetch_stock_basic.py` | stock_basic | 按需 |
| `scripts/fetch_daily_kline.py` | daily_kline | 每日 |
| `scripts/build_weekly_kline.py` | weekly_kline | 每日 |
| `scripts/fetch_index_kline.py` | index_daily_kline | 每日 |
| `scripts/fetch_index_fundamental.py` | index_fundamental_daily | 每日 |
| `src/scanners/index_crowding.py` | index_crowding_daily | 每日（依赖上条） |
| `scripts/fetch_index_constituents.py` | index_constituents, index_constituent_weightings | 每月 |
| `scripts/fetch_fundamental_nonfinancial.py` | fundamental_indicator | 每日 |
| `scripts/fetch_stock_financials.py` | stock_financials_quarterly, stock_financials_annual | 季报后 |
| `scripts/fetch_margin.py` | stock_margin | 每日 |
| `scripts/compute_rs.py` | rs_daily | 每日 |
| `scripts/compute_sector_rs.py` | sector_rs_daily | 每日 |
| `scripts/market_direction.py` | market_direction_daily, distribution_days_detail, ... | 每日 |
| `scripts/canslim_*.py` | canslim_* tables | 按需 |

---

## 关键数字

| 指标 | 数值 |
|------|------|
| 个股总数 | 5,595（正常上市 5,391） |
| 指数总数 | 409（覆盖 5 大类） |
| 个股日K线 | 17.94M 行（1996 ~ 今） |
| 指数日K线 | 1.42M 行（2000 ~ 今） |
| 财务季报 | 161K 行（2012 ~ 今） |
| 财务年报 | 57K 行（2012 ~ 今） |
| RS 日评 | 5.27M 行（2022-02 ~ 今） |
| 成分股权重 | 1.19M 行 |
| 总行数 | ≈ 30M |
