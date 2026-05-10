#!/usr/bin/env python3
"""
补全个股融资融券历史数据（3年）

旧 API: /api/cn/company/margin-trading-and-securities-lending
  支持 dateRange，但每次只查一只股票
新 API: /api/cn/company/hot/mtasl
  批量查 100 只，但只返回最新数据点（无法拉历史）

策略：用旧 API 逐股拉取 3 年日数据，多线程并行。
映射：financingBalance→mtaslb_fb, securitiesBalance→mtaslb_sb,
       financingPurchaseAmount→mtaslb_mc_r

npa (净买入) 和 fb_mc_rc (偿还率) 字段在旧 API 中无直接返回，需另行计算。
"""

import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# ── 项目路径 ──
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))
os.chdir(PROJECT_DIR)

from scripts.common import api_post, get_db, get_all_stock_codes, log, DEFAULT_TIMEOUT

# ── 配置 ──
API_PATH = "/company/margin-trading-and-securities-lending"
YEARS_BACK = 3
WORKERS = 2
BATCH_SIZE = 100  # 每批提交后批量入库

# ── 全局 ──
_total = 0
_success = 0
_failed = 0
_rows_written = 0
_lock = threading.Lock()
_start_time = None


def fetch_one(stock_code, start_date, end_date):
    """拉取单只股票的融资融券历史"""
    payload = {
        "stockCode": stock_code,
        "startDate": start_date,
        "endDate": end_date,
    }
    try:
        result = api_post(API_PATH, payload, timeout=30)
        # API 可能直接返回列表或 {"code":1, "data":[...]}
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict):
            if result.get("code") != 1:
                return stock_code, []
            data = result.get("data", [])
        else:
            return stock_code, []

        if not data:
            return stock_code, []

        rows = []
        for item in data:
            d = item.get("date", "")
            date_str = d[:10] if "T" in d else d
            if not date_str:
                continue

            fb = item.get("financingBalance")
            sb = item.get("securitiesBalance")
            mc_r = item.get("financingPurchaseAmount")
            fsb = item.get("financingSecuritiesBalance")

            if fb is None and sb is None and mc_r is None:
                continue

            rows.append({
                "stock_code": stock_code,
                "date": date_str,
                "mtaslb": fsb,
                "mtaslb_fb": fb,
                "mtaslb_sb": sb,
                "mtaslb_mc_r": mc_r,
            })

        return stock_code, rows

    except Exception as e:
        log.info(f"  ⚠️ {stock_code} 异常: {e}")
        return stock_code, []


def worker(stock_codes, start_date, end_date):
    """线程工作：拉取一批股票，返回所有行"""
    results = []
    for code in stock_codes:
        _, rows = fetch_one(code, start_date, end_date)
        if rows:
            results.extend(rows)
        time.sleep(0.3)  # 限速
    return results


def main():
    global _total, _success, _failed, _rows_written, _start_time
    _start_time = time.time()

    start_date = (datetime.now() - timedelta(days=YEARS_BACK * 365)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"🐺 融资融券历史数据补全")
    log.info(f"   时间范围: {start_date} ~ {end_date}")
    log.info(f"   并发数: {WORKERS}")
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 获取所有活跃股票
    db = get_db()
    codes = get_all_stock_codes(db)
    _total = len(codes)
    log.info(f"活跃股票: {_total} 只")

    # 查出已有数据的股票，跳过
    try:
        existing = db.execute(
            "SELECT DISTINCT stock_code FROM stock_margin WHERE date >= ? AND date <= ?",
            (start_date, end_date)
        ).fetchall()
        existing_codes = {r["stock_code"] for r in existing}
        log.info(f"已有数据: {len(existing_codes)} 只 (跳过)")
    except Exception:
        existing_codes = set()
        log.info("无已有数据，全量拉取")

    to_fetch = [c for c in codes if c not in existing_codes]
    log.info(f"待拉取: {len(to_fetch)} 只")

    if not to_fetch:
        log.info("✅ 数据已完整，无需拉取")
        return

    # 分批多线程
    chunk_size = max(1, len(to_fetch) // WORKERS)
    chunks = [to_fetch[i:i + chunk_size] for i in range(0, len(to_fetch), chunk_size)]
    if len(chunks) > WORKERS:
        chunks = [to_fetch[i::WORKERS] for i in range(WORKERS)]

    buffer = []
    completed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(worker, chunk, start_date, end_date): i for i, chunk in enumerate(chunks)}

        for future in as_completed(futures):
            try:
                rows = future.result()
                with _lock:
                    buffer.extend(rows)
                    completed += 1
                    _success += 1

                    # 批量写入
                    if len(buffer) >= BATCH_SIZE:
                        _write_batch(db, buffer)
                        buffer.clear()

                    elapsed = time.time() - _start_time
                    progress = completed / len(futures) * 100 if futures else 0
                    eta = (elapsed / progress * 100 - elapsed) / 60 if progress > 0 else 0
                    log.info(f"  [{completed}/{len(futures)} 批 · {progress:.0f}%] "
                        f"累计 {_rows_written:,} 行 · ETA {eta:.1f}min")

            except Exception as e:
                with _lock:
                    _failed += 1
                    completed += 1
                    log.info(f"  ❌ 批次失败: {e}")

    # 写入剩余
    if buffer:
        _write_batch(db, buffer)

    elapsed = time.time() - _start_time
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"🐺 完成: {_success} 批成功, {_failed} 批失败, {_rows_written:,} 行, {elapsed:.0f}s")
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 统计覆盖
    stock_count = db.execute(
        "SELECT COUNT(DISTINCT stock_code) FROM stock_margin WHERE date >= ?",
        (start_date,)
    ).fetchone()[0]
    log.info(f"当前覆盖: {stock_count} / {_total} 只")


def _write_batch(db, rows):
    global _rows_written
    if not rows:
        return
    sql = """INSERT OR REPLACE INTO stock_margin
        (stock_code, date, mtaslb, mtaslb_fb, mtaslb_sb, mtaslb_mc_r)
        VALUES (?, ?, ?, ?, ?, ?)"""
    data = [(r["stock_code"], r["date"], r.get("mtaslb"),
             r.get("mtaslb_fb"), r.get("mtaslb_sb"), r.get("mtaslb_mc_r"))
            for r in rows]
    try:
        db.executemany(sql, data)
        db.commit()
        _rows_written += len(data)
    except Exception as e:
        log.info(f"  ⚠️ DB 写入失败: {e}")


if __name__ == "__main__":
    main()
