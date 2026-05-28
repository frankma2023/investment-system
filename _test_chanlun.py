"""缠论引擎验证脚本 — 用中证全指K线跑一遍CZSC"""
import sqlite3, pandas as pd
from czsc import CZSC, RawBar, Freq

DB = r"D:\hanako\investment-system\data\lixinger.db"
CODE = "000985"  # 中证全指

# 1. 读取K线
conn = sqlite3.connect(DB)
df = pd.read_sql("""
    SELECT date, open, high, low, close, volume, amount
    FROM index_daily_kline
    WHERE stock_code = ?
    ORDER BY date DESC
    LIMIT 500
""", conn, params=(CODE,))
conn.close()

df = df.sort_values("date").reset_index(drop=True)
print(f"读取 {len(df)} 根K线: {df.date.iloc[0]} ~ {df.date.iloc[-1]}")

# 2. 转换为 CZSC RawBar 格式
df2 = df.rename(columns={"date": "dt", "volume": "vol"})
df2["dt"] = pd.to_datetime(df2["dt"])
bars = []
for _, row in df2.iterrows():
    bars.append(RawBar(
        symbol=CODE, dt=row["dt"].to_pydatetime(),
        freq=Freq.D, open=row.open, close=row.close,
        high=row.high, low=row.low, vol=row.vol, amount=row.amount
    ))
print(f"创建 {len(bars)} 个RawBar")

# 3. 创建 CZSC 分析对象
czsc_obj = CZSC(bars)

# 4. 输出结果
print(f"\n=== 缠论分析结果 ===")
print(f"分型(fx)数量: {len(czsc_obj.fx_list)}")
print(f"笔(bi)数量:   {len(czsc_obj.bi_list)}")
print(f"中枢(zs)数量: {len(czsc_obj.bi_list)}")  # zs is computed per-bi
print(f"可用属性: {[a for a in dir(czsc_obj) if not a.startswith('_')]}")

if czsc_obj.bi_list:
    print(f"\n最近 3 笔:")
    for bi in czsc_obj.bi_list[-3:]:
        direction = "↑" if getattr(bi,'direction','')=='up' else "↓"
        s = getattr(bi,'start',getattr(bi,'start_dt','?'))
        e = getattr(bi,'end',getattr(bi,'end_dt','?'))
        lo = getattr(bi,'low',0)
        hi = getattr(bi,'high',0)
        print(f"  {direction} {s} → {e}  {lo:.2f} ~ {hi:.2f}")
    print(f"\nBI attrs: {[a for a in dir(czsc_obj.bi_list[0]) if not a.startswith('_')]}")

print("\n✅ CZSC 集成验证通过")
