#!/usr/bin/env python
"""
scripts/fetch_equity_change.py — 拉取全量股票股本变动数据

从理杏仁 /company/equity-change API 拉取所有 A 股近 10 年股本变动记录，
存入 stock_equity_change 表。每只股票一次 API 调用（10年区间）。

用法：
    python scripts/fetch_equity_change.py              # 全量拉取
    python scripts/fetch_equity_change.py --test       # 测试：仅 10 只股票
    python scripts/fetch_equity_change.py --incremental # 增量更新
    python scripts/fetch_equity_change.py --workers 4  # 4 线程并发
"""

import os
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from common import api_post, get_db, get_all_stock_codes, log

# ── 配置 ──────────────────────────────────────────────
API_PATH = "/company/equity-change"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CREATE_TABLE_SQL = """CREATE TABLE IF NOT EXISTS stock_equity_change (
    stock_code         TEXT NOT NULL,
    date               TEXT NOT NULL,
    declaration_date   TEXT,
    change_reason      TEXT,
    capitalization     REAL,       -- 总股本
    outstanding_a      REAL,       -- 流通A股
    limited_a          REAL,       -- 限售A股
    outstanding_h      REAL,       -- 流通H股
    cap_change_ratio   REAL,       -- 总股本变动比例
    outstanding_a_ratio REAL,      -- 流通A股变动比例
    limited_a_ratio    REAL,       -- 限售A股变动比例
    outstanding_h_ratio REAL,      -- 流通H股变动比例
    updated_at         TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, date)
)"""

UPSERT_SQL = """INSERT OR REPLACE INTO stock_equity_change
    (stock_code, date, declaration_date, change_reason,
     capitalization, outstanding_a, limited_a, outstanding_h,
     cap_change_ratio, outstanding_a_ratio, limited_a_ratio, outstanding_h_ratio)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


# ════════════════════════════════════════════════════════

def fetch_one_stock(stock_code, start_date="2016-01-01", end_date=None):
    """拉取单只股票 10 年内的股本变动"""
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    payload = {
        "stockCode": stock_code,
        "startDate": start_date,
        "endDate": end_date,
    }
    return api_post(API_PATH, payload)


def save_equity(conn, stock_code, data):
    """写入股本变动数据"""
    rows = []
    for item in data:
        date_str = item["date"][:10]
        decl_date = item.get("declarationDate", "")
        if decl_date and len(decl_date) > 10:
            decl_date = decl_date[:10]

        rows.append((
            stock_code,
            date_str,
            decl_date if decl_date else None,
            item.get("changeReason"),
            item.get("capitalization"),
            item.get("outstandingSharesA"),
            item.get("limitedSharesA"),
            item.get("outstandingSharesH"),
            item.get("capitalizationChangeRatio"),
            item.get("outstandingSharesAChangeRatio"),
            item.get("limitedSharesAChangeRatio"),
            item.get("outstandingSharesHChangeRatio"),
        ))

    if rows:
        conn.executemany(UPSERT_SQL, rows)
        conn.commit()
    return len(rows)


def fetch_all(codes, test_mode=False, incremental=False, workers=1, conn=None):
    """拉取所有股票股本变动"""
    total_rows = 0
    end_date = datetime.now().strftime("%Y-%m-%d")

    if test_mode:
        codes = codes[:10]
        log.info(f"测试模式：{len(codes)} 只股票")

    if workers > 1:
        # 多线程
        def worker(code):
            try:
                data = fetch_one_stock(code, end_date=end_date)
                return code, data, None
            except Exception as e:
                return code, [], str(e)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(worker, c): c for c in codes}
            for idx, future in enumerate(as_completed(futures)):
                code = futures[future]
                code_name, data, error = future.result()
                if error:
                    log.error(f"  [{idx+1}/{len(codes)}] {code_name} 失败: {error}")
                    continue
                n = save_equity(conn, code_name, data)
                total_rows += n
                if (idx + 1) % 100 == 0 or idx == 0:
                    log.info(f"  [{idx+1}/{len(codes)}] {code_name} +{n} 条 (累计 {total_rows})")
    else:
        # 单线程
        for idx, code in enumerate(codes):
            label = f"[{idx+1}/{len(codes)}] {code}"
            try:
                data = fetch_one_stock(code, end_date=end_date)
                n = save_equity(conn, code, data)
                total_rows += n
                if (idx + 1) % 200 == 0 or idx == 0:
                    log.info(f"  {label} +{n} 条 (累计 {total_rows})")
            except Exception as e:
                log.error(f"  {label} 失败: {e}")
                continue

    return total_rows


# ════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="拉取全量股本变动数据")
    parser.add_argument("--test", action="store_true", help="测试模式：仅 10 只股票")
    parser.add_argument("--incremental", action="store_true", help="增量更新")
    parser.add_argument("--workers", type=int, default=1, help="并发线程数（默认1）")
    args = parser.parse_args()

    conn = get_db()
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    codes = get_all_stock_codes(conn)
    log.info(f"共 {len(codes)} 只股票待拉取")

    total = fetch_all(codes, test_mode=args.test,
                      incremental=args.incremental,
                      workers=args.workers, conn=conn)
    log.info(f"完成！共写入 {total} 行数据到 stock_equity_change")
    conn.close()


if __name__ == "__main__":
    main()
