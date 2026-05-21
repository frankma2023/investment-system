import sqlite3, json
conn = sqlite3.connect(r'D:\hanako\investment-system\data\lixinger.db')
cur = conn.cursor()
# Check how many have signals_json
cur.execute("SELECT COUNT(*) FROM discipline_observation_pool WHERE date='2026-05-20' AND signals_json IS NOT NULL")
sig_count = cur.fetchone()[0]
print(f"With signals_json: {sig_count}")

# Get a sample
cur.execute("SELECT stock_code, signals_json FROM discipline_observation_pool WHERE date='2026-05-20' AND signals_json IS NOT NULL LIMIT 3")
for row in cur.fetchall():
    sj = json.loads(row[1])
    print(f"  {row[0]}: {len(sj)} signals")
    for s in sj[:2]:
        print(f"    - {s.get('type') or s.get('pattern')}: {s.get('date')}")

conn.close()
