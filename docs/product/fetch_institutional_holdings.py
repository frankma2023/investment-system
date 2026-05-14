"""
理杏仁机构持股数据拉取脚本

API:
  - /api/cn/company/fund-shareholders  公募基金持股（按基金粒度）
  - /api/cn/company/majority-shareholders 前十大股东（按股东粒度）

用法:
  python fetch_institutional_holdings.py 600519                # 单只
  python fetch_institutional_holdings.py --batch top500        # 批量 TOP500 RS
  python fetch_institutional_holdings.py --batch top500 --save # 批量+入库
  python fetch_institutional_holdings.py --date 2026-05-14
"""

import sys
import os
import time
import json
import sqlite3
from datetime import datetime, timedelta, date
from collections import defaultdict

# 项目根路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# docs/product/ → 项目根
PROJECT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from common import get_token, get_session, api_post

DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")

# ═══════════════════════════════════════════════
# 建表
# ═══════════════════════════════════════════════
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_institutional_holdings (
    stock_code              TEXT NOT NULL,
    date                    TEXT NOT NULL,      -- 报告期或统计日期
    data_type               TEXT NOT NULL,      -- 'fund' / 'majority' / 'combined'
    -- 公募基金
    fund_count              INTEGER,            -- 持有基金数
    fund_holdings_total     REAL,               -- 基金持股市值合计
    fund_proportion_sum     REAL,               -- 流通A股占比合计
    -- 前十大股东（仅机构）
    top10_inst_count        INTEGER,            -- 前十大中机构数
    top10_inst_proportion   REAL,               -- 前十大中机构持股占比合计
    -- 汇总
    total_inst_count        INTEGER,            -- 总机构数（去重）
    total_inst_proportion   REAL,               -- 总机构持股占比估算
    org_categories_json     TEXT,               -- 机构类别分布 JSON
    updated_at              TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, date, data_type)
);
"""


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    conn.close()


def fetch_fund_shareholders(stock_code, start_date, end_date):
    """拉取公募基金持股数据，汇总统计"""
    payload = {
        "token": get_token(),
        "stockCode": stock_code,
        "startDate": start_date,
        "endDate": end_date,
    }
    try:
        records = api_post("/company/fund-shareholders", payload, timeout=60)
    except Exception as e:
        print(f"  [{stock_code}] fund API error: {e}")
        return None

    if not records:
        return {"fund_count": 0, "fund_holdings_total": 0, "fund_proportion_sum": 0, "date": None}

    # 取最新报告期的数据（避免多期叠加）
    # 按 date 分组，只保留最新日期
    date_groups = defaultdict(list)
    for r in records:
        d = r.get("date", "")
        if isinstance(d, str) and "T" in d:
            d = d.split("T")[0]
        date_groups[d].append(r)

    if not date_groups:
        return {"fund_count": 0, "fund_holdings_total": 0, "fund_proportion_sum": 0, "date": None}

    latest_date = sorted(date_groups.keys())[-1]
    latest_records = date_groups[latest_date]

    # 汇总
    fund_codes = set()
    fund_holdings_total = 0.0
    fund_proportion_sum = 0.0

    for r in latest_records:
        fc = r.get("fundCode", "")
        if fc:
            fund_codes.add(fc)
        fund_holdings_total += r.get("marketCap", 0) or 0
        fund_proportion_sum += r.get("proportionOfOutstandingSharesA", 0) or 0

    return {
        "fund_count": len(fund_codes),
        "fund_holdings_total": fund_holdings_total,
        "fund_proportion_sum": round(fund_proportion_sum, 4),
        "date": latest_date,
    }


def fetch_majority_shareholders(stock_code, start_date, end_date):
    """拉取前十大股东数据，按机构类别统计"""
    payload = {
        "token": get_token(),
        "stockCode": stock_code,
        "startDate": start_date,
        "endDate": end_date,
    }
    try:
        records = api_post("/company/majority-shareholders", payload, timeout=60)
    except Exception as e:
        print(f"  [{stock_code}] majority API error: {e}")
        return None

    if not records:
        return {"top10_inst_count": 0, "top10_inst_proportion": 0, "categories": {}, "date": None}

    # 取最新报告期的数据
    date_groups = defaultdict(list)
    for r in records:
        d = r.get("date", "")
        if isinstance(d, str) and "T" in d:
            d = d.split("T")[0]
        date_groups[d].append(r)

    if not date_groups:
        return {"top10_inst_count": 0, "top10_inst_proportion": 0, "categories": {}, "date": None}

    latest_date = sorted(date_groups.keys())[-1]
    latest_records = date_groups[latest_date]

    # 机构类别
    INST_CATEGORIES = {
        "fund", "qfii", "social_security", "insurance",
        "trust", "brokerage", "other_organisations",
    }
    categories = defaultdict(lambda: {"count": 0, "proportion": 0})
    total_inst_proportion = 0.0
    inst_names = set()

    for r in latest_records:
        cats = r.get("shareholderCategories", [])
        proportion = r.get("proportionOfCapitalization", 0) or 0
        name = r.get("name", "")

        is_inst = False
        for cat in cats:
            if cat in INST_CATEGORIES:
                categories[cat]["count"] += 1
                categories[cat]["proportion"] += proportion
                is_inst = True

        if is_inst and name:
            inst_names.add(name)
            total_inst_proportion += proportion

    return {
        "top10_inst_count": len(inst_names),
        "top10_inst_proportion": round(total_inst_proportion, 4),
        "categories": {k: {"count": v["count"], "proportion": round(v["proportion"], 4)}
                       for k, v in categories.items()},
        "date": latest_date,
    }


def fetch_one_stock(stock_code, start_date, end_date):
    """拉取单只股票的机构持股汇总"""
    fund = fetch_fund_shareholders(stock_code, start_date, end_date)
    majority = fetch_majority_shareholders(stock_code, start_date, end_date)

    # 合并
    result = {
        "fund_count": fund["fund_count"] if fund else 0,
        "fund_proportion_sum": fund["fund_proportion_sum"] if fund else 0,
        "top10_inst_count": majority["top10_inst_count"] if majority else 0,
        "top10_inst_proportion": majority["top10_inst_proportion"] if majority else 0,
        "categories": majority["categories"] if majority else {},
        "fund_date": fund["date"] if fund else None,
        "majority_date": majority["date"] if majority else None,
    }

    # 估算总机构持股：取两者中较大值（避免重复计算）
    result["total_inst_proportion"] = max(
        result["fund_proportion_sum"],
        result["top10_inst_proportion"]
    )

    return result


def save_to_db(stock_code, date_str, result):
    """写入数据库"""
    if not result:
        return
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO stock_institutional_holdings
        (stock_code, date, data_type, fund_count, fund_proportion_sum,
         top10_inst_count, top10_inst_proportion, total_inst_proportion,
         org_categories_json)
        VALUES (?, ?, 'combined', ?, ?, ?, ?, ?, ?)
    """, (
        stock_code, date_str,
        result["fund_count"], result["fund_proportion_sum"],
        result["top10_inst_count"], result["top10_inst_proportion"],
        result["total_inst_proportion"],
        json.dumps(result["categories"], ensure_ascii=False)
    ))
    conn.commit()
    conn.close()


def batch_fetch(stock_codes, start_date, end_date, save=False, delay=0.8):
    """批量拉取"""
    results = {}
    total = len(stock_codes)
    if save:
        init_db()

    for i, code in enumerate(stock_codes):
        try:
            r = fetch_one_stock(code, start_date, end_date)
            results[code] = r
            print(f"  [{i+1}/{total}] {code}: 基金{r['fund_count']}家 "
                  f"占比{r['fund_proportion_sum']*100:.1f}% "
                  f"十大机构{r['top10_inst_count']}家 "
                  f"占比{r['top10_inst_proportion']*100:.1f}%")
            if save:
                save_to_db(code, end_date, r)
        except Exception as e:
            print(f"  [{i+1}/{total}] {code}: ERROR {e}")
            results[code] = None

        if i < total - 1:
            time.sleep(delay)

    return results


def get_top_candidates(limit=500, date_str=None):
    """从 stock_rs_daily 取 RS 评分最高的 N 只股票"""
    conn = sqlite3.connect(DB_PATH)
    if not date_str:
        cur = conn.execute("SELECT MAX(date) FROM stock_rs_daily")
        date_str = cur.fetchone()[0]

    rows = conn.execute("""
        SELECT r.stock_code, b.name, r.rps_250
        FROM stock_rs_daily r
        JOIN stock_basic b ON r.stock_code = b.stock_code
        WHERE r.date = ? AND b.listing_status = 'normally_listed'
          AND b.name NOT LIKE '%ST%' AND b.name NOT LIKE '%*ST%'
        ORDER BY r.rps_250 DESC
        LIMIT ?
    """, (date_str, limit)).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    stock_code = None
    # 机构持股按季度报告，回溯1年覆盖最近4个报告期
    end_date = date.today().strftime("%Y-%m-%d")
    start_date = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    batch_mode = False
    batch_limit = 500
    save_flag = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--batch":
            batch_mode = True
            i += 1
            if i < len(args) and args[i].startswith("top"):
                batch_limit = int(args[i].replace("top", ""))
                i += 1
        elif a == "--save":
            save_flag = True
            i += 1
        elif a == "--date":
            end_date = args[i+1]
            i += 2
        else:
            stock_code = a
            i += 1

    print(f"机构持股拉取: {start_date} ~ {end_date}")
    print(f"API: company/fund-shareholders + company/majority-shareholders")
    print()

    if batch_mode:
        print(f"批量模式: TOP {batch_limit} RS股票")
        candidates = get_top_candidates(batch_limit, end_date)
        print(f"  候选: {len(candidates)} 只")
        codes = [c[0] for c in candidates]

        results = batch_fetch(codes, start_date, end_date, save=save_flag)

        valid = [(code, r) for code, r in results.items() if r]
        print(f"\n汇总: {len(valid)}/{len(results)} 只有机构数据")

        if save_flag:
            print(f"已写入 stock_institutional_holdings 表")

        # TOP 20 by fund count
        sorted_fund = sorted(valid, key=lambda x: x[1]["fund_count"], reverse=True)
        print("\n机构持股 TOP 20 (按基金数):")
        for code, r in sorted_fund[:20]:
            name = next((c[1] for c in candidates if c[0] == code), "?")
            print(f"  {code} {name}: 基金{r['fund_count']}家 "
                  f"十大机构{r['top10_inst_count']}家 "
                  f"占比{r['total_inst_proportion']*100:.1f}%")

    else:
        if not stock_code:
            print("用法: python fetch_institutional_holdings.py <代码>")
            print("      python fetch_institutional_holdings.py --batch top200 --save")
            sys.exit(1)

        print(f"单只模式: {stock_code}")
        r = fetch_one_stock(stock_code, start_date, end_date)
        if r:
            print(f"  基金持股: {r['fund_count']}家, 流通占比 {r['fund_proportion_sum']*100:.1f}%")
            print(f"  十大机构: {r['top10_inst_count']}家, 占比 {r['top10_inst_proportion']*100:.1f}%")
            print(f"  总机构占比: {r['total_inst_proportion']*100:.1f}%")
            if r["categories"]:
                print(f"  机构类别:")
                for cat, info in sorted(r["categories"].items()):
                    print(f"    {cat}: {info['count']}家 占比{info['proportion']*100:.1f}%")
            if save_flag:
                init_db()
                save_to_db(stock_code, end_date, r)
                print(f"  已写入 stock_institutional_holdings")


if __name__ == "__main__":
    main()
