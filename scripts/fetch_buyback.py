"""
股票回购数据拉取 — 东方财富

API: RPTA_WEB_GETHGLIST_NEW（回购计划列表）
只拉取评分所需的 6 个字段，不贪多。

字段:
  DIM_SCODE       股票代码
  ZJJE            累计已回购金额(元)
  REPUROBJECTIVE  回购目的（含"注销"关键词）
  REPURPROGRESS   进度（001=实施中）
  NOTICEDATE      公告日期
  ZJSZBL          已回购占总股本比例(%)

用法:
  python scripts/fetch_buyback.py                             # 全量拉取
  python scripts/fetch_buyback.py --limit 500                 # 前500条
  python scripts/fetch_buyback.py 600519                      # 单只查询

执行频率: 每周一（daily_update.py 步骤10）
"""

import os, sys, time, json, sqlite3, requests
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR.parent / "data" / "lixinger.db"

API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/gphg/",
}

CREATE_TABLE = """CREATE TABLE IF NOT EXISTS stock_buyback (
    stock_code       TEXT NOT NULL,
    buyback_code     TEXT NOT NULL,           -- 回购编号(REPURCODE)
    notice_date      TEXT,                    -- 公告日期
    progress         TEXT,                    -- 001=实施中 002=已完成
    objective        TEXT,                    -- 回购目的
    amount_yuan      REAL,                    -- 累计已回购金额(元)
    ratio_pct        REAL,                    -- 占总股本比例(%)
    is_cancellation  INTEGER DEFAULT 0,       -- 是否注销回购(0/1)
    updated_at       TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, buyback_code)
);"""


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(CREATE_TABLE)
    conn.commit()
    conn.close()


def fetch_all_buybacks():
    """拉取全量回购计划（分页）"""
    all_data = []
    page = 1
    max_pages = 20
    while page <= max_pages:
        params = {
            "reportName": "RPTA_WEB_GETHGLIST_NEW",
            "columns": "DIM_SCODE,ZJJE,REPUROBJECTIVE,REPURPROGRESS,NOTICEDATE,ZJSZBL,REPURCODE",
            "pageNumber": page,
            "pageSize": 500,
            "sortColumns": "NOTICEDATE",
            "sortTypes": -1,
            "source": "WEB",
            "client": "WEB",
        }
        try:
            r = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            d = r.json()
            if not d.get("success"):
                break
            data = d.get("result", {}).get("data") or []
            if not data:
                break
            all_data.extend(data)
            if len(data) < 500:
                break
            page += 1
            time.sleep(0.3)
        except Exception as e:
            print("Page %d error: %s" % (page, e))
            break
    return all_data


def save_to_db(records):
    """入库（只保留实施中的回购）"""
    conn = sqlite3.connect(str(DB_PATH))
    count = 0
    for r in records:
        code = r.get("DIM_SCODE", "")
        if not code:
            continue

        # 只保留实施中的回购
        progress = r.get("REPURPROGRESS", "")
        if progress != "001":
            continue

        objective = r.get("REPUROBJECTIVE", "") or ""
        is_cancel = 1 if ("注销" in objective or "减少注册资本" in objective) else 0
        amount = r.get("ZJJE") or 0
        ratio = r.get("ZJSZBL") or 0

        conn.execute("""INSERT OR REPLACE INTO stock_buyback
            (stock_code, buyback_code, notice_date, progress, objective,
             amount_yuan, ratio_pct, is_cancellation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, r.get("REPURCODE", ""), (r.get("NOTICEDATE") or "")[:10],
             progress, objective, amount, ratio, is_cancel))
        count += 1

    conn.commit()
    conn.close()
    return count


def main():
    args = sys.argv[1:]
    stock_code = None
    limit = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit":
            limit = int(args[i + 1])
            i += 2
        else:
            stock_code = a
            i += 1

    init_db()

    if stock_code:
        # 单只查询
        print("Query: %s" % stock_code)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""SELECT * FROM stock_buyback
            WHERE stock_code=? AND progress='001'
            ORDER BY notice_date DESC""", (stock_code,)).fetchall()
        conn.close()
        if rows:
            for r in rows:
                extra = " [注销]" if r['is_cancellation'] else ""
                print("  %s: %.0f万元 %.2f%%%s" % (
                    r['notice_date'], r['amount_yuan'] / 10000,
                    r['ratio_pct'] or 0, extra))
        else:
            print("  无实施中的回购")
        return

    # 全量拉取
    print("Fetching buyback plans...")
    records = fetch_all_buybacks()
    print("Total records: %d" % len(records))

    if limit:
        records = records[:limit]

    count = save_to_db(records)
    print("Saved %d active buybacks" % count)

    # 统计
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute("SELECT COUNT(DISTINCT stock_code) FROM stock_buyback WHERE progress='001'")
    stocks = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM stock_buyback WHERE is_cancellation=1 AND progress='001'")
    cancel = cur.fetchone()[0]
    conn.close()
    print("Active: %d stocks, %d cancellations" % (stocks, cancel))


if __name__ == "__main__":
    main()
