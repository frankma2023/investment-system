import traceback, sys, sqlite3, os
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))

# Check for NULL values
db = sqlite3.connect(os.path.join(PROJECT_DIR, 'data', 'lixinger.db'))
for col in ['close', 'volume', 'open', 'high', 'low']:
    n = db.execute(f"SELECT COUNT(*) FROM daily_kline WHERE {col} IS NULL").fetchone()[0]
    print(f"{col} IS NULL: {n}")
n = db.execute("SELECT COUNT(*) FROM daily_kline WHERE volume=0").fetchone()[0]
print(f"volume=0: {n}")

# Test base_breakout on a small sample
try:
    from scanners.base_breakout import detect, load_params
    db.row_factory = sqlite3.Row
    for code in ['000001', '600519', '300750', '688981']:
        rows = db.execute(f"SELECT date, open, high, low, close, volume FROM daily_kline WHERE stock_code='{code}' ORDER BY date DESC LIMIT 500").fetchall()
        daily = [dict(r) for r in rows]
        daily.reverse()
        try:
            signals = detect(daily, load_params())
            print(f"{code}: {len(signals)} OK")
        except Exception as e:
            print(f"{code}: ERROR - {type(e).__name__}: {e}")
except Exception as e:
    traceback.print_exc()

db.close()
# Clean up self
os.remove(__file__)
