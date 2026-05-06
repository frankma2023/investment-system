#!/usr/bin/env python3
"""
scripts/fetch_index_constituents.py — 拉取指数成分股 & 权重数据（按月快照）

从 config/index_style.yaml 读取指数清单，拉取：
  1. 成分股列表 (index_constituents) — 每月快照
  2. 成分股权重 (index_constituent_weightings) — 区间查询

用法：
    python scripts/fetch_index_constituents.py                          # 默认：全部 408 个指数
    python scripts/fetch_index_constituents.py --category market        # 仅全市场指数
    python scripts/fetch_index_constituents.py --category market,sector_l1
    python scripts/fetch_index_constituents.py --constituents-only      # 仅拉取成分股
    python scripts/fetch_index_constituents.py --weightings-only        # 仅拉取权重
    python scripts/fetch_index_constituents.py --months 24              # 覆盖最近 24 个月
    python scripts/fetch_index_constituents.py --dry-run                # 仅统计不写入

API 参考：
    /index/constituents           — 批量查询成分股 (stockCodes[], date)
    /index/constituent-weightings — 单指数权重区间 (stockCode, startDate, endDate)
"""

import os
import sys
import yaml
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from common import api_post, get_db, log

# ── 配置路径 ──────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "index_style.yaml")

# ── API 路径 ──────────────────────────────────────────
API_CONSTITUENTS = "/index/constituents"
API_WEIGHTINGS = "/index/constituent-weightings"

# ── 批量参数 ──────────────────────────────────────────
CONSTITUENTS_BATCH_SIZE = 100   # API 单次最多 100 个指数
WEIGHTINGS_MAX_YEARS = 9        # 权重 API 单次区间 ≤10 年，取 9 年安全

# ── SQL ───────────────────────────────────────────────
UPSERT_CONSTITUENT = """INSERT OR REPLACE INTO index_constituents
    (index_code, stock_code, date) VALUES (?, ?, ?)"""

UPSERT_WEIGHTING = """INSERT OR REPLACE INTO index_constituent_weightings
    (index_code, stock_code, date, weighting) VALUES (?, ?, ?, ?)"""


# ════════════════════════════════════════════════════════
# 指数配置加载
# ════════════════════════════════════════════════════════

def load_indices(categories: list = None) -> dict:
    """从 index_style.yaml 加载指数，返回 {code: name}。
    categories=None 时加载全部。
    """
    with open(CONFIG_PATH, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    cats = data.get("categories", {})
    result = {}
    for cat_name, indices in cats.items():
        if categories and cat_name not in categories:
            continue
        for item in indices:
            result[item["code"]] = item["name"]
    return result

# ════════════════════════════════════════════════════════
# 日期生成
# ════════════════════════════════════════════════════════

def monthly_snapshot_dates(months: int = 12) -> list:
    """生成最近 N 个月的快照日期（每月 1 号）。
    返回格式 ['2025-05-01', '2025-06-01', ..., '2026-05-01']
    """
    today = datetime.now()
    dates = []
    for i in range(months):
        d = today - relativedelta(months=i)
        dates.append(d.replace(day=1).strftime("%Y-%m-%d"))
    dates.sort()
    return dates

# ════════════════════════════════════════════════════════
# 成分股拉取
# ════════════════════════════════════════════════════════

def fetch_constituents_batch(index_codes: list, date: str) -> list:
    """批量拉取成分股：stockCodes 最多 100 个，指定日期。
    返回: [{stockCode, constituents: [{stockCode, ...}]}, ...]
    """
    payload = {"stockCodes": index_codes, "date": date}
    return api_post(API_CONSTITUENTS, payload)


def save_constituents(conn, data: list, date: str) -> int:
    """写入 index_constituents 表。data 是 API 响应数组。"""
    rows = []
    for item in data:
        index_code = item["stockCode"]
        for c in item.get("constituents", []):
            rows.append((index_code, c["stockCode"], date))
    if rows:
        conn.executemany(UPSERT_CONSTITUENT, rows)
        conn.commit()
    return len(rows)


def fetch_all_constituents(conn, indices: dict, dates: list,
                            dry_run: bool = False) -> int:
    """拉取所有指数的月度成分股快照。
    将 indices 分批（每批 100 个），逐日拉取。
    """
    codes = sorted(indices.keys())
    batches = [codes[i:i + CONSTITUENTS_BATCH_SIZE]
               for i in range(0, len(codes), CONSTITUENTS_BATCH_SIZE)]

    total = 0
    for date in dates:
        for batch in batches:
            label = f"({batch[0]}…{batch[-1]})" if len(batch) > 1 else f"({batch[0]})"
            if dry_run:
                log.info(f"  [DRY] /constituents date={date} codes={label}")
                continue
            try:
                data = fetch_constituents_batch(batch, date)
                n = save_constituents(conn, data, date)
                total += n
                log.info(f"  {date} {label}: +{n} 成分股")
            except Exception as e:
                log.error(f"  {date} {label}: ❌ {e}")
    return total


# ════════════════════════════════════════════════════════
# 权重拉取
# ════════════════════════════════════════════════════════

def fetch_weightings(index_code: str, start_date: str, end_date: str) -> list:
    """拉取单指数的历史权重（区间查询）。
    返回: [{date, stockCode, weighting}, ...]
    """
    payload = {
        "stockCode": index_code,
        "startDate": start_date,
        "endDate": end_date,
    }
    return api_post(API_WEIGHTINGS, payload)


def fetch_weightings_batched(index_code: str, start_date: str, end_date: str) -> list:
    """分批拉取权重，每批 ≤9 年（API 限制 10 年）"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    span = (end - start).days

    if span <= WEIGHTINGS_MAX_YEARS * 365:
        return fetch_weightings(index_code, start_date, end_date)

    all_data = []
    chunk_delta = timedelta(days=WEIGHTINGS_MAX_YEARS * 365)
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + chunk_delta, end)
        s = chunk_start.strftime("%Y-%m-%d")
        e = chunk_end.strftime("%Y-%m-%d")
        try:
            chunk = fetch_weightings(index_code, s, e)
            all_data.extend(chunk)
        except Exception:
            pass  # 某批失败不中断整体
        chunk_start = chunk_end + timedelta(days=1)

    # 去重
    seen = set()
    deduped = []
    for r in all_data:
        key = (r["date"][:10], r["stockCode"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def save_weightings(conn, index_code: str, data: list) -> int:
    """写入 index_constituent_weightings 表"""
    rows = []
    for r in data:
        rows.append((
            index_code,
            r["stockCode"],
            r["date"][:10],
            r.get("weighting"),
        ))
    if rows:
        conn.executemany(UPSERT_WEIGHTING, rows)
        conn.commit()
    return len(rows)


def fetch_all_weightings(conn, indices: dict, start_date: str, end_date: str,
                          dry_run: bool = False) -> int:
    """拉取所有指数的权重数据（每个指数 1 次 API 调用）。"""
    total = 0
    for idx_code, idx_name in indices.items():
        if dry_run:
            log.info(f"  [DRY] /weightings {idx_code} {idx_name}: {start_date}~{end_date}")
            continue
        try:
            data = fetch_weightings_batched(idx_code, start_date, end_date)
            n = save_weightings(conn, idx_code, data)
            total += n
            log.info(f"  {idx_code} {idx_name}: +{n} 权重 {start_date}~{end_date}")
        except Exception as e:
            log.error(f"  {idx_code} {idx_name}: ❌ {e}")
    return total


# ════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════

def main():
    # ── 解析参数 ──────────────────────────────────────────
    args = sys.argv[1:]

    constituents_only = "--constituents-only" in args
    weightings_only = "--weightings-only" in args
    dry_run = "--dry-run" in args

    # months
    months = 12
    for i, a in enumerate(args):
        if a == "--months" and i + 1 < len(args):
            months = int(args[i + 1])

    # categories
    VALID_CATS = {"market", "sector_l1", "sector_l2", "thematic", "strategy"}
    selected_cats = None
    for i, a in enumerate(args):
        if a.startswith("--category="):
            selected_cats = [c.strip() for c in a.split("=", 1)[1].split(",")]
        elif a == "--category" and i + 1 < len(args):
            selected_cats = [c.strip() for c in args[i + 1].split(",")]
    if selected_cats:
        selected_cats = [c for c in selected_cats if c in VALID_CATS]
        if not selected_cats:
            log.error(f"无效分类，支持: {', '.join(sorted(VALID_CATS))}")
            return

    # ── 加载指数 ──────────────────────────────────────────
    indices = load_indices(selected_cats)
    log.info("📋 加载 %d 个指数%s",
             len(indices),
             f" (分类: {', '.join(selected_cats)})" if selected_cats else " (全部分类)")
    if not indices:
        log.error("没有匹配的指数！")
        return

    # ── 生成日期 ──────────────────────────────────────────
    dates = monthly_snapshot_dates(months)
    log.info("📅 %d 个月度快照: %s → %s", len(dates), dates[0], dates[-1])

    conn = None if dry_run else get_db()

    # ── 拉取成分股 ────────────────────────────────────────
    if not weightings_only:
        log.info("=" * 60)
        log.info("📊 拉取成分股 (index_constituents)")
        n = fetch_all_constituents(conn, indices, dates, dry_run)
        log.info("🏁 成分股完成: +%d 条", n)

    # ── 拉取权重 ──────────────────────────────────────────
    if not constituents_only:
        log.info("=" * 60)
        log.info("📊 拉取权重 (index_constituent_weightings)")
        start_date = dates[0]
        end_date = datetime.now().strftime("%Y-%m-%d")
        log.info("   时间范围: %s → %s", start_date, end_date)
        n = fetch_all_weightings(conn, indices, start_date, end_date, dry_run)
        log.info("🏁 权重完成: +%d 条", n)

    if conn:
        conn.close()
    log.info("🎉 全部完成")


if __name__ == "__main__":
    main()
