#!/usr/bin/env python
"""
scripts/fetch_stock_basic.py — 拉取全量A股基础信息并更新 stock_basic 表
用法：python scripts/fetch_stock_basic.py
"""

from common import api_post, get_db, log

UPSERT_SQL = """INSERT OR REPLACE INTO stock_basic
    (stock_code, name, market, exchange, area_code, listing_status,
     ipo_date, delisted_date, fs_table_type, mutual_market_flag)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

if __name__ == "__main__":
    log.info("拉取全量股票基础信息...")

    all_data = []
    page = 0
    while True:
        payload = {"pageIndex": page}
        records = api_post("/company", payload)
        if not records:
            break
        all_data.extend(records)
        log.info(f"  第{page+1}页: {len(records)}条 (累计{len(all_data)})")
        if len(records) < 500:  # 最后一页不足500条
            break
        page += 1

    if not all_data:
        log.error("未拉取到数据")
        exit(1)

    conn = get_db()
    rows = []
    for item in all_data:
        rows.append((
            item.get("stockCode"), item.get("name"), item.get("market"),
            item.get("exchange"), item.get("areaCode"), item.get("listingStatus"),
            item.get("ipoDate", "")[:10] if item.get("ipoDate") else None,
            item.get("delistedDate", "")[:10] if item.get("delistedDate") else None,
            item.get("fsTableType"),
            1 if item.get("mutualMarketFlag") else 0,
        ))
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()

    statuses = conn.execute("""
        SELECT listing_status, COUNT(*) as cnt FROM stock_basic
        GROUP BY listing_status ORDER BY cnt DESC
    """).fetchall()
    log.info(f"写入/更新 {len(rows)} 条")
    for s in statuses:
        log.info(f"  {s['listing_status']}: {s['cnt']}")

    st = conn.execute("""
        SELECT COUNT(*) FROM stock_basic
        WHERE listing_status IN ('special_treatment', 'delisting_risk_warning')
    """).fetchone()[0]
    log.info(f"ST/*ST: {st} 只")

    r = conn.execute("SELECT stock_code, name, listing_status FROM stock_basic WHERE stock_code='000056'").fetchone()
    if r:
        log.info(f"000056: {r['name']} status={r['listing_status']}")
    conn.close()
