"""缠论分析引擎 - 基于 CZSC 库

计算流程: K线 → 分型 → 笔 → 中枢 → 买卖信号
数据持久化到 SQLite: chanlun_bi, chanlun_fx, chanlun_signals
"""

import sqlite3, pandas as pd, math
from datetime import datetime
from czsc import CZSC, RawBar, Freq

DB_PATH = r"D:\hanako\investment-system\data\lixinger.db"
SUPPORTED_FREQ = {"D": Freq.D, "W": Freq.W, "M": Freq.M}

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _ensure_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chanlun_bi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            freq TEXT NOT NULL,
            sdt TEXT NOT NULL,
            edt TEXT NOT NULL,
            direction TEXT NOT NULL,
            high REAL, low REAL,
            power REAL, slope REAL, angle REAL, length INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS chanlun_fx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            freq TEXT NOT NULL,
            dt TEXT NOT NULL,
            fx_type TEXT NOT NULL,
            high REAL, low REAL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_chanlun_bi_code ON chanlun_bi(stock_code, freq);
        CREATE INDEX IF NOT EXISTS idx_chanlun_fx_code ON chanlun_fx(stock_code, freq);
    """)
    conn.commit()

def analyze(code, freq="D", limit=500):
    """分析单只股票/指数的缠论结构
    
    Args:
        code: 股票代码 (如 000985)
        freq: K线周期 (D/W/M)
        limit: 读取K线数量
    
    Returns:
        dict: {bi_count, fx_count, signals, bi_list, fx_list}
    """
    freq_enum = SUPPORTED_FREQ.get(freq, Freq.D)
    table = "index_daily_kline" if code.startswith("000") or code.startswith("399") else "daily_kline"
    
    conn = _connect()
    df = pd.read_sql(f"""
        SELECT date, open, high, low, close, volume, amount
        FROM {table}
        WHERE stock_code = ?
        ORDER BY date DESC
        LIMIT ?
    """, conn, params=(code, limit))
    conn.close()
    
    if df.empty:
        return {"error": f"无K线数据: {code}"}
    
    df = df.sort_values("date").reset_index(drop=True)
    
    # 转换为 RawBar
    df["dt"] = pd.to_datetime(df["date"])
    bars = []
    for _, row in df.iterrows():
        bars.append(RawBar(
            symbol=code, dt=row["dt"].to_pydatetime(), freq=freq_enum,
            open=row.open, close=row.close, high=row.high, low=row.low,
            vol=row.volume, amount=row.amount
        ))
    
    # CZSC 计算
    czsc_obj = CZSC(bars)
    
    # 提取结果
    bi_list = []
    for bi in czsc_obj.bi_list:
        bi_list.append({
            "sdt": str(bi.sdt), "edt": str(bi.edt),
            "direction": bi.direction,
            "high": bi.high, "low": bi.low,
            "power": bi.power, "slope": bi.slope,
            "angle": bi.angle, "length": bi.length
        })
    
    fx_list = []
    for fx in czsc_obj.fx_list:
        fx_type = getattr(fx, 'fx_type', getattr(fx, 'fx', getattr(fx, 'direction', '?')))
        fx_list.append({
            "dt": str(fx.dt),
            "fx_type": str(fx_type),
            "high": fx.high, "low": fx.low
        })
    
    return {
        "code": code, "freq": freq,
        "kline_count": len(bars),
        "bi_count": len(bi_list),
        "fx_count": len(fx_list),
        "signals": czsc_obj.signals,
        "bi_list": bi_list,
        "fx_list": fx_list
    }

def save_to_db(code, freq, result):
    """将分析结果持久化到数据库"""
    conn = _connect()
    _ensure_tables(conn)
    
    # 清空旧数据
    conn.execute("DELETE FROM chanlun_bi WHERE stock_code=? AND freq=?", (code, freq))
    conn.execute("DELETE FROM chanlun_fx WHERE stock_code=? AND freq=?", (code, freq))
    
    # 写入笔
    for bi in result.get("bi_list", []):
        conn.execute("""
            INSERT INTO chanlun_bi (stock_code, freq, sdt, edt, direction, high, low, power, slope, angle, length)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, freq, bi["sdt"], bi["edt"], bi["direction"],
              bi["high"], bi["low"], bi["power"], bi["slope"], bi["angle"], bi["length"]))
    
    # 写入分型
    for fx in result.get("fx_list", []):
        conn.execute("""
            INSERT INTO chanlun_fx (stock_code, freq, dt, fx_type, high, low)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, freq, fx["dt"], fx["fx_type"], fx["high"], fx["low"]))
    
    conn.commit()
    conn.close()
    return True

def get_echarts_option(code, freq="D", limit=400, theme="dark"):
    """手动构建 ECharts option（CZSC Rust版暂不支持 to_echarts）"""
    freq_enum = SUPPORTED_FREQ.get(freq, Freq.D)
    table = "index_daily_kline" if code.startswith("000") or code.startswith("399") else "daily_kline"
    
    conn = _connect()
    df = pd.read_sql(f"""
        SELECT date, open, high, low, close, volume, amount
        FROM {table}
        WHERE stock_code = ?
        ORDER BY date DESC LIMIT ?
    """, conn, params=(code, limit))
    conn.close()
    
    if df.empty:
        return {"error": "无数据"}
    
    df = df.sort_values("date").reset_index(drop=True)
    df = df.fillna(0)  # JSON-safe
    dates = df["date"].tolist()
    
    # RawBar for CZSC
    df["dt"] = pd.to_datetime(df["date"])
    bars = [RawBar(symbol=code, dt=row["dt"].to_pydatetime(), freq=freq_enum,
                   open=row.open, close=row.close, high=row.high, low=row.low,
                   vol=row.volume, amount=row.amount) for _, row in df.iterrows()]
    
    czsc_obj = CZSC(bars)
    
    # 构建带涨跌幅的 K线数据
    ohlc_with_chg = []
    for i, (_, row) in enumerate(df.iterrows()):
        prev_close = df.iloc[i-1]["close"] if i > 0 else row.open
        chg_pct = (row.close - prev_close) / prev_close * 100 if prev_close else 0
        ohlc_with_chg.append([row.open, row.close, row.low, row.high, round(chg_pct, 2)])
    volumes = df["volume"].tolist()
    
    # 构建笔的 markLine 数据
    mark_points = []
    for bi in czsc_obj.bi_list:
        try:
            sdt_str = str(bi.sdt)[:10]
            edt_str = str(bi.edt)[:10]
            if sdt_str in dates:
                idx = dates.index(sdt_str)
                mark_points.append({
                    "name": "笔" + ("顶" if bi.direction == "down" else "底"),
                    "coord": [idx, bi.high if bi.direction == "down" else bi.low],
                    "value": ("顶" if bi.direction == "down" else "底") + " " + str(round(bi.high if bi.direction == "down" else bi.low, 1)),
                    "symbol": "pin",
                    "symbolSize": 14,
                    "itemStyle": {"color": up_color if bi.direction == "down" else down_color}
                })
        except: pass
    
    # 构建笔的 markArea
    mark_areas = []
    for bi in czsc_obj.bi_list:
        try:
            s = str(bi.sdt)[:10]
            e = str(bi.edt)[:10]
            if s in dates and e in dates:
                si = dates.index(s)
                ei = dates.index(e)
                is_up = bi.direction == "up"
                mark_areas.append([
                    {"xAxis": si, "yAxis": bi.low, "itemStyle": {"color": "rgba(239,68,68,0.05)" if is_up else "rgba(16,185,129,0.05)"}},
                    {"xAxis": ei, "yAxis": bi.high}
                ])
        except: pass
    
    # hanako-glass 配色 (根据主题动态)
    is_dark = theme == "dark"
    chart_bg = "rgba(26,26,31,.6)" if is_dark else "rgba(255,255,255,.75)"
    axis_color = "rgba(200,200,200,0.3)" if is_dark else "rgba(128,128,128,0.3)"
    grid_color = "rgba(200,200,200,0.08)" if is_dark else "rgba(128,128,128,0.1)"
    up_color = "#ef4444" if is_dark else "#dc2626"
    down_color = "#10b981" if is_dark else "#059669"
    vol_color = up_color  # 成交量与K线同色：红涨绿跌
    vol_color0 = down_color
    
    # 成交量数据（红涨绿跌）
    vol_data = []
    for _, row in df.iterrows():
        is_up = row.close >= row.open
        vol_data.append({"value": int(row.volume), "itemStyle": {"color": up_color if is_up else down_color}})
    
    return {
        "backgroundColor": chart_bg,
        "animation": False,
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross", "crossStyle": {"color": axis_color}},
            "backgroundColor": "rgba(20,20,25,0.95)" if is_dark else "rgba(255,255,255,0.95)",
            "borderColor": "rgba(255,255,255,0.06)" if is_dark else "rgba(0,0,0,0.08)",
            "textStyle": {"fontSize": 11, "color": "#e4e4e7" if is_dark else "#1a1a2e"},
            "formatter": "function(p){var k=p[0];if(!k)return'';var d=k.data;var chg=d[4]!=null?d[4].toFixed(2):'0.00';var col=chg>=0?'"+up_color+"':'"+down_color+"';var s='<b>'+k.axisValue+'</b><br/>开: '+d[0].toFixed(2)+'<br/>收: <b style=color:'+col+'>'+d[1].toFixed(2)+'</b><br/>高: '+d[3].toFixed(2)+'<br/>低: '+d[2].toFixed(2)+'<br/>涨跌: <b style=color:'+col+'>'+(chg>=0?'+':'')+chg+'%</b>';return s}"},
        "legend": {"data": ["K线", "成交量"], "bottom": 20, "textStyle": {"color": axis_color, "fontSize": 10}, "selectedMode": True},
        "grid": [{"left": "8%", "right": "4%", "top": 8, "height": "60%"},
                 {"left": "8%", "right": "4%", "top": "75%", "height": "15%"}],
        "xAxis": [{"type": "category", "data": dates, "axisLabel": {"color": axis_color, "fontSize": 9},
                    "axisLine": {"lineStyle": {"color": grid_color}}},
                  {"type": "category", "gridIndex": 1, "data": dates, "axisLabel": {"show": False},
                    "axisLine": {"lineStyle": {"color": grid_color}}}],
        "yAxis": [{"type": "value", "scale": True, "axisLabel": {"color": axis_color, "fontSize": 9},
                    "splitLine": {"lineStyle": {"color": grid_color}}},
                  {"type": "value", "gridIndex": 1, "axisLabel": {"color": axis_color, "fontSize": 9},
                    "splitLine": {"show": False}}],
        "dataZoom": [{"type": "inside", "start": 70, "end": 100},
                     {"type": "slider", "start": 70, "end": 100, "height": 16, "bottom": 4}],
        "series": [
            {"name": "K线", "type": "candlestick", "data": ohlc_with_chg,
             "itemStyle": {"color": up_color, "color0": down_color,
                           "borderColor": up_color, "borderColor0": down_color},
             "markPoint": {"data": mark_points, "symbol": "pin", "symbolSize": 14}},
            {"name": "成交量", "type": "bar", "xAxisIndex": 1, "yAxisIndex": 1, "data": vol_data}
        ]
    }


if __name__ == "__main__":
    # 快速测试
    r = analyze("000985", "D", 300)
    print(f"笔: {r['bi_count']}, 分型: {r['fx_count']}")
    if r["bi_list"]:
        last = r["bi_list"][-1]
        print(f"最新笔: {last['direction']} {last['sdt'][:10]}→{last['edt'][:10]} {last['low']:.1f}~{last['high']:.1f}")
