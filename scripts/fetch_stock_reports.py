"""
个股研报数据全量拉取 — 东方财富主源 + 理杏仁辅助

数据源:
  东方财富:
    - reportapi.eastmoney.com/report/list  个股研报（多页翻取）
  理杏仁:
    - 理杏仁暂无直接研报API，通过基本面数据API获取机构关注度辅助指标
    - /api/cn/company/fundamental/non_financial  估值&市场指标（含股东人数变化等）

用法:
  python fetch_stock_reports.py                              # 全量A股，90天回溯
  python fetch_stock_reports.py --days 180                   # 180天回溯
  python fetch_stock_reports.py --limit 200                  # 前200只
  python fetch_stock_reports.py 600519                       # 单只股票
  python fetch_stock_reports.py --date 2026-05-14 --days 90
  python fetch_stock_reports.py --min-reports 5              # 至少5篇研报才入库

输出: lixinger.db → stock_analyst_reports, stock_report_raw
"""

import os
import sys
import time
import json
import sqlite3
import threading
from datetime import datetime, timedelta, date
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ═══════════════════════════════════════════════
# 路径 & 配置
# ═══════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR.parent / "data" / "lixinger.db"
ENV_PATH = Path.home() / ".hermes" / ".env"

EASTMONEY_REPORT_URL = "https://reportapi.eastmoney.com/report/list"
LIXINGER_BASE = "https://open.lixinger.com/api/cn"

DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_TIMEOUT = 60
BATCH_DELAY = 0.6

# ═══════════════════════════════════════════════
# 理杏仁 Token / Session
# ═══════════════════════════════════════════════

def load_lixinger_token() -> str:
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"未找到 .env 文件: {ENV_PATH}")
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LIXINGER_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise ValueError(f"LIXINGER_TOKEN 未在 {ENV_PATH} 中配置")

_token: Optional[str] = None
_limit_lock = threading.Lock()
_req_timestamps: list = []
MAX_REQ_PER_WINDOW = 30
REQ_WINDOW_SECS = 2.0

def get_token() -> str:
    global _token
    if _token is None:
        _token = load_lixinger_token()
    return _token

def rate_limit():
    with _limit_lock:
        now = time.time()
        global _req_timestamps
        _req_timestamps = [t for t in _req_timestamps if now - t < REQ_WINDOW_SECS]
        if len(_req_timestamps) >= MAX_REQ_PER_WINDOW:
            time.sleep(REQ_WINDOW_SECS - (now - _req_timestamps[0]) + 0.1)
            now = time.time()
            _req_timestamps = [t for t in _req_timestamps if now - t < REQ_WINDOW_SECS]
        _req_timestamps.append(now)

_session: Optional[requests.Session] = None
_session_lock = threading.Lock()

def get_session() -> requests.Session:
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = requests.Session()
                adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20,
                                      max_retries=Retry(total=0))
                _session.mount("https://", adapter)
                _session.mount("http://", adapter)
    return _session

def lixinger_post(path: str, payload: dict, timeout: int = DEFAULT_TIMEOUT):
    rate_limit()
    payload["token"] = get_token()
    url = f"{LIXINGER_BASE}{path}"
    session = get_session()
    for attempt in range(3):
        try:
            resp = session.post(url, json=payload, timeout=timeout)
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 1:
                raise RuntimeError(f"API error: code={data.get('code')} msg={data.get('message')}")
            return data.get("data", [])
        except requests.exceptions.Timeout:
            wait = [5, 10, 15][attempt] if attempt < 3 else 5
            time.sleep(wait)
        except requests.exceptions.ConnectionError:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"请求失败 (重试3次): {url}")

# ═══════════════════════════════════════════════
# 数据库
# ═══════════════════════════════════════════════

CREATE_SUMMARY_SQL = """
CREATE TABLE IF NOT EXISTS stock_analyst_reports (
    stock_code      TEXT NOT NULL,
    date            TEXT NOT NULL,
    lookback_days   INTEGER NOT NULL,
    report_count    INTEGER DEFAULT 0,
    org_count       INTEGER DEFAULT 0,
    first_coverage  INTEGER DEFAULT 0,
    upgrade_count   INTEGER DEFAULT 0,
    downgrade_count INTEGER DEFAULT 0,
    maintain_count  INTEGER DEFAULT 0,
    buy_count       INTEGER DEFAULT 0,
    overweight_count INTEGER DEFAULT 0,
    neutral_count   INTEGER DEFAULT 0,
    reduce_count    INTEGER DEFAULT 0,
    -- 理杏仁辅助指标
    lx_pe_ttm       REAL,              -- PE-TTM
    lx_pb           REAL,              -- PB
    lx_mc           REAL,              -- 市值（亿元）
    lx_shn          REAL,              -- 股东人数
    lx_shn_change   REAL,              -- 股东人数变化率（估算）
    orgs_json       TEXT,
    top_orgs_json   TEXT,              -- 覆盖最多的前5家机构
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, date, lookback_days)
);
"""

CREATE_RAW_SQL = """
CREATE TABLE IF NOT EXISTS stock_report_raw (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code      TEXT NOT NULL,
    report_date     TEXT NOT NULL,
    org_name        TEXT,
    author_name     TEXT,
    title           TEXT,
    rating_name     TEXT,
    rating_change   TEXT,
    is_first        INTEGER DEFAULT 0,
    info_code       TEXT UNIQUE,       -- 东方财富研报唯一标识
    updated_at      TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_report_raw_stock ON stock_report_raw(stock_code, report_date);
"""

# 东方财富研报拉取请求头
EM_REPORT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(CREATE_SUMMARY_SQL + CREATE_RAW_SQL)
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════
# 股票列表
# ═══════════════════════════════════════════════

def get_all_stocks(limit: int = None) -> list:
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute(
            "SELECT stock_code, name FROM stock_basic "
            "WHERE listing_status IN ('normally_listed','special_treatment','delisting_risk_warning') "
            "  AND name NOT LIKE '%ST%' AND name NOT LIKE '%*ST%' "
            "ORDER BY stock_code"
        )
        rows = cur.fetchall()
        conn.close()
        if rows:
            if limit:
                rows = rows[:limit]
            return [(r[0], r[1]) for r in rows]

    # 兜底：理杏仁API
    stocks = []
    for page in range(20):
        data = lixinger_post("/company", {"pageIndex": page, "includeDelisted": False})
        if not data:
            break
        for item in data:
            code = item.get("stockCode", "")
            name = item.get("name", "")
            status = item.get("listingStatus", "")
            if status in ("normally_listed", "special_treatment", "delisting_risk_warning"):
                if "ST" not in name:
                    stocks.append((code, name))
        if len(data) < 100:
            break
    if limit:
        stocks = stocks[:limit]
    return stocks

# ═══════════════════════════════════════════════
# 东方财富 研报拉取
# ═══════════════════════════════════════════════

def fetch_em_reports(stock_code: str, begin_date: str, end_date: str) -> dict:
    """拉取单只股票研报（多页翻取）"""
    all_records = []
    page = 1
    max_pages = 20

    session = requests.Session()
    session.headers.update(EM_REPORT_HEADERS)

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
            r = session.get(EASTMONEY_REPORT_URL, params=params, timeout=30)
            d = r.json()
        except Exception as e:
            break

        if not d or "data" not in d:
            break
        records = d.get("data", [])
        if not records:
            break
        all_records.extend(records)

        total_pages = d.get("TotalPage", d.get("totalPage", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)

    if not all_records:
        return None

    # ── 统计 ──
    orgs = set()
    org_counter = Counter()
    first_coverage = False
    rating_change_counter = Counter()
    rating_name_counter = Counter()
    raw_list = []

    for rec in all_records:
        org_name = rec.get("orgSName", rec.get("orgName", ""))
        if org_name:
            orgs.add(org_name)
            org_counter[org_name] += 1

        if rec.get("indvIsNew", "001") == "":
            first_coverage = True

        rc = rec.get("ratingChange", "")
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

        rn = rec.get("emRatingName", rec.get("sRatingName", ""))
        if rn:
            rating_name_counter[rn] += 1

        # author 字段可能为列表，safe_str 确保输出为字符串
        def safe_str(val):
            if isinstance(val, list):
                return ', '.join(str(v) for v in val)
            return str(val) if val else ''

        # 原始记录
        raw_list.append({
            "report_date": rec.get("reportDate", rec.get("publishDate", ""))[:10],
            "org_name": safe_str(org_name),
            "author_name": safe_str(rec.get("author", "")),
            "title": rec.get("title", ""),
            "rating_name": rn,
            "rating_change": rc,
            "is_first": 1 if rec.get("indvIsNew", "001") == "" else 0,
            "info_code": rec.get("infoCode", ""),
        })

    # 评级分布
    buy_count = overweight_count = neutral_count = reduce_count = 0
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
        "top_orgs": [{"name": n, "count": c} for n, c in org_counter.most_common(5)],
        "first_coverage": first_coverage,
        "upgrade_count": rating_change_counter.get("upgrade", 0),
        "downgrade_count": rating_change_counter.get("downgrade", 0),
        "maintain_count": rating_change_counter.get("maintain", 0),
        "buy_count": buy_count,
        "overweight_count": overweight_count,
        "neutral_count": neutral_count,
        "reduce_count": reduce_count,
        "raw": raw_list,
    }

# ═══════════════════════════════════════════════
# 理杏仁 辅助指标
# ═══════════════════════════════════════════════

def fetch_lixinger_fundamental(stock_code: str, end_date: str) -> dict:
    """获取理杏仁基本面辅助指标"""
    try:
        data = lixinger_post("/company/fundamental/non_financial", {
            "stockCodes": [stock_code],
            "date": end_date,
            "metricsList": ["sp", "pe_ttm", "pb", "mc", "shn", "dyr", "to_r"],
        }, timeout=30)
        if data and isinstance(data, list) and len(data) > 0:
            d = data[0]
            return {
                "lx_pe_ttm": d.get("pe_ttm"),
                "lx_pb": d.get("pb"),
                "lx_mc": d.get("mc"),
                "lx_shn": d.get("shn"),
                "lx_dyr": d.get("dyr"),
                "lx_sp": d.get("sp"),
            }
    except Exception:
        pass
    return {}

# ═══════════════════════════════════════════════
# 入库
# ═══════════════════════════════════════════════

def save_summary(stock_code: str, date_str: str, lookback_days: int,
                 result: dict, lx_fund: dict):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        INSERT OR REPLACE INTO stock_analyst_reports
        (stock_code, date, lookback_days, report_count, org_count,
         first_coverage, upgrade_count, downgrade_count, maintain_count,
         buy_count, overweight_count, neutral_count, reduce_count,
         lx_pe_ttm, lx_pb, lx_mc, lx_shn,
         orgs_json, top_orgs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?)
    """, (
        stock_code, date_str, lookback_days,
        result["report_count"], result["org_count"],
        1 if result["first_coverage"] else 0,
        result["upgrade_count"], result["downgrade_count"],
        result["maintain_count"],
        result["buy_count"], result["overweight_count"],
        result["neutral_count"], result["reduce_count"],
        lx_fund.get("lx_pe_ttm"), lx_fund.get("lx_pb"),
        lx_fund.get("lx_mc"), lx_fund.get("lx_shn"),
        json.dumps(result["orgs"], ensure_ascii=False),
        json.dumps(result.get("top_orgs", []), ensure_ascii=False),
    ))
    conn.commit()
    conn.close()

def save_raw(stock_code: str, raw_list: list):
    if not raw_list:
        return
    conn = sqlite3.connect(str(DB_PATH))
    for d in raw_list:
        conn.execute("""
            INSERT OR IGNORE INTO stock_report_raw
            (stock_code, report_date, org_name, author_name, title,
             rating_name, rating_change, is_first, info_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_code, d["report_date"], d["org_name"], d["author_name"],
            d["title"], d["rating_name"], d["rating_change"],
            d["is_first"], d["info_code"],
        ))
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════
# 单只 & 批量
# ═══════════════════════════════════════════════

def fetch_one_stock(stock_code: str, begin_date: str, end_date: str,
                    with_lixinger: bool = True) -> dict:
    """拉取单只股票研报+辅助数据"""
    result = fetch_em_reports(stock_code, begin_date, end_date)
    if not result:
        return None

    lx = {}
    if with_lixinger:
        lx = fetch_lixinger_fundamental(stock_code, end_date)

    result["lx"] = lx
    return result

def get_recently_fetched_reports(days: int = 7) -> set:
    """查询最近N天内已拉取研报的股票代码集合"""
    if not DB_PATH.exists():
        return set()
    conn = sqlite3.connect(str(DB_PATH))
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    cur = conn.execute(
        "SELECT DISTINCT stock_code FROM stock_analyst_reports WHERE updated_at >= ?",
        (cutoff,)
    )
    result = {r[0] for r in cur.fetchall()}
    conn.close()
    return result


def batch_fetch(stock_list: list, begin_date: str, end_date: str,
                lookback_days: int, delay: float = BATCH_DELAY,
                with_lixinger: bool = True, min_reports: int = 0):
    total = len(stock_list)
    init_db()
    skipped = 0

    for i, (code, name) in enumerate(stock_list):
        print(f"[{i+1}/{total}] {code} {name}", end="", flush=True)
        try:
            r = fetch_one_stock(code, begin_date, end_date, with_lixinger)
        except Exception as e:
            print(f"  ERROR: {e}")
            skipped += 1
            continue

        if not r:
            print("  无研报")
            skipped += 1
            continue

        if r["report_count"] < min_reports:
            print(f"  仅{r['report_count']}篇（跳过，阈值{min_reports}）")
            skipped += 1
            continue

        save_summary(code, end_date, lookback_days, r, r.get("lx", {}))
        save_raw(code, r.get("raw", []))

        extra = ""
        if r["first_coverage"]:
            extra += " 🔥首次覆盖"
        if r["upgrade_count"]:
            extra += f" ↑{r['upgrade_count']}"
        if r["downgrade_count"]:
            extra += f" ↓{r['downgrade_count']}"
        print(f"  {r['report_count']}篇 {r['org_count']}家{extra}")

        if i < total - 1:
            time.sleep(delay)

    print(f"\n完成: {total - skipped}/{total} 只有研报数据 ({skipped} 只跳过)")

# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    stock_code = None
    end_date = date.today().strftime("%Y-%m-%d")
    days = DEFAULT_LOOKBACK_DAYS
    limit = None
    min_reports = 0
    with_lixinger = True
    force = False

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--force":
            force = True
            i += 1
        elif a == "--days":
            days = int(args[i+1])
            i += 2
        elif a == "--limit":
            limit = int(args[i+1])
            i += 2
        elif a == "--date":
            end_date = args[i+1]
            i += 2
        elif a == "--min-reports":
            min_reports = int(args[i+1])
            i += 2
        elif a == "--no-lixinger":
            with_lixinger = False
            i += 1
        else:
            stock_code = a
            i += 1

    begin_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    lookback_days = (datetime.strptime(end_date, "%Y-%m-%d") -
                     datetime.strptime(begin_date, "%Y-%m-%d")).days

    print(f"研报拉取: {begin_date} ~ {end_date} ({lookback_days}天)")
    print(f"理杏仁辅助: {'是' if with_lixinger else '否'}")
    print()

    if stock_code:
        print(f"单只: {stock_code}")
        r = fetch_one_stock(stock_code, begin_date, end_date, with_lixinger)
        if r:
            print(f"\n{'='*50}")
            print(f"股票: {stock_code}")
            print(f"  研报: {r['report_count']}篇  机构: {r['org_count']}家")
            print(f"  首次覆盖: {'是' if r['first_coverage'] else '否'}")
            print(f"  评级变化: 上调{r['upgrade_count']} 下调{r['downgrade_count']} 维持{r['maintain_count']}")
            print(f"  评级分布: 买入{r['buy_count']} 增持{r['overweight_count']} 中性{r['neutral_count']} 减持{r['reduce_count']}")
            if r.get("top_orgs"):
                print(f"  覆盖最多: {', '.join(f'{o['name']}({o['count']})' for o in r['top_orgs'][:5])}")
            lx = r.get("lx", {})
            if lx:
                print(f"  理杏仁: PE={lx.get('lx_pe_ttm')} PB={lx.get('lx_pb')} 市值={lx.get('lx_mc')}")
        else:
            print("  无数据")
        return

    # 批量模式（增量：默认跳过7天内已拉取的股票）
    stocks = get_all_stocks(limit)
    skip_set = set() if force else get_recently_fetched_reports(7)
    todo = [s for s in stocks if s[0] not in skip_set]

    print("研报拉取: %d 只" % len(stocks))
    if not force and skip_set:
        print("  7天内已拉取: %d 只，跳过" % len(skip_set))
    print("  本次: %d 只" % len(todo))

    if todo:
        batch_fetch(todo, begin_date, end_date, lookback_days,
                    with_lixinger=with_lixinger, min_reports=min_reports)

if __name__ == "__main__":
    main()
