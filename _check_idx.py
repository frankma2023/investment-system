import sqlite3
db=sqlite3.connect(r'D:\hanako\investment-system\data\lixinger.db')
db.row_factory=sqlite3.Row
code='931743'

rs=db.execute("SELECT * FROM index_rs_daily WHERE stock_code=? ORDER BY date DESC LIMIT 1",(code,)).fetchone()
if rs:
    print(f"RS: 20={rs['rs_20']} 60={rs['rs_60']} 120={rs['rs_120']} 250={rs['rs_250']}")

kl=db.execute("SELECT date,close FROM index_daily_kline WHERE stock_code=? AND kline_type='normal' ORDER BY date DESC LIMIT 70",(code,)).fetchall()
kl=list(reversed(kl))
closes=[k['close'] for k in kl]
def ma(a,n):
    if len(a)<n: return None
    return sum(a[-n:])/n
ma10=ma(closes,10); ma50=ma(closes,50)
latest=closes[-1]; ld=kl[-1]['date']
chg=db.execute("SELECT change FROM index_daily_kline WHERE stock_code=? AND kline_type='normal' ORDER BY date DESC LIMIT 1",(code,)).fetchone()
cp=(chg['change'] or 0)*100 if chg else 0
print(f"Date:{ld} Close:{latest:.2f} Chg:{cp:.2f}% MA10:{ma10:.2f} MA50:{ma50:.2f}")
print(f"Below MA10:{latest<ma10} Below MA50:{latest<ma50}")

h52=db.execute("SELECT MAX(close) FROM index_daily_kline WHERE stock_code=? AND kline_type='normal' AND date>=date(?,'-365 days')",(code,ld)).fetchone()
if h52 and h52[0]:
    p=(latest-h52[0])/h52[0]*100
    print(f"52W High:{h52[0]:.2f} Dist:{p:.1f}%")

dd=db.execute("SELECT COUNT(*) c FROM distribution_days_detail WHERE stock_code=? AND date>=date(?,'-25 days')",(code,ld)).fetchone()
print(f"DD(25d):{dd['c']}")

db.close()
