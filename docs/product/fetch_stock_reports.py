"""
东方财富个股研报数据拉取（优化版）

API: reportapi.eastmoney.com/report/list
功能: 多页翻取 + 入库 + 首次覆盖/评级变化统计

用法:
  python fetch_stock_reports.py 600519                 # 单只股票
  python fetch_stock_reports.py --batch top500         # 批量 TOP500 RS股票
  python fetch_stock_reports.py --batch top100 --save  # 批量+入库
  python fetch_stock_reports.py --date 2026-05-14 --days 90
"""

import requests
import json
import sys
import time
import sqlite3
import os
import re
from datetime import datetime, timedelta, date
from collections import Counter

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 适配 docs/product/ → 项目根
PROJECT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")
API_URL = "https://reportapi.eastmoney.com/report/list"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# 建表SQL
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_analyst_reports (
    stock_code      TEXT NOT NULL,
    date            TEXT NOT NULL,          -- 统计日期
    lookback_days   INTEGER NOT NULL,       -- 回溯天数
    report_count    INTEGER DEFAULT 0,      -- 研报总数
    org_count       INTEGER DEFAULT 0,      -- 覆盖机构数
    first_coverage  INTEGER DEFAULT 0,      -- 是否有首次覆盖 (0/1)
    upgrade_count   INTEGER DEFAULT 0,      -- 上调评级数
    downgrade_count INTEGER DEFAULT 0,      -- 下调评级数
    maintain_count  INTEGER DEFAULT 0,      -- 维持评级数
    buy_count       INTEGER DEFAULT 0,      -- 买入/推荐数量
    overweight_count INTEGER DEFAULT 0,     -- 增持数量
    neutral_count   INTEGER DEFAULT 0,      -- 中性/持有数量
    reduce_count    INTEGER DEFAULT 0,      -- 减持数量
    orgs_json       TEXT,                   -- 机构名称列表 JSON
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, date, lookback_days)
);
"""

# ═══════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════

def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    conn.close()


def fetch_one_stock(stock_code, begin_date, end_date):
    """
    拉取单只股票在日期范围内的全部研报（多页翻取）。

    返回: {
        'report_count': int,
        'org_count': int,
        'orgs': [str],              # 机构简称列表
        'first_coverage': bool,
        'upgrade_count': int,
        'downgrade_count': int,
        'maintain_count': int,
        'rating_dist': {name: count},
    } 或 None
    """
    all_records = []
    page = 1
    max_pages = 20  # 安全上限

    session = requests.Session()
    session.headers.update(HEADERS)

    while page <= max_pages:
        params = {
            "industryCode": "*",
            "pageSize": "500",
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": begin_date,
            "endTime": end_date,
            "pageNo": str(page),
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": stock_code,
            "rcode": "",
        }
        try:
            r = session.get(API_URL, params=params, timeout=30)
            d = r.json()
        except Exception as e:
            print(f"  [{stock_code}] 请求失败 (page={page}): {e}")
            break

        if not d or "data" not in d:
            break

        records = d.get("data", [])
        if not records:
            break

        all_records.extend(records)

        # 检查是否还有下一页
        total_pages = d.get("TotalPage", d.get("totalPage", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)  # 翻页间隙

    if not all_records:
        return None

    # ── 统计 ──
    orgs = set()
    first_coverage = False
    rating_change_counter = Counter()
    rating_name_counter = Counter()

    for rec in all_records:
        # 机构
        org_name = rec.get("orgSName", rec.get("orgName", ""))
        if org_name:
            orgs.add(org_name)

        # 首次覆盖: indvIsNew 为空字符串 = 首次
        if rec.get("indvIsNew", "001") == "":
            first_coverage = True

        # 评级变化: 1=下调, 2=上调, 3=维持, 其他=未知
        rc = rec.get("ratingChange", "")
        # API返回可能是int或str
        try:
            rc_int = int(rc) if rc != "" else 0
        except (ValueError, TypeError):
            rc_int = 0
        if rc_int == 1:
            rating_change_counter["downgrade"] += 1
        elif rc_int == 2:
            rating_change_counter["upgrade"] += 1
        elif rc_int == 3:
            rating_change_counter["maintain"] += 1
        else:
            rating_change_counter["unknown"] += 1

        # 评级名称
        rn = rec.get("emRatingName", rec.get("sRatingName", ""))
        if rn:
            rating_name_counter[rn] += 1

    # 映射评级名称到买入/增持/中性等
    buy_count = 0
    overweight_count = 0
    neutral_count = 0
    reduce_count = 0
    for name, cnt in rating_name_counter.items():
        name_lower = name.lower() if isinstance(name, str) else ""
        if any(w in name for w in ["买入", "推荐", "强推", "buy"]):
            buy_count += cnt
        elif any(w in name for w in ["增持", "outperform", "overweight"]):
            overweight_count += cnt
        elif any(w in name for w in ["中性", "持有", "neutral", "hold"]):
            neutral_count += cnt
        elif any(w in name for w in ["减持", "卖出", "reduce", "sell"]):
            reduce_count += cnt

    return {
        "report_count": len(all_records),
        "org_count": len(orgs),
        "orgs": sorted(orgs),
        "first_coverage": first_coverage,
        "upgrade_count": rating_change_counter.get("upgrade", 0),
        "downgrade_count": rating_change_counter.get("downgrade", 0),
        "maintain_count": rating_change_counter.get("maintain", 0),
        "buy_count": buy_count,
        "overweight_count": overweight_count,
        "neutral_count": neutral_count,
        "reduce_count": reduce_count,
    }


def save_to_db(stock_code, date_str, lookback_days, result):
    """将单只股票的研报统计写入数据库"""
    if not result:
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO stock_analyst_reports
        (stock_code, date, lookback_days, report_count, org_count,
         first_coverage, upgrade_count, downgrade_count, maintain_count,
         buy_count, overweight_count, neutral_count, reduce_count, orgs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        stock_code, date_str, lookback_days,
        result["report_count"], result["org_count"],
        1 if result["first_coverage"] else 0,
        result["upgrade_count"], result["downgrade_count"],
        result["maintain_count"],
        result["buy_count"], result["overweight_count"],
        result["neutral_count"], result["reduce_count"],
        json.dumps(result["orgs"], ensure_ascii=False)
    ))
    conn.commit()
    conn.close()


def batch_fetch(stock_codes, begin_date, end_date, save=False, delay=0.6):
    """批量拉取"""
    results = {}
    total = len(stock_codes)
    lookback_days = (datetime.strptime(end_date, "%Y-%m-%d") -
                     datetime.strptime(begin_date, "%Y-%m-%d")).days

    if save:
        init_db()

    for i, code in enumerate(stock_codes):
        r = fetch_one_stock(code, begin_date, end_date)
        if r:
            results[code] = r
            print(f"  [{i+1}/{total}] {code}: {r['report_count']}篇, {r['org_count']}家"
                  f"{' 🔥首次覆盖' if r['first_coverage'] else ''}"
                  f"{' ↑'+str(r['upgrade_count']) if r['upgrade_count'] else ''}")
            if save:
                save_to_db(code, end_date, lookback_days, r)
        else:
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
    return [(r[0], r[1], r[2]) for r in rows]


# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    stock_code = None
    begin_date = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    end_date = date.today().strftime("%Y-%m-%d")
    batch_mode = False
    batch_limit = 500
    save_to_db_flag = False

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
            save_to_db_flag = True
            i += 1
        elif a == "--days":
            days = int(args[i+1])
            begin_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
            i += 2
        elif a == "--date":
            end_date = args[i+1]
            i += 2
        else:
            stock_code = a
            i += 1

    lookback_days = (datetime.strptime(end_date, "%Y-%m-%d") -
                     datetime.strptime(begin_date, "%Y-%m-%d")).days

    print(f"研报拉取: {begin_date} ~ {end_date} ({lookback_days}天)")
    print(f"API: {API_URL}")
    print()

    if batch_mode:
        print(f"批量模式: TOP {batch_limit} RS股票")
        candidates = get_top_candidates(batch_limit, end_date)
        print(f"  候选: {len(candidates)} 只")
        codes = [c[0] for c in candidates]

        results = batch_fetch(codes, begin_date, end_date, save=save_to_db_flag)

        # 汇总
        valid = [(code, r) for code, r in results.items() if r]
        with_report = len(valid)
        print(f"\n汇总: {with_report}/{len(results)} 只有研报")

        # 首次覆盖
        first_cov = [(code, r) for code, r in valid if r["first_coverage"]]
        print(f"首次覆盖: {len(first_cov)} 只")

        if save_to_db_flag:
            print(f"已写入 stock_analyst_reports 表")

        # TOP 20
        sorted_results = sorted(valid, key=lambda x: x[1]["report_count"], reverse=True)
        print("\n研报数量 TOP 20:")
        for code, r in sorted_results[:20]:
            name = next((c[1] for c in candidates if c[0] == code), "?")
            print(f"  {code} {name}: {r['report_count']}篇, {r['org_count']}家"
                  f"{' 🔥首次' if r['first_coverage'] else ''}")

    else:
        if not stock_code:
            print("用法: python fetch_stock_reports.py <代码>")
            print("      python fetch_stock_reports.py --batch top500 --save")
            sys.exit(1)

        print(f"单只模式: {stock_code}")
        r = fetch_one_stock(stock_code, begin_date, end_date)
        if r:
            print(f"  研报: {r['report_count']}篇")
            print(f"  机构: {r['org_count']}家")
            print(f"  首次覆盖: {'是' if r['first_coverage'] else '否'}")
            print(f"  评级变化: 上调{r['upgrade_count']} 下调{r['downgrade_count']} 维持{r['maintain_count']}")
            print(f"  评级分布: 买入{r['buy_count']} 增持{r['overweight_count']} 中性{r['neutral_count']} 减持{r['reduce_count']}")
            if r["orgs"]:
                print(f"  机构列表: {', '.join(r['orgs'][:10])}{' ...' if len(r['orgs'])>10 else ''}")

            if save_to_db_flag:
                init_db()
                save_to_db(stock_code, end_date, lookback_days, r)
                print(f"  已写入 stock_analyst_reports")
        else:
            print(f"  无数据")


if __name__ == "__main__":
    main()
