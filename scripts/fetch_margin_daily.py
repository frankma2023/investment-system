#!/usr/bin/env python3
"""
每日融资融券更新（新 API）

新 API: /api/cn/company/hot/mtasl
  批量 100 只，返回最新快照（含 npa 和 fb_mc_rc 字段）
  运行频率：每日盘后
"""

import sys
import os
import time
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))
os.chdir(PROJECT_DIR)

from scripts.common import api_post, get_db, get_all_stock_codes, log, DEFAULT_TIMEOUT

API_PATH = "/company/hot/mtasl"
BATCH = 100

def main():
    start = time.time()
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("🐺 每日融资融券更新（新API）")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━")

    codes = get_all_stock_codes()
    log.info(f"活跃股票: {len(codes)} 只")

    db = get_db()
    total_rows = 0
    failed_batches = 0

    for i in range(0, len(codes), BATCH):
        batch = codes[i:i + BATCH]
        payload = {"stockCodes": batch}
        try:
            result = api_post(API_PATH, payload)
            data = result.get("data", [])
            if not data:
                log.info(f"  [{i//BATCH+1}] 空返回")
                failed_batches += 1
                continue

            rows = []
            for item in data:
                code = item.get("stockCode", "")
                d = item.get("last_data_date", "")
                date_str = d[:10] if "T" in d else d
                if not code or not date_str:
                    continue

                rows.append((
                    code, date_str,
                    item.get("mtaslb"),           # 融资融券余额
                    item.get("mtaslb_fb"),        # 融资余额
                    item.get("mtaslb_sb"),        # 融券余额
                    item.get("mtaslb_mc_r"),      # 融资余额占流通市值比
                    item.get("npa_o_f_d1"),       # 1日融资净买入
                    item.get("npa_o_f_d5"),       # 5日
                    item.get("npa_o_f_d10"),
                    item.get("npa_o_f_d20"),
                    item.get("npa_o_f_d60"),
                    item.get("npa_o_f_d120"),
                    item.get("npa_o_f_d240"),
                    item.get("fb_mc_rc_d1"),      # 1日融资偿还率
                    item.get("fb_mc_rc_d5"),
                    item.get("fb_mc_rc_d10"),
                    item.get("fb_mc_rc_d20"),
                    item.get("fb_mc_rc_d60"),
                    item.get("fb_mc_rc_d120"),
                    item.get("fb_mc_rc_d240"),
                ))

            if rows:
                sql = """INSERT OR REPLACE INTO stock_margin
                    (stock_code, date, mtaslb, mtaslb_fb, mtaslb_sb, mtaslb_mc_r,
                     npa_o_f_d1, npa_o_f_d5, npa_o_f_d10, npa_o_f_d20,
                     npa_o_f_d60, npa_o_f_d120, npa_o_f_d240,
                     fb_mc_rc_d1, fb_mc_rc_d5, fb_mc_rc_d10, fb_mc_rc_d20,
                     fb_mc_rc_d60, fb_mc_rc_d120, fb_mc_rc_d240)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                db.executemany(sql, rows)
                db.commit()
                total_rows += len(rows)

            if (i // BATCH) % 50 == 0:
                log.info(f"  [{i//BATCH+1}] {i+len(batch)}/{len(codes)} · {total_rows} 行")

            if i + BATCH < len(codes):
                time.sleep(0.3)

        except Exception as e:
            log.info(f"  ❌ 批次 [{i//BATCH+1}] 失败: {e}")
            failed_batches += 1

    elapsed = time.time() - start
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info(f"🐺 完成: {total_rows} 行, 失败 {failed_batches} 批, {elapsed:.0f}s")
    log.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
