#!/usr/bin/env python3
"""
scripts/fetch_index_daily_kline.py — 增量拉取A股主要指数日K线

用法：
    python scripts/fetch_index_daily_kline.py                        # 增量更新（默认）
    python scripts/fetch_index_daily_kline.py --all                  # 拉取全部3层指数
    python scripts/fetch_index_daily_kline.py --tier-1               # 仅拉取全市场指数
    python scripts/fetch_index_daily_kline.py --start 2015-01-01     # 指定起始日期
    python scripts/fetch_index_daily_kline.py --start 2010-01-01 --end 2020-12-31

注意：理杏仁API限制单次请求不超过10年。超过10年的区间会自动分批拉取。

指数定义：参见 docs/指数定义.md
- 层级一（全市场）：000985, 000001, 399001
- 层级二（风格）：000016, 000300, 000905, 399006, 000688, 000852
- 层级三（行业）：000949, 000813, H30463, 930606, ... (共30个)

指数K线保存到 index_daily_kline 表（独立于股票 daily_kline）。
"""

import sys
from datetime import datetime, timedelta
from common import api_post, get_db, get_latest_date, log

# ── 指数定义 ──────────────────────────────────────────
# 参见 docs/指数定义.md

INDICES_TIER1 = {  # 全市场指数
    "000985": "中证全指",
    "000001": "上证指数",
    "399001": "深证成指",
}

INDICES_TIER2 = {  # 风格指数
    "000016": "上证50",
    "000300": "沪深300",
    "000905": "中证500",
    "399006": "创业板指",
    "000688": "科创50",
    "000852": "中证1000",
}

INDICES_TIER3 = {  # 行业指数
    "000949": "中证农业",
    "000813": "中证细分化工",
    "H30463": "沪港深医药",
    "930606": "中证钢铁",
    "930708": "中证有色",
    "931494": "中证消费电子",
    "930653": "中证食品饮料",
    "930697": "中证家用电器",
    "000932": "中证消费800",
    "000806": "中证消费服务",
    "000995": "中证全指公用",
    "000945": "中证内地运输",
    "931775": "中证房地产",
    "399986": "中证银行",
    "931479": "中证证券保险",
    "930651": "中证计算机",
    "H30318": "中证科技传媒通信",
    "931160": "中证通信设备",
    "931066": "中证军工龙头",
    "931752": "中证工程机械主题",
    "931008": "中证汽车指数",
    "399995": "中证基建工程",
    "931009": "中证建筑材料",
    "931994": "中证电网设备主题",
    "399998": "中证煤炭",
    "H11057": "中证石化产业",
    "000126": "中证消费50",
    "931663": "中证消费龙头",
    "930633": "中证旅游",
    "930614": "中证环保50",
}

# ── API ───────────────────────────────────────────────
API_PATH = "/index/candlestick"

UPSERT_SQL = """INSERT OR REPLACE INTO index_daily_kline
    (stock_code, date, kline_type, open, close, high, low,
     volume, amount, change)
    VALUES (?, ?, 'normal', ?, ?, ?, ?, ?, ?, ?)"""


# ════════════════════════════════════════════════════════

def fetch_index_kline(stock_code: str, start_date: str, end_date: str) -> list:
    """拉取单只指数的区间K线"""
    payload = {
        "stockCode": stock_code,
        "type": "normal",
        "startDate": start_date,
        "endDate": end_date,
    }
    return api_post(API_PATH, payload)


def fetch_index_kline_batched(stock_code: str, start_date: str, end_date: str,
                              max_years: int = 9) -> list:
    """分批拉取K线，每批不超过 max_years 年（理杏仁限制 ≤10年）"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    span = (end - start).days

    if span <= max_years * 365:
        # 单批即可
        return fetch_index_kline(stock_code, start_date, end_date)

    # 需要分批
    chunk_delta = timedelta(days=max_years * 365)
    all_klines = []
    chunk_start = start

    while chunk_start < end:
        chunk_end = min(chunk_start + chunk_delta, end)
        s = chunk_start.strftime("%Y-%m-%d")
        e = chunk_end.strftime("%Y-%m-%d")
        log.info(f"    分批: {s} → {e}")
        chunk = fetch_index_kline(stock_code, s, e)
        all_klines.extend(chunk)
        chunk_start = chunk_end + timedelta(days=1)

    # 去重（按 date 字段）
    seen = set()
    deduped = []
    for k in all_klines:
        d = k["date"][:10]
        if d not in seen:
            seen.add(d)
            deduped.append(k)
    return deduped


def save_klines(conn, stock_code: str, klines: list) -> int:
    """写入指数K线"""
    if not klines:
        return 0
    rows = []
    for k in klines:
        rows.append((
            stock_code,
            k["date"][:10],
            k.get("open"),
            k.get("close"),
            k.get("high"),
            k.get("low"),
            k.get("volume"),
            k.get("amount"),
            k.get("change"),
        ))
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()
    return len(rows)


def main():
    conn = get_db()

    # ── 解析参数 ──────────────────────────────────────────
    # --start / --end: 指定日期区间
    user_start = None
    user_end = None
    for i, arg in enumerate(sys.argv):
        if arg == "--start" and i + 1 < len(sys.argv):
            user_start = sys.argv[i + 1]
        if arg == "--end" and i + 1 < len(sys.argv):
            user_end = sys.argv[i + 1]

    # 确定拉取哪些指数
    if "--tier-1" in sys.argv:
        indices = INDICES_TIER1
        log.info("🎯 仅拉取层级一（全市场指数）")
    elif "--all" in sys.argv:
        indices = {**INDICES_TIER1, **INDICES_TIER2, **INDICES_TIER3}
        log.info("🎯 拉取全部三层指数")
    else:
        # 默认：层级一 + 层级二（常用指数）
        indices = {**INDICES_TIER1, **INDICES_TIER2}
        log.info("🎯 拉取层级一 + 层级二（默认）")

    default_end = datetime.now().strftime("%Y-%m-%d")
    total_saved = 0

    for idx_code, idx_name in indices.items():
        # 查询该指数已存的最新日期
        latest = get_latest_date(conn, "index_daily_kline", stock_code=idx_code)

        if user_start:
            # 用户指定了起始日期 → 强制从指定日期开始
            start_date = user_start
        elif latest:
            start = datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)
            start_date = start.strftime("%Y-%m-%d")
            if start_date > default_end:
                log.info(f"  {idx_code} {idx_name} ✅ 已最新")
                continue
        else:
            # 新建：从 2000 年开始
            start_date = "2000-01-01"

        end_date = user_end if user_end else default_end

        try:
            klines = fetch_index_kline_batched(idx_code, start_date, end_date)
            n = save_klines(conn, idx_code, klines)
            total_saved += n
            log.info(f"  {idx_code} {idx_name}: +{n} 条 {start_date}~{end_date}")
        except Exception as e:
            log.error(f"  {idx_code} {idx_name}: ❌ {e}")

    log.info(f"🏁 完成: 共保存 {total_saved} 条指数K线")
    conn.close()


if __name__ == "__main__":
    main()
