"""
全量A股 CAN SLIM 批量评分

读取 config/canslim_scorecard.yaml，对全部A股逐一评分并入库。

用法:
  python scripts/batch_canslim_score.py                    # 增量（7天内已评分的跳过）
  python scripts/batch_canslim_score.py --force             # 强制全量重评
  python scripts/batch_canslim_score.py --limit 100         # 仅前100只
  python scripts/batch_canslim_score.py --workers 4         # 4线程并行

执行频率: 每周一 (daily_update.py 步骤11)
"""

import os, sys, time, sqlite3, json, argparse
from datetime import datetime, timedelta, date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / 'src'))

from scanners.canslim_score import score_stock, load_params

DB_PATH = PROJECT_DIR / "data" / "lixinger.db"


def get_stocks(limit=None):
    """获取全量正常上市A股"""
    conn = sqlite3.connect(str(DB_PATH))
    q = """SELECT stock_code, name FROM stock_basic
        WHERE listing_status='normally_listed'
        AND name NOT LIKE '%ST%' AND name NOT LIKE '%*ST%'
        ORDER BY stock_code"""
    if limit:
        q += " LIMIT %d" % limit
    rows = conn.execute(q).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def get_skip_set(days=7):
    """查询最近N天内已评分的股票"""
    conn = sqlite3.connect(str(DB_PATH))
    # 确保表存在
    conn.execute("""CREATE TABLE IF NOT EXISTS cansim_scores (
        stock_code TEXT, date TEXT, score_c REAL, score_a REAL, score_n REAL,
        score_s REAL, score_l REAL, score_i REAL, raw_total REAL,
        score INTEGER, grade TEXT, detail_json TEXT,
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        PRIMARY KEY (stock_code, date))""")
    conn.commit()
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    cur = conn.execute(
        "SELECT DISTINCT stock_code FROM cansim_scores WHERE date >= ?", (cutoff,))
    result = {r[0] for r in cur.fetchall()}
    conn.close()
    return result


def score_one(code, name, target_date, params, save):
    """评分单只股票"""
    try:
        r = score_stock(code, target_date, params=params, save=save)
        return code, name, r['score'], r['grade'], r
    except Exception as e:
        return code, name, None, None, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='强制全量重评')
    ap.add_argument('--limit', type=int, default=None, help='仅前N只')
    ap.add_argument('--workers', type=int, default=1, help='并行线程数（默认1=串行）')
    ap.add_argument('--date', type=str, default=None)
    args = ap.parse_args()

    target_date = args.date or date.today().strftime("%Y-%m-%d")
    params = load_params()

    stocks = get_stocks(args.limit)
    skip_set = set() if args.force else get_skip_set(7)
    todo = [(c, n) for c, n in stocks if c not in skip_set]

    print("Date: %s" % target_date)
    print("Stocks: %d total, %d skip, %d to score" % (
        len(stocks), len(skip_set), len(todo)))
    if not todo:
        print("All up to date.")
        return

    t0 = time.time()
    results = []

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(score_one, c, n, target_date, params, True): (c, n)
                       for c, n in todo}
            for f in as_completed(futures):
                results.append(f.result())
    else:
        for i, (code, name) in enumerate(todo):
            results.append(score_one(code, name, target_date, params, True))
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                print("  %d/%d (%.0fs)" % (i + 1, len(todo), elapsed))

    elapsed = time.time() - t0

    # 统计
    scored = [r for r in results if r[2] is not None]
    errors = [r for r in results if r[2] is None]

    grades = {}
    for _, _, s, g, _ in scored:
        grades[g] = grades.get(g, 0) + 1

    print()
    print("Done: %d stocks in %.0fs (%.1f s/stock)" % (
        len(scored), elapsed, elapsed / max(len(scored), 1)))
    if errors:
        print("Errors: %d" % len(errors))
    print("Grades: %s" % dict(sorted(grades.items())))

    # TOP 20
    top = sorted(scored, key=lambda x: -x[2])[:20]
    print("\nTOP 20:")
    for code, name, s, g, _ in top:
        print("  %s %s: %d pts %s" % (code, name, s, g))


if __name__ == "__main__":
    main()
