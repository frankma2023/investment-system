#!/usr/bin/env python3
"""
scripts/fetch_fundamental_nonfinancial.py — 拉取A股所有股票的基本面非财务数据

33 个估值指标：PE/PB/PS/股息率/市值/融资融券/陆股通等，
覆盖时间范围：最近 10 年（可通过 --start / --end 自定义）。

用法：
    python scripts/fetch_fundamental_nonfinancial.py                           # 拉取最近 10 年
    python scripts/fetch_fundamental_nonfinancial.py --start 2020-01-01        # 从指定日期起
    python scripts/fetch_fundamental_nonfinancial.py --start 2024-01-01 --end 2025-12-31
    python scripts/fetch_fundamental_nonfinancial.py --incremental             # 增量更新
    python scripts/fetch_fundamental_nonfinancial.py --workers 8               # 8 线程并发

原理：
    使用理杏仁 API /company/fundamental/non_financial 的 startDate/endDate 模式，
    每只股票一次调用拉取其历史数据。33 个指标 < 36 限制，无需拆分。
    跨度超过 9 年时自动切分为多次调用（API 限制 ≤10 年）。
"""

import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from common import api_post, get_db, get_all_stock_codes, get_latest_date, log, DEFAULT_TIMEOUT

# ── 配置 ──────────────────────────────────────────────
API_PATH = "/company/fundamental/non_financial"

# 33 个估值指标（API 26 — metricsList 估值指标 全部）
METRICS = [
    # 估值
    "pe_ttm", "d_pe_ttm", "pb", "pb_wo_gw", "ps_ttm", "dyr",
    "pcf_ttm", "ev_ebit_r", "ev_ebitda_r", "ey",
    # 价量
    "sp", "spc", "spa", "tv", "ta", "to_r",
    # 股东 / 市值
    "shn", "mc", "mc_om", "cmc", "ecmc", "ecmc_psh",
    # 融资融券
    "fpa", "fra", "fnpa", "fb", "ssa", "sra", "snsa", "sb",
    # 陆股通
    "ha_sh", "ha_shm", "mm_nba",
]

UPSERT_SQL = """INSERT OR REPLACE INTO fundamental_indicator
    (stock_code, date, metric_code, value)
    VALUES (?, ?, ?, ?)"""

# API 限制 startDate～endDate ≤ 10 年，留 1 年余量
MAX_SPAN_YEARS = 9

# 默认并发数（0 = 串行，兼容旧行为）
DEFAULT_WORKERS = 5

# 写锁 — 保证多线程写 DB 互斥
_write_lock = threading.Lock()

# ── 辅助函数 ──────────────────────────────────────────

def parse_date_arg(argv: list, flag: str) -> str | None:
    """从命令行参数提取日期值"""
    try:
        idx = argv.index(flag)
        return argv[idx + 1]
    except (ValueError, IndexError):
        return None


def parse_int_arg(argv: list, flag: str, default: int) -> int:
    """从命令行参数提取整数值"""
    try:
        idx = argv.index(flag)
        return int(argv[idx + 1])
    except (ValueError, IndexError):
        return default


def generate_year_slices(start: str, end: str) -> list:
    """将日期范围切分为 ≤9 年的片段"""
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    slices = []
    cur = s
    while cur < e:
        slice_end = min(
            cur.replace(year=cur.year + MAX_SPAN_YEARS) - timedelta(days=1),
            e,
        )
        # 确保 slice_end >= cur（处理跨年）
        if slice_end < cur:
            slice_end = cur
        slices.append((cur.strftime("%Y-%m-%d"), slice_end.strftime("%Y-%m-%d")))
        cur = slice_end + timedelta(days=1)
    return slices


def fetch_stock_fundamentals(stock_code: str, start_date: str, end_date: str) -> list:
    """拉取单只股票在日期范围内的全部 33 个指标"""
    payload = {
        "stockCodes": [stock_code],
        "startDate": start_date,
        "endDate": end_date,
        "metricsList": METRICS,
    }
    return api_post(API_PATH, payload)


def data_to_rows(data: list) -> list:
    """将 API 返回数据转为 EAV 行列表（不写库，线程安全）"""
    if not data:
        return []
    rows = []
    for record in data:
        stock_code = record["stockCode"]
        date = record["date"][:10]  # "2026-03-10T00:00:00+08:00" → "2026-03-10"
        for metric in METRICS:
            value = record.get(metric)
            if value is not None:
                rows.append((stock_code, date, metric, float(value)))
    return rows


def save_indicators(conn, rows: list) -> int:
    """将 EAV 行写入 fundamental_indicator（调用方负责加锁）"""
    if not rows:
        return 0
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()
    return len(rows)


def fetch_one_stock(code: str, year_slices: list) -> tuple:
    """
    拉取单只股票全部时间片的数据，返回 (stock_code, rows, success)。

    在 worker 线程中调用，不涉及 DB 写入。
    """
    all_rows = []
    for s_start, s_end in year_slices:
        try:
            data = fetch_stock_fundamentals(code, s_start, s_end)
            rows = data_to_rows(data)
            all_rows.extend(rows)
        except Exception as e:
            log.error(f"{code} ({s_start}→{s_end}) ❌ {e}")
            return (code, [], False)
    return (code, all_rows, True)


# ════════════════════════════════════════════════════════

def main():
    conn = get_db()

    # ── 解析参数 ──────────────────────────────────────
    arg_start = parse_date_arg(sys.argv, "--start")
    arg_end = parse_date_arg(sys.argv, "--end")
    incremental = "--incremental" in sys.argv
    workers = parse_int_arg(sys.argv, "--workers", DEFAULT_WORKERS)

    stocks = get_all_stock_codes(conn)
    log.info(f"📊 股票总数: {len(stocks)}")

    # ── 确定日期范围 ──────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")

    if incremental:
        latest = get_latest_date(conn, "fundamental_indicator")
        if latest:
            start_date = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            log.info(f"📅 增量模式：最新数据日期 {latest}，从 {start_date} 开始")
        else:
            start_date = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
            log.info(f"📅 增量模式：无历史数据，从 {start_date} 开始全量")
        end_date = arg_end or today
    elif arg_start:
        start_date = arg_start
        end_date = arg_end or today
        log.info(f"📅 自定义范围: {start_date} → {end_date}")
    else:
        start_date = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
        end_date = today
        log.info(f"📅 默认 10 年: {start_date} → {end_date}")

    # ── 切分时间跨度 ──────────────────────────────────
    year_slices = generate_year_slices(start_date, end_date)
    if len(year_slices) > 1:
        log.info(f"⏳ 时间跨度 >{MAX_SPAN_YEARS}年，切分为 {len(year_slices)} 段")

    # ── 模式选择 ──────────────────────────────────────
    if workers <= 1:
        log.info(f"🔄 串行模式（--workers 1）")
        run_sequential(conn, stocks, year_slices)
    else:
        log.info(f"⚡ 并发模式：{workers} workers")
        run_concurrent(conn, stocks, year_slices, workers)

    # ── 汇总 ──────────────────────────────────────────
    # 打印表统计
    row = conn.execute("SELECT COUNT(*) as cnt FROM fundamental_indicator").fetchone()
    log.info(f"   fundamental_indicator 表总计: {row['cnt']:,} 条记录")

    conn.close()


def run_sequential(conn, stocks, year_slices):
    """原始串行逻辑（--workers 0 或未指定时使用）"""
    total_rows = 0
    success = 0
    fail = 0
    t_start = time.time()

    for i, code in enumerate(stocks, 1):
        stock_rows = 0
        stock_fail = False

        for s_start, s_end in year_slices:
            try:
                data = fetch_stock_fundamentals(code, s_start, s_end)
                n = save_indicators(conn, data_to_rows(data))
                stock_rows += n
            except Exception as e:
                log.error(f"[{i}/{len(stocks)}] {code} ({s_start}→{s_end}) ❌ {e}")
                stock_fail = True
                break  # 不继续该股票的其他时间分片

        if stock_fail:
            fail += 1
        else:
            success += 1
            total_rows += stock_rows

        # 进度报告：每 100 只或首尾打印
        if i % 100 == 0 or i == 1 or i == len(stocks):
            elapsed = time.time() - t_start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(stocks) - i) / rate if rate > 0 else 0
            log.info(
                f"[{i}/{len(stocks)}] {code} ✅ {stock_rows} 行 "
                f"| 累计 {total_rows:,} | 速度 {rate:.1f} 股/s | ETA {eta:.0f}s"
            )

    elapsed = time.time() - t_start
    log.info(f"🏁 完成: {success} 成功, {fail} 失败, {total_rows:,} 行, 耗时 {elapsed:.0f}s")


def run_concurrent(conn, stocks, year_slices, workers):
    """
    多线程并发拉取。

    策略：
    - Worker 线程拉取 API 数据并转为 EAV 行（纯 I/O + CPU，线程安全）
    - 主线程收集结果后写 DB（避免 SQLite 写冲突）
    - 批量写入减少 commit 次数
    """
    total_rows = 0
    success = 0
    fail = 0
    t_start = time.time()
    completed = 0
    total = len(stocks)

    # 批量写入阈值：每收集 BATCH_SIZE 只股票的数据就写一次
    BATCH_SIZE = max(50, workers * 5)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # 提交所有任务
        futures = {
            executor.submit(fetch_one_stock, code, year_slices): code
            for code in stocks
        }

        pending_rows = []  # 待写入的 EAV 行

        for future in as_completed(futures):
            code = futures[future]
            completed += 1

            try:
                stock_code, rows, ok = future.result()
                if ok:
                    success += 1
                    total_rows += len(rows)
                    pending_rows.extend(rows)
                else:
                    fail += 1
            except Exception as e:
                log.error(f"{code} ❌ worker 异常: {e}")
                fail += 1

            # 批量写入
            if len(pending_rows) >= BATCH_SIZE * 33 * len(year_slices):  # 粗略阈值
                with _write_lock:
                    save_indicators(conn, pending_rows)
                pending_rows = []

            # 进度报告
            if completed % 100 == 0 or completed == 1 or completed == total:
                elapsed = time.time() - t_start
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (total - completed) / rate if rate > 0 else 0
                log.info(
                    f"[{completed}/{total}] {code} "
                    f"| 成功 {success} 失败 {fail} | 累计 {total_rows:,} 行 "
                    f"| 速度 {rate:.1f} 股/s | ETA {eta:.0f}s"
                )

        # 写入剩余数据
        if pending_rows:
            with _write_lock:
                save_indicators(conn, pending_rows)

    elapsed = time.time() - t_start
    log.info(f"🏁 完成: {success} 成功, {fail} 失败, {total_rows:,} 行, 耗时 {elapsed:.0f}s")


if __name__ == "__main__":
    main()
