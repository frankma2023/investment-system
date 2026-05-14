"""
机构持股历史数据回补 — 拉取过去8个季度

直接调理杏仁API，返回全部报告期数据，逐季入库。

用法:
  python scripts/backfill_institutional.py                     # 全量回补
  python scripts/backfill_institutional.py --limit 100          # 前100只测试
  python scripts/backfill_institutional.py --force              # 覆盖已有
"""

import os, sys, time, json, sqlite3, requests
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / 'src'))

DB_PATH = PROJECT_DIR / "data" / "lixinger.db"
ENV_PATH = Path.home() / ".hermes" / ".env"

# 理杏仁配置
BASE_URL = "https://open.lixinger.com/api/cn"
TOKEN = None
INST_CATS = {"fund", "qfii", "social_security", "insurance", "trust", "brokerage", "other_organisations"}


def get_token():
    global TOKEN
    if TOKEN is None:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith("LIXINGER_TOKEN="):
                    TOKEN = line.split("=", 1)[1].strip()
                    break
    return TOKEN


def lx_post(path, payload):
    payload["token"] = get_token()
    r = requests.post(BASE_URL + path, json=payload, timeout=60)
    d = r.json()
    if d.get("code") != 1:
        raise RuntimeError("API error: %s" % d.get("message", ""))
    return d.get("data", [])


def fetch_all_fund(stock_code, start, end):
    """返回 {quarter_date: {fund_count, fund_proportion_sum}}"""
    records = lx_post("/company/fund-shareholders", {
        "stockCode": stock_code, "startDate": start, "endDate": end,
    })
    by_date = defaultdict(lambda: {"count": 0, "prop_sum": 0.0})
    codes_seen = defaultdict(set)
    for r in records:
        d = r.get("date", "")
        if "T" in str(d): d = d.split("T")[0]
        fc = r.get("fundCode", "")
        if fc and fc not in codes_seen[d]:
            codes_seen[d].add(fc)
            by_date[d]["count"] += 1
        by_date[d]["prop_sum"] += r.get("proportionOfOutstandingSharesA", 0) or 0
    # Normalize
    for d in by_date:
        if by_date[d]["prop_sum"] > 1.0:
            by_date[d]["prop_sum"] /= 100.0
    return by_date


def fetch_all_majority(stock_code, start, end):
    """返回 {quarter_date: {inst_count, inst_proportion}}"""
    records = lx_post("/company/majority-shareholders", {
        "stockCode": stock_code, "startDate": start, "endDate": end,
    })
    by_date = defaultdict(lambda: {"count": 0, "prop_sum": 0.0})
    names_seen = defaultdict(set)
    for r in records:
        d = r.get("date", "")
        if "T" in str(d): d = d.split("T")[0]
        cats = r.get("shareholderCategories", [])
        if any(c in INST_CATS for c in cats):
            name = r.get("name", "")
            if name and name not in names_seen[d]:
                names_seen[d].add(name)
                by_date[d]["count"] += 1
            by_date[d]["prop_sum"] += r.get("proportionOfCapitalization", 0) or 0
    for d in by_date:
        if by_date[d]["prop_sum"] > 1.0:
            by_date[d]["prop_sum"] /= 100.0
    return by_date


def save_quarter(stock_code, qdate, fund_data, maj_data):
    """保存单个季度汇总"""
    fc = fund_data.get("count", 0) if fund_data else 0
    fp = fund_data.get("prop_sum", 0) if fund_data else 0
    mc = maj_data.get("count", 0) if maj_data else 0
    mp = maj_data.get("prop_sum", 0) if maj_data else 0
    total = max(fp, mp)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""INSERT OR REPLACE INTO stock_institutional_holdings
        (stock_code, date, data_source, fund_count, fund_holdings_total, fund_proportion_sum,
         top10_inst_count, top10_inst_proportion, top10_float_inst_count, top10_float_inst_prop,
         total_inst_count, total_inst_proportion)
        VALUES (?, ?, 'lixinger', ?, 0, ?, ?, ?, 0, 0, ?, ?)""",
        (stock_code, qdate, fc, round(fp, 4), mc, round(mp, 4), fc + mc, round(total, 4)))
    conn.commit()
    conn.close()


def get_quarter_ends(n=8):
    today = date.today()
    q = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)
    dates = []
    for _ in range(n):
        dates.append(q.strftime("%Y-%m-%d"))
        q = date(q.year, q.month - 2, 1) - timedelta(days=1) if q.month > 3 else date(q.year - 1, 12, 31)
    return sorted(dates)


def get_all_stocks_local(limit=None):
    conn = sqlite3.connect(str(DB_PATH))
    q = """SELECT stock_code, name FROM stock_basic
        WHERE listing_status='normally_listed' AND name NOT LIKE '%ST%'
        ORDER BY stock_code"""
    if limit:
        q += " LIMIT %d" % limit
    rows = conn.execute(q).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def main():
    args = sys.argv[1:]
    limit = None
    force = False
    i = 0
    while i < len(args):
        if args[i] == "--limit": limit = int(args[i+1]); i += 2
        elif args[i] == "--force": force = True; i += 1
        else: i += 1

    quarters = get_quarter_ends(8)
    start = (datetime.strptime(quarters[0], "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    end = quarters[-1]
    print("Quarters: %s ~ %s (%d)" % (quarters[0], quarters[-1], len(quarters)))
    print()

    stocks = get_all_stocks_local(limit)
    print("Stocks: %d" % len(stocks))
    total = 0
    for i, (code, name) in enumerate(stocks):
        try:
            fund = fetch_all_fund(code, start, end)
            maj = fetch_all_majority(code, start, end)
            saved = 0
            for qdate in quarters:
                if not force:
                    conn = sqlite3.connect(str(DB_PATH))
                    ex = conn.execute("SELECT 1 FROM stock_institutional_holdings WHERE stock_code=? AND date=?",
                                      (code, qdate)).fetchone()
                    conn.close()
                    if ex: continue
                fq = {k: fund.get(qdate, {}).get(k, 0) for k in ["count", "prop_sum"]}
                mq = {k: maj.get(qdate, {}).get(k, 0) for k in ["count", "prop_sum"]}
                if fq["count"] > 0 or mq["count"] > 0:
                    save_quarter(code, qdate, {"count": fq["count"], "prop_sum": fq["prop_sum"]},
                                 {"count": mq["count"], "prop_sum": mq["prop_sum"]})
                    saved += 1
            if saved:
                total += saved
                print("[%d/%d] %s %s: %d quarters" % (i+1, len(stocks), code, name, saved))
        except Exception as e:
            print("[%d/%d] %s: ERROR %s" % (i+1, len(stocks), code, e))
    print("\nTotal saved: %d" % total)


if __name__ == "__main__":
    main()
