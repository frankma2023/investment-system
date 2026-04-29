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
