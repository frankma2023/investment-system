import sqlite3
conn = sqlite3.connect(r'D:\hanako\investment-system\data\lixinger.db')
try:
    conn.execute("ALTER TABLE discipline_observation_pool ADD COLUMN signals_json TEXT")
    print("signals_json column added")
except sqlite3.OperationalError as e:
    if 'duplicate column' in str(e).lower():
        print("Column already exists")
    else:
        print(f"Error: {e}")
conn.commit()
conn.close()
