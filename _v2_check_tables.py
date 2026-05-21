import sqlite3
conn = sqlite3.connect(r'D:\hanako\investment-system\data\lixinger.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%inst%' OR name LIKE '%sector%' OR name LIKE '%canslim%' OR name LIKE '%rs_daily%' OR name LIKE '%financial%')")
for r in cur.fetchall():
    print(r[0])

# Check cansim_scores columns
cur.execute("SELECT * FROM cansim_scores LIMIT 1")
cols = [d[0] for d in cur.description]
print(f"\ncansim_scores cols: {cols}")

# Check stock_financials_annual
cur.execute("SELECT * FROM stock_financials_annual LIMIT 1")
cols = [d[0] for d in cur.description]
print(f"stock_financials_annual cols: {cols}")

conn.close()
