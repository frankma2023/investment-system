"""
机构持股数据全量拉取 — 理杏仁

数据源:
  理杏仁:
    - /api/cn/company/fund-shareholders    公募基金持股（基金粒度）
    - /api/cn/company/majority-shareholders 前十大股东（股东粒度）
    - /api/cn/company/nolimit-shareholders  前十大流通股东

用法:
  python fetch_institutional_holdings.py                        # 全量A股
  python fetch_institutional_holdings.py --limit 200            # 前200只
  python fetch_institutional_holdings.py 600519                 # 单只股票
  python fetch_institutional_holdings.py --date 2026-05-14      # 指定截止日期

输出: lixinger.db → stock_institutional_holdings, stock_inst_holders_detail
"""

import os
import sys
import time
import json
import sqlite3
import threading
from datetime import datetime, timedelta, date
from collections import defaultdict, Counter
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

LIXINGER_BASE = "https://open.lixinger.com/api/cn"
EASTMONEY_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"

DEFAULT_TIMEOUT = 60
BATCH_DELAY = 0.8          # 每只股票间延迟（秒）

# ═══════════════════════════════════════════════
# Token / Session
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

# ═══════════════════════════════════════════════
# API 请求
# ═══════════════════════════════════════════════

def lixinger_post(path: str, payload: dict, timeout: int = DEFAULT_TIMEOUT):
    """理杏仁 POST 请求"""
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

EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}

def eastmoney_get(report_name: str, stock_code: str, columns: str,
                  page_size: int = 500, max_pages: int = 5) -> list:
    """东方财富数据查询"""
    all_data = []
    for page in range(1, max_pages + 1):
        params = {
            "reportName": report_name,
            "columns": columns,
            "filter": f'(SECURITY_CODE="{stock_code}")',
            "pageNumber": page,
            "pageSize": page_size,
            "sortColumns": "END_DATE",
            "sortTypes": -1,
            "source": "WEB",
            "client": "WEB",
        }
        try:
            r = requests.get(EASTMONEY_BASE, params=params,
                           headers=EASTMONEY_HEADERS, timeout=30)
            d = r.json()
            if not d.get("success"):
                break
            data = d.get("result", {}).get("data") or []
            if not data:
                break
            all_data.extend(data)
            if len(data) < page_size:
                break
        except Exception as e:
            print(f"    [{stock_code}] 东方财富 {report_name} page={page}: {e}")
            break
        time.sleep(0.15)
    return all_data

# ═══════════════════════════════════════════════
# 数据库
# ═══════════════════════════════════════════════

CREATE_SUMMARY_SQL = """
CREATE TABLE IF NOT EXISTS stock_institutional_holdings (
    stock_code              TEXT NOT NULL,
    date                    TEXT NOT NULL,
    data_source             TEXT NOT NULL,     -- 'lixinger' / 'eastmoney' / 'merged'
    -- 公募基金 (理杏仁)
    fund_count              INTEGER,
    fund_holdings_total     REAL,              -- 基金持股市值合计(元)
    fund_proportion_sum     REAL,              -- 流通A股占比合计
    -- 前十大机构 (理杏仁)
    top10_inst_count        INTEGER,
    top10_inst_proportion   REAL,
    -- 前十大流通机构 (理杏仁)
    top10_float_inst_count  INTEGER,
    top10_float_inst_prop   REAL,
    -- 汇总
    total_inst_count        INTEGER,
    total_inst_proportion   REAL,
    org_categories_json     TEXT,              -- 机构类别分布
    updated_at              TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (stock_code, date, data_source)
);
"""

CREATE_DETAIL_SQL = """
CREATE TABLE IF NOT EXISTS stock_inst_holders_detail (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code              TEXT NOT NULL,
    date                    TEXT NOT NULL,
    data_source             TEXT NOT NULL,
    holder_type             TEXT NOT NULL,     -- 'fund' / 'majority' / 'freeholders'
    holder_name             TEXT,
    holder_code             TEXT,              -- 基金代码或机构代码
    holdings                REAL,              -- 持股数量
    market_cap              REAL,              -- 持股市值(仅基金)
    proportion              REAL,              -- 占比
    holder_category         TEXT,              -- 机构类别
    holder_rank             INTEGER,           -- 排名
    updated_at              TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_inst_detail_stock ON stock_inst_holders_detail(stock_code, date);
"""

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(CREATE_SUMMARY_SQL + CREATE_DETAIL_SQL)
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════
# 股票列表
# ═══════════════════════════════════════════════

def get_all_stocks(limit: int = None) -> list:
    """获取全量A股列表（从理杏仁API或本地DB）"""
    # 优先从本地DB获取
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

    # 兜底：从理杏仁API获取
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
# 理杏仁 数据拉取
# ═══════════════════════════════════════════════

def fetch_lixinger_fund(stock_code: str, start_date: str, end_date: str) -> dict:
    """拉取公募基金持股"""
    try:
        records = lixinger_post("/company/fund-shareholders", {
            "stockCode": stock_code,
            "startDate": start_date,
            "endDate": end_date,
        })
    except Exception as e:
        print(f"  [{stock_code}] 理杏仁基金API错误: {e}")
        return None

    if not records:
        return {"fund_count": 0, "fund_holdings_total": 0, "fund_proportion_sum": 0,
                "date": None, "detail": []}

    date_groups = defaultdict(list)
    for r in records:
        d = r.get("date", "")
        if isinstance(d, str) and "T" in d:
            d = d.split("T")[0]
        date_groups[d].append(r)
    if not date_groups:
        return {"fund_count": 0, "fund_holdings_total": 0, "fund_proportion_sum": 0,
                "date": None, "detail": []}

    latest_date = sorted(date_groups.keys())[-1]
    latest = date_groups[latest_date]

    fund_codes = set()
    total_market_cap = 0.0
    prop_sum = 0.0
    detail = []

    for r in latest:
        fc = r.get("fundCode", "")
        if fc:
            fund_codes.add(fc)
        mc = r.get("marketCap", 0) or 0
        prop = r.get("proportionOfOutstandingSharesA", 0) or 0
        total_market_cap += mc
        prop_sum += prop
        detail.append({
            "holder_code": fc,
            "holder_name": r.get("name", ""),
            "holdings": r.get("holdings", 0),
            "market_cap": mc,
            "proportion": prop,
            "holder_rank": r.get("marketCapRank", 0),
        })

    # 归一化：理杏仁API返回的 proportion 可能为百分比(>1)或小数，统一存小数
    if prop_sum > 1.0:
        prop_sum = prop_sum / 100.0

    return {
        "fund_count": len(fund_codes),
        "fund_holdings_total": total_market_cap,
        "fund_proportion_sum": round(prop_sum, 4),
        "date": latest_date,
        "detail": detail,
    }

def fetch_lixinger_majority(stock_code: str, start_date: str, end_date: str) -> dict:
    """拉取前十大股东"""
    try:
        records = lixinger_post("/company/majority-shareholders", {
            "stockCode": stock_code,
            "startDate": start_date,
            "endDate": end_date,
        })
    except Exception as e:
        print(f"  [{stock_code}] 理杏仁十大股东API错误: {e}")
        return None

    if not records:
        return {"top10_inst_count": 0, "top10_inst_proportion": 0,
                "categories": {}, "date": None, "detail": []}

    date_groups = defaultdict(list)
    for r in records:
        d = r.get("date", "")
        if isinstance(d, str) and "T" in d:
            d = d.split("T")[0]
        date_groups[d].append(r)
    if not date_groups:
        return {"top10_inst_count": 0, "top10_inst_proportion": 0,
                "categories": {}, "date": None, "detail": []}

    latest_date = sorted(date_groups.keys())[-1]
    latest = date_groups[latest_date]

    INST_CATS = {"fund", "qfii", "social_security", "insurance",
                 "trust", "brokerage", "other_organisations"}
    categories = defaultdict(lambda: {"count": 0, "proportion": 0})
    total_inst_prop = 0.0
    inst_names = set()
    detail = []

    for r in latest:
        cats = r.get("shareholderCategories", [])
        prop = r.get("proportionOfCapitalization", 0) or 0
        name = r.get("name", "")
        is_inst = any(c in INST_CATS for c in cats)
        if is_inst:
            for c in cats:
                if c in INST_CATS:
                    categories[c]["count"] += 1
                    categories[c]["proportion"] += prop
            if name:
                inst_names.add(name)
                total_inst_prop += prop
        detail.append({
            "holder_name": name,
            "holder_category": r.get("shareholderCategory", ""),
            "holdings": r.get("holdings", 0),
            "proportion": prop,
            "is_institution": is_inst,
        })

    # 归一化：理杏仁API返回比例可能>1(百分比)，统一存小数
    if total_inst_prop > 1.0:
        total_inst_prop = total_inst_prop / 100.0

    return {
        "top10_inst_count": len(inst_names),
        "top10_inst_proportion": round(total_inst_prop, 4),
        "categories": {k: {"count": v["count"], "proportion": round(v["proportion"], 4)}
                       for k, v in categories.items()},
        "date": latest_date,
        "detail": detail,
    }

def fetch_lixinger_float_top10(stock_code: str, start_date: str, end_date: str) -> dict:
    """拉取前十大流通股东"""
    try:
        records = lixinger_post("/company/nolimit-shareholders", {
            "stockCode": stock_code,
            "startDate": start_date,
            "endDate": end_date,
        })
    except Exception as e:
        return {"top10_float_inst_count": 0, "top10_float_inst_prop": 0,
                "date": None, "detail": []}

    if not records:
        return {"top10_float_inst_count": 0, "top10_float_inst_prop": 0,
                "date": None, "detail": []}

    date_groups = defaultdict(list)
    for r in records:
        d = r.get("date", "")
        if isinstance(d, str) and "T" in d:
            d = d.split("T")[0]
        date_groups[d].append(r)
    if not date_groups:
        return {"top10_float_inst_count": 0, "top10_float_inst_prop": 0,
                "date": None, "detail": []}

    latest_date = sorted(date_groups.keys())[-1]
    latest = date_groups[latest_date]

    INST_CATS = {"fund", "qfii", "social_security", "insurance",
                 "trust", "brokerage", "other_organisations"}
    inst_count = 0
    inst_prop = 0.0
    detail = []

    for r in latest:
        cats = r.get("shareholderCategories", [])
        prop = r.get("proportionOfOutstandingSharesA", 0) or 0
        is_inst = any(c in INST_CATS for c in cats)
        if is_inst:
            inst_count += 1
            inst_prop += prop
        detail.append({
            "holder_name": r.get("name", ""),
            "holder_category": r.get("shareholderCategory", ""),
            "holdings": r.get("holdings", 0),
            "proportion": prop,
            "is_institution": is_inst,
        })

    return {
        "top10_float_inst_count": inst_count,
        "top10_float_inst_prop": round(inst_prop, 4),
        "date": latest_date,
        "detail": detail,
    }

# ═══════════════════════════════════════════════
# 东方财富 数据拉取
# ═══════════════════════════════════════════════

def fetch_em_top10_holders(stock_code: str) -> dict:
    """东方财富十大股东"""
    COLUMNS = "SECURITY_CODE,END_DATE,HOLDER_NAME,HOLD_NUM,HOLD_NUM_RATIO,HOLDER_RANK"
    data = eastmoney_get("RPT_F10_EH_HOLDERS", stock_code, COLUMNS, page_size=20, max_pages=2)
    if not data:
        return {"em_top10_holder_count": 0, "em_top10_inst_count": 0,
                "em_top10_inst_prop": 0, "date": None, "detail": []}

    # 取最新报告期
    date_groups = defaultdict(list)
    for r in data:
        end_date = r.get("END_DATE", "")[:10] if r.get("END_DATE") else ""
        if end_date:
            date_groups[end_date].append(r)
    if not date_groups:
        return {"em_top10_holder_count": 0, "em_top10_inst_count": 0,
                "em_top10_inst_prop": 0, "date": None, "detail": []}

    latest_date = sorted(date_groups.keys())[-1]
    latest = date_groups[latest_date]

    INST_KEYWORDS = ["基金", "QFII", "社保", "保险", "信托", "券商", "银行", "资产管理",
                     "投资公司", "香港中央结算", "中央汇金", "证金", "养老金", "企业年金",
                     "私募", "资管", "理财"]
    inst_count = 0
    inst_prop = 0.0
    detail = []

    for r in latest:
        name = r.get("HOLDER_NAME", "")
        prop = float(r.get("HOLD_NUM_RATIO", 0) or 0)
        rank = int(r.get("HOLDER_RANK", 0) or 0)
        is_inst = any(kw in name for kw in INST_KEYWORDS) and "自然人" not in name
        if is_inst:
            inst_count += 1
            inst_prop += prop
        detail.append({
            "holder_name": name,
            "holdings": float(r.get("HOLD_NUM", 0) or 0),
            "proportion": prop,
            "holder_rank": rank,
            "is_institution": is_inst,
        })

    return {
        "em_top10_holder_count": len(latest),
        "em_top10_inst_count": inst_count,
        "em_top10_inst_prop": round(inst_prop, 2),
        "date": latest_date,
        "detail": detail,
    }

def fetch_em_freeholders(stock_code: str) -> dict:
    """东方财富十大流通股东"""
    COLUMNS = "SECURITY_CODE,END_DATE,HOLDER_NAME,HOLD_NUM,FREE_HOLDNUM_RATIO,HOLDER_RANK"
    data = eastmoney_get("RPT_F10_EH_FREEHOLDERS", stock_code, COLUMNS, page_size=20, max_pages=2)
    if not data:
        return {"em_top10_float_count": 0, "em_top10_float_inst": 0,
                "em_top10_float_inst_prop": 0, "date": None, "detail": []}

    date_groups = defaultdict(list)
    for r in data:
        end_date = r.get("END_DATE", "")[:10] if r.get("END_DATE") else ""
        if end_date:
            date_groups[end_date].append(r)
    if not date_groups:
        return {"em_top10_float_count": 0, "em_top10_float_inst": 0,
                "em_top10_float_inst_prop": 0, "date": None, "detail": []}

    latest_date = sorted(date_groups.keys())[-1]
    latest = date_groups[latest_date]

    INST_KEYWORDS = ["基金", "QFII", "社保", "保险", "信托", "券商", "银行", "资产管理",
                     "投资公司", "香港中央结算", "中央汇金", "证金", "养老金", "企业年金",
                     "私募", "资管", "理财"]
    inst_count = 0
    inst_prop = 0.0
    detail = []

    for r in latest:
        name = r.get("HOLDER_NAME", "")
        prop = float(r.get("FREE_HOLDNUM_RATIO", 0) or 0)
        rank = int(r.get("HOLDER_RANK", 0) or 0)
        is_inst = any(kw in name for kw in INST_KEYWORDS) and "自然人" not in name
        if is_inst:
            inst_count += 1
            inst_prop += prop
        detail.append({
            "holder_name": name,
            "holdings": float(r.get("HOLD_NUM", 0) or 0),
            "proportion": prop,
            "holder_rank": rank,
            "is_institution": is_inst,
        })

    return {
        "em_top10_float_count": len(latest),
        "em_top10_float_inst": inst_count,
        "em_top10_float_inst_prop": round(inst_prop, 2),
        "date": latest_date,
        "detail": detail,
    }

# ═══════════════════════════════════════════════
# 汇总 & 入库
# ═══════════════════════════════════════════════

def merge_results(lx_fund, lx_majority, lx_float):
    """
    合并理杏仁三源数据。

    综合占比取各源最大值（不叠加，防止双重计数）。
    """
    result = {}

    # ── 理杏仁数据 ──
    if lx_fund:
        result.update({k: lx_fund[k] for k in
                       ["fund_count", "fund_holdings_total", "fund_proportion_sum"]})
    if lx_majority:
        result.update({k: lx_majority[k] for k in
                       ["top10_inst_count", "top10_inst_proportion", "categories"]})
    if lx_float:
        result.update({k: lx_float[k] for k in
                       ["top10_float_inst_count", "top10_float_inst_prop"]})
    # 综合估算（归一化）
    def norm_prop(v):
        return v / 100.0 if v > 1.0 else v

    props = []
    for v in [lx_fund, lx_majority]:
        if v:
            p = v.get("fund_proportion_sum") or v.get("top10_inst_proportion") or 0
            props.append(norm_prop(p))
    result["total_inst_proportion"] = max(props) if props else 0
    result["total_inst_count"] = max(
        lx_fund.get("fund_count", 0) if lx_fund else 0,
        lx_majority.get("top10_inst_count", 0) if lx_majority else 0,
    )
    result["categories"] = (lx_majority or {}).get("categories", {})

    # 最新日期
    dates = []
    for v in [lx_fund, lx_majority, lx_float]:
        if v and v.get("date"):
            dates.append(v["date"])
    result["date"] = max(dates) if dates else date.today().strftime("%Y-%m-%d")

    return result

def save_summary(stock_code: str, date_str: str, result: dict):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        INSERT OR REPLACE INTO stock_institutional_holdings
        (stock_code, date, data_source, fund_count, fund_holdings_total,
         fund_proportion_sum, top10_inst_count, top10_inst_proportion,
         top10_float_inst_count, top10_float_inst_prop,
         total_inst_count, total_inst_proportion, org_categories_json)
        VALUES (?, ?, 'lixinger', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        stock_code, date_str,
        result.get("fund_count", 0),
        result.get("fund_holdings_total", 0),
        result.get("fund_proportion_sum", 0),
        result.get("top10_inst_count", 0),
        result.get("top10_inst_proportion", 0),
        result.get("top10_float_inst_count", 0),
        result.get("top10_float_inst_prop", 0),
        result.get("total_inst_count", 0),
        result.get("total_inst_proportion", 0),
        json.dumps(result.get("categories", {}), ensure_ascii=False),
    ))
    conn.commit()
    conn.close()

def save_detail(stock_code: str, date_str: str, source: str,
                holder_type: str, details: list):
    if not details:
        return
    conn = sqlite3.connect(str(DB_PATH))
    for d in details:
        conn.execute("""
            INSERT INTO stock_inst_holders_detail
            (stock_code, date, data_source, holder_type, holder_name,
             holder_code, holdings, market_cap, proportion, holder_category, holder_rank)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_code, date_str, source, holder_type,
            d.get("holder_name", ""),
            d.get("holder_code", ""),
            d.get("holdings", 0),
            d.get("market_cap", 0),
            d.get("proportion", 0),
            d.get("holder_category", ""),
            d.get("holder_rank", 0),
        ))
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════
# 单只 & 批量
# ═══════════════════════════════════════════════

def fetch_one_stock(stock_code: str, start_date: str, end_date: str):
    """
    拉取单只股票的全部机构持股数据。
    数据源：理杏仁（公募基金 + 前十大股东 + 前十大流通股东）
    """
    result = {}
    all_details = []

    # ① 公募基金持股
    lx_fund = fetch_lixinger_fund(stock_code, start_date, end_date)
    if lx_fund and lx_fund.get("detail"):
        all_details.append(("lixinger", "fund", lx_fund["detail"]))

    # ② 前十大股东
    lx_majority = fetch_lixinger_majority(stock_code, start_date, end_date)
    if lx_majority and lx_majority.get("detail"):
        all_details.append(("lixinger", "majority", lx_majority["detail"]))

    # ③ 前十大流通股东
    lx_float = fetch_lixinger_float_top10(stock_code, start_date, end_date)
    if lx_float and lx_float.get("detail"):
        all_details.append(("lixinger", "freeholders", lx_float["detail"]))

    result = merge_results(lx_fund, lx_majority, lx_float)
    result["_details"] = all_details
    return result

def batch_fetch(stock_list: list, start_date: str, end_date: str,
                delay: float = BATCH_DELAY):
    """批量拉取全量A股"""
    total = len(stock_list)
    init_db()

    for i, (code, name) in enumerate(stock_list):
        print(f"[{i+1}/{total}] {code} {name}", end="", flush=True)
        try:
            r = fetch_one_stock(code, start_date, end_date)
            save_summary(code, r.get("date", end_date), r)
            for src, htype, details in r.get("_details", []):
                save_detail(code, r.get("date", end_date), src, htype, details)
            # 输出摘要
            print(f"  基金{r.get('fund_count',0)}家 "
                  f"十大机构{r.get('top10_inst_count',0)}家 "
                  f"占比{r.get('total_inst_proportion',0)*100:.1f}%")
        except Exception as e:
            print(f"  ERROR: {e}")

        if i < total - 1:
            time.sleep(delay)

# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    stock_code = None
    end_date = date.today().strftime("%Y-%m-%d")
    start_date = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    limit = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit":
            limit = int(args[i+1])
            i += 2
        elif a == "--date":
            end_date = args[i+1]
            i += 2
        elif a == "--start-date":
            start_date = args[i+1]
            i += 2
        else:
            stock_code = a
            i += 1

    if stock_code:
        # 单只模式
        print(f"单只: {stock_code}  范围: {start_date} ~ {end_date}")
        r = fetch_one_stock(stock_code, start_date, end_date)
        print("\n" + "="*50)
        print("Stock: %s" % stock_code)
        print("Date: %s" % r.get('date'))
        print("  Fund: %d, Prop: %.2f%%" % (r.get('fund_count',0), r.get('fund_proportion_sum',0)*100))
        print("  Top10 Inst: %d, Prop: %.2f%%" % (r.get('top10_inst_count',0), r.get('top10_inst_proportion',0)*100))
        print("  Float Inst: %d, Prop: %.2f%%" % (r.get('top10_float_inst_count',0), r.get('top10_float_inst_prop',0)*100))
        print("  Total Prop: %.2f%%" % (r.get('total_inst_proportion',0)*100))
        cats = r.get("categories", {})
        if cats:
            print(f"  机构类别分布:")
            for cat, info in sorted(cats.items()):
                print(f"    {cat}: {info['count']}家 {info['proportion']*100:.2f}%")
        return

    # 批量模式
    stocks = get_all_stocks(limit)
    print("A股机构持股拉取: %d 只" % len(stocks))
    print("Time: %s ~ %s" % (start_date, end_date))
    print()
    batch_fetch(stocks, start_date, end_date)

if __name__ == "__main__":
    main()
