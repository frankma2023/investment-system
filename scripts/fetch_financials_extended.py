#!/usr/bin/env python3
"""
scripts/fetch_financials_extended.py — 补拉年报缺失字段

新增8个指标，存入 stock_financials_annual_ext 宽表:
  - ebitda (息税折旧摊销前利润)
  - interest_expense (利息支出)
  - selling_expense (销售费用)
  - admin_expense (管理费用)
  - depreciation (折旧与摊销)
  - total_equity (归母股东权益)
  - total_assets (总资产)  
  - operating_profit (营业利润)

API: /company/fs/non_financial, 逐只查询(≤128指标, 当前17+8=25)
"""

import sys, time
from datetime import datetime, timedelta
from common import api_post, get_db, get_all_stock_codes, get_latest_date, log

API_PATH = "/company/fs/non_financial"

# 新增指标 (年度, y.xx.xx.t)
NEW_METRICS = [
    ["y.ps.ebitda.t",             "ebitda",              False],  # EBITDA
    ["y.ps.ie.t",                  "interest_expense",    False],  # 利息支出
    ["y.ps.se.t",                  "selling_expense",     False],  # 销售费用
    ["y.ps.ae.t",                  "admin_expense",       False],  # 管理费用
    ["y.cfs.dofx_dooaga_dopba.t", "depreciation_fa",     False],  # 固定资产折旧
    ["y.cfs.daaorei.t",           "depreciation_ip",     False],  # 投资性房地产折旧
    ["y.bs.tetoshopc.t",          "total_equity",        False],  # 归母股东权益
    ["y.bs.ta.t",                 "total_assets",        False],  # 总资产
]

SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS stock_financials_annual_ext (
    stock_code TEXT NOT NULL,
    report_date TEXT NOT NULL,
    ebitda REAL,
    interest_expense REAL,
    selling_expense REAL,
    admin_expense REAL,
    depreciation_fa REAL,
    depreciation_ip REAL,
    total_equity REAL,
    total_assets REAL,
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, report_date)
)"""


def fetch_one_stock(code, date_str):
    """拉取单只股票指定报告期的指标"""
    payload = {
        "stockCodes": [code],
        "date": date_str,
        "metricsList": [m[0] for m in NEW_METRICS],
    }
    return api_post(API_PATH, payload)


def extract_nested(data, api_metric):
    keys = api_metric.split(".")
    val = data
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
        if val is None:
            return None
    return float(val) if isinstance(val, (int, float)) else None


def save_annual(conn, raw_data):
    if not raw_data:
        return 0
    rows = []
    for item in raw_data:
        code = item.get("stockCode")
        if not code:
            continue
        date_str = item.get("date", "")[:10]
        vals = {}
        for api_metric, db_col, is_pct in NEW_METRICS:
            v = extract_nested(item, api_metric)
            vals[db_col] = round(v, 2) if v is not None else None

        rows.append((
            code, date_str,
            vals.get("ebitda"), vals.get("interest_expense"),
            vals.get("selling_expense"), vals.get("admin_expense"),
            vals.get("depreciation_fa"), vals.get("depreciation_ip"),
            vals.get("total_equity"), vals.get("total_assets"),
        ))

    if rows:
        conn.executemany("""INSERT OR REPLACE INTO stock_financials_annual_ext
            (stock_code, report_date, ebitda, interest_expense, selling_expense,
             admin_expense, depreciation_fa, depreciation_ip, total_equity, total_assets)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
        conn.commit()
    return len(rows)


def recent_annual_dates(years_back=5):
    today = datetime.now()
    return [f"{y}-12-31" for y in range(today.year - years_back, today.year + 1)]


def main():
    conn = get_db()
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    annual_dates = recent_annual_dates(5)
    stocks = get_all_stock_codes(conn)

    log.info(f"补拉 {len(NEW_METRICS)} 个财务指标")
    log.info(f"股票: {len(stocks)}, 年度: {annual_dates}")
    log.info(f"预估: {len(stocks) * len(annual_dates) / 15 / 60:.0f} 分钟")

    total = 0
    for date_str in annual_dates:
        log.info(f"[{date_str}] 开始...")
        saved = 0
        for i, code in enumerate(stocks):
            try:
                raw = fetch_one_stock(code, date_str)
                n = save_annual(conn, raw)
                saved += n
                total += n
                if (i + 1) % 500 == 0:
                    log.info(f"  [{i+1}/{len(stocks)}] +{saved}条(累计)")
            except Exception as e:
                if (i + 1) % 100 == 0:
                    log.error(f"  [{i+1}/{len(stocks)}] {code} ❌ {str(e)[:50]}")
                time.sleep(3)
        log.info(f"[{date_str}] ✅ {saved}条")

    log.info(f"总计: {total}条")
    row = conn.execute("SELECT COUNT(*) FROM stock_financials_annual_ext").fetchone()
    log.info(f"stock_financials_annual_ext: {row[0]}条")
    conn.close()


if __name__ == "__main__":
    main()
