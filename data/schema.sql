-- ============================================================
-- O'Neil 信号回测框架 — 数据库表
-- 数据库: ~/source/lixinger.db
-- ============================================================

-- 回测运行记录
CREATE TABLE IF NOT EXISTS backtest_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,                    -- 回测名称
    signal_type TEXT    NOT NULL DEFAULT 'distribution_day',  -- 信号类型
    stock_code  TEXT    NOT NULL,                    -- 指数代码 (如 000985)
    start_date  TEXT    NOT NULL,                    -- 开始日期 YYYY-MM-DD
    end_date    TEXT    NOT NULL,                    -- 结束日期
    params      TEXT    NOT NULL,                    -- 参数 JSON
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 回测结果中的每个抛盘日
CREATE TABLE IF NOT EXISTS backtest_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    stock_code  TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    signal_type TEXT    NOT NULL,                    -- standard / heavy / stealth / reversal
    score       REAL,                               -- 总分
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    change_pct  REAL,                               -- 涨跌幅%
    volume      INTEGER,
    amount      REAL,                               -- 成交额(元)
    -- 波动率
    vol_5d      REAL,
    vol_10d     REAL,
    vol_20d     REAL,
    -- 均线
    ma5         REAL,
    ma10        REAL,
    ma20        REAL,
    ma50        REAL,
    ma120       REAL,
    ma250       REAL,
    -- 详细评分
    volume_score    INTEGER,
    decline_score   INTEGER,
    position_score  INTEGER,
    gap_score       INTEGER,
    special_score   INTEGER,
    total_score     INTEGER,
    -- 形态
    close_position  REAL,
    upper_shadow_pct REAL,
    lower_shadow_pct REAL,
    volume_ratio    REAL,
    volume_ratio_ma5 REAL
);

-- 回测统计摘要
CREATE TABLE IF NOT EXISTS backtest_stats (
    run_id          INTEGER PRIMARY KEY REFERENCES backtest_runs(id) ON DELETE CASCADE,
    total_days      INTEGER,                        -- 总交易日
    signal_count    INTEGER,                        -- 信号总数
    standard_count  INTEGER,                        -- 标准抛盘日
    heavy_count     INTEGER,                        -- 重抛盘日
    stealth_count   INTEGER,                        -- 假阳线
    reversal_count  INTEGER,                        -- 盘中反转
    weighted_count  INTEGER,                        -- 加权合计
    avg_vol_10d     REAL,                           -- 平均10日波动率
    avg_volume_ratio REAL                           -- 平均量比
);

CREATE INDEX IF NOT EXISTS idx_br_stock ON backtest_runs(stock_code, signal_type);
CREATE INDEX IF NOT EXISTS idx_bs_run ON backtest_signals(run_id);
CREATE INDEX IF NOT EXISTS idx_bs_date ON backtest_signals(date);

-- ============================================================
-- 知行系统 — 投资纪律引擎
-- ============================================================

-- 观察池日快照（宽表）
CREATE TABLE IF NOT EXISTS discipline_observation_pool (
    stock_code          TEXT NOT NULL,
    date                TEXT NOT NULL,
    stock_name          TEXT,
    industry_name       TEXT,
    -- RS 分类
    rs_category         TEXT,
    rps_20              REAL,
    rps_60              REAL,
    rps_120             REAL,
    rps_250             REAL,
    -- CANSLIM 评分
    canslim_total       REAL,
    canslim_c           REAL,
    canslim_a           REAL,
    canslim_n           REAL,
    canslim_s           REAL,
    canslim_l           REAL,
    canslim_i           REAL,
    canslim_m           REAL,
    -- 财务健康
    roe                 REAL,
    eps_yoy             REAL,
    revenue_yoy         REAL,
    debt_ratio          REAL,
    gross_margin        REAL,
    -- 估值仪表
    pe_ttm              REAL,
    pb                  REAL,
    pe_percentile       REAL,
    market_cap          REAL,
    -- 形态信号
    buy_signals_json    TEXT,
    sell_signals_json   TEXT,
    signals_json        TEXT,       -- V2: 统一信号列（替代 buy/sell 拆分）
    -- 综合建议
    composite_score     REAL,
    grade               TEXT,
    suggestion          TEXT,
    PRIMARY KEY (stock_code, date)
);

-- 交易记录（买入→卖出闭环）
CREATE TABLE IF NOT EXISTS discipline_trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code          TEXT NOT NULL,
    stock_name          TEXT,
    asset_type          TEXT DEFAULT 'stock',  -- 'stock' 或 'index'
    -- 买入信息
    buy_date            TEXT NOT NULL,
    buy_price           REAL NOT NULL,
    buy_qty             INTEGER NOT NULL,
    buy_amount          REAL NOT NULL,
    buy_reason          TEXT NOT NULL,
    buy_emotion         TEXT,
    target_period       TEXT NOT NULL,
    target_price        REAL,
    stop_loss_price     REAL NOT NULL,
    position_pct        REAL,
    checklist_json      TEXT,
    -- 卖出信息
    sell_date           TEXT,
    sell_price          REAL,
    sell_reason         TEXT,
    sell_emotion        TEXT,
    -- 结果
    pnl_amount          REAL,
    pnl_pct             REAL,
    hold_days           INTEGER,
    -- 复盘
    review_rule_compliance  REAL,
    review_alpha            REAL,
    review_beta             REAL,
    review_note             TEXT,
    review_vitality         INTEGER,
    created_at          TEXT DEFAULT (datetime('now','localtime')),
    updated_at          TEXT
);

-- 规则配置
CREATE TABLE IF NOT EXISTS discipline_rules_config (
    rule_name           TEXT PRIMARY KEY,
    display_name        TEXT,
    category            TEXT,
    parameters_json     TEXT,
    is_active           INTEGER DEFAULT 1,
    created_at          TEXT DEFAULT (datetime('now','localtime'))
);

-- 持仓快照（V2）
CREATE TABLE IF NOT EXISTS discipline_daily_snapshots (
    date                TEXT NOT NULL,
    trade_id            INTEGER NOT NULL,
    current_price       REAL,
    market_value        REAL,
    pnl_pct             REAL,
    position_pct        REAL,
    alerts_json         TEXT,
    PRIMARY KEY (date, trade_id)
);

-- 告警记录（V2）
CREATE TABLE IF NOT EXISTS discipline_alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            INTEGER,
    stock_code          TEXT,
    alert_date          TEXT,
    alert_level         TEXT,
    alert_type          TEXT,
    alert_message       TEXT,
    acknowledged        INTEGER DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now','localtime'))
);

-- 形态扫描信号（持久化，替代 data.json 的历史追溯）
CREATE TABLE IF NOT EXISTS pattern_scan_signals (
    stock_code      TEXT NOT NULL,
    date            TEXT NOT NULL,
    signals_json    TEXT,
    PRIMARY KEY (stock_code, date)
);