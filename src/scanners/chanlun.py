"""缠论分析引擎 - 基于 CZSC 库

计算流程: K线 → 分型 → 笔 → 中枢 → 背驰 → 买卖信号
数据持久化到 SQLite: chanlun_bi, chanlun_fx, chanlun_zs, chanlun_signals

v2.0 (2026-05-28): 新增中枢检测、背驰诊断、买卖信号生成
"""

import sqlite3, pandas as pd, math, json
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
        CREATE TABLE IF NOT EXISTS chanlun_zs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            freq TEXT NOT NULL,
            start_dt TEXT NOT NULL,
            end_dt TEXT NOT NULL,
            zg REAL, zd REAL, zz REAL,
            bi_count INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_chanlun_bi_code ON chanlun_bi(stock_code, freq);
        CREATE INDEX IF NOT EXISTS idx_chanlun_fx_code ON chanlun_fx(stock_code, freq);
        CREATE INDEX IF NOT EXISTS idx_chanlun_zs_code ON chanlun_zs(stock_code, freq);
    """)
    conn.commit()


# ═══════════════════════════════════════════════
# 中枢检测
# ═══════════════════════════════════════════════

def compute_zhongshu(bi_list_raw):
    """从笔列表计算中枢（连续3笔重叠法）
    
    缠论定义：连续三段次级别走势类型（笔）重叠部分构成中枢。
    这里用简化版：滑动窗口检测每3笔是否有重叠区间。
    
    Args:
        bi_list_raw: CZSC 的 BI 对象列表
    
    Returns:
        list[dict]: 每项 {start_dt, end_dt, zg, zd, zz, width, bi_indices}
    """
    n = len(bi_list_raw)
    if n < 3:
        return []
    
    zs_list = []
    i = 0
    while i <= n - 3:
        b0, b1, b2 = bi_list_raw[i], bi_list_raw[i+1], bi_list_raw[i+2]
        ZG = min(b0.high, b1.high, b2.high)
        ZD = max(b0.low, b1.low, b2.low)
        
        if ZG > ZD and ZG > 0 and ZD > 0:
            ZZ = (ZG + ZD) / 2  # 中枢中轴
            zs_list.append({
                "start_dt": str(b0.sdt)[:10],
                "end_dt": str(b2.edt)[:10],
                "zg": float(ZG),
                "zd": float(ZD),
                "zz": float(ZZ),
                "width": float(ZG - ZD),
                "width_pct": round(float(ZG - ZD) / float(ZZ) * 100, 2) if ZZ else 0,
                "bi_indices": [i, i+1, i+2],
                "bi_dirs": [str(b0.direction), str(b1.direction), str(b2.direction)]
            })
            # 有重叠 → 可能有延伸，检查下一笔
            i += 1
        else:
            i += 1
    
    # 合并连续重叠的中枢（简化：相邻且重叠则合并为一个延伸中枢）
    merged = []
    for zs in zs_list:
        if not merged:
            merged.append(zs)
            continue
        last = merged[-1]
        # 如果两个中枢在日期上相邻（bi_indices 连续），且价格区间重叠>50%
        overlap_low = max(zs["zd"], last["zd"])
        overlap_high = min(zs["zg"], last["zg"])
        if overlap_high > overlap_low:
            overlap_pct = (overlap_high - overlap_low) / (zs["zg"] - zs["zd"]) if (zs["zg"] - zs["zd"]) else 0
            if overlap_pct > 0.5 and zs["bi_indices"][0] > last["bi_indices"][0]:
                # 延伸：扩展 end_dt 和 bi_indices
                last["end_dt"] = zs["end_dt"]
                last["zg"] = min(last["zg"], zs["zg"])
                last["zd"] = max(last["zd"], zs["zd"])
                last["zz"] = (last["zg"] + last["zd"]) / 2
                last["width"] = last["zg"] - last["zd"]
                last["bi_indices"].extend(zs["bi_indices"])
                last["bi_dirs"].extend(zs["bi_dirs"])
                continue
        merged.append(zs)
    
    # 去重 & 给每个中枢编号
    for idx, zs in enumerate(merged):
        zs["idx"] = idx + 1
        unique_bi = list(set(zs["bi_indices"]))
        unique_bi.sort()
        zs["bi_count"] = len(unique_bi)
    
    return merged


# ═══════════════════════════════════════════════
# 背驰检测
# ═══════════════════════════════════════════════

def detect_divergence(bi_list_raw, zs_list):
    """检测背驰信号
    
    两类背驰：
    1. 趋势背驰：中枢前后两段同向趋势的力度衰减
    2. 盘整背驰：中枢内部震荡的力度衰减
    
    Returns:
        list[dict]: 背驰信号列表
    """
    signals = []
    n = len(bi_list_raw)
    if n < 5:
        return signals
    
    # ── 趋势背驰 ──
    # 缠论笔是严格交替的（上→下→上→下），需比较间隔的同向笔
    # 即笔[i] vs 笔[i+2]（中间隔一个反向笔）
    for i in range(0, n - 2):
        prev_bi = bi_list_raw[i]
        curr_bi = bi_list_raw[i+2]  # 间隔一个反向笔
        
        # 必须同向
        if prev_bi.direction != curr_bi.direction:
            continue
        
        # 同向笔比较力度
        if prev_bi.power and curr_bi.power and prev_bi.power > 0:
            power_ratio = curr_bi.power / prev_bi.power
            
            # 力度衰减阈值：< 0.6 视为背驰（调整后更敏感）
            if power_ratio < 0.6:
                direction_str = str(curr_bi.direction)
                # 向上笔力度衰减 = 顶背驰
                sig_type = "顶背驰" if direction_str in ("up", "向上") else "底背驰"
                
                signals.append({
                    "type": sig_type,
                    "category": "趋势背驰",
                    "dt": str(curr_bi.sdt)[:10],
                    "bi_idx": i + 2,
                    "prev_bi_idx": i,
                    "power_ratio": round(power_ratio, 2),
                    "prev_power": round(float(prev_bi.power), 1),
                    "curr_power": round(float(curr_bi.power), 1),
                    "price_ampl_ratio": round(float(curr_bi.high - curr_bi.low) / float(prev_bi.high - prev_bi.low), 2) 
                        if (prev_bi.high - prev_bi.low) > 0 else 0,
                    "severity": "强" if power_ratio < 0.3 else "中" if power_ratio < 0.45 else "弱"
                })
    
    # ── 盘整背驰 ──
    # 中枢内部：检查离开中枢的笔是否背驰
    for zs in zs_list:
        bi_indices = zs.get("bi_indices", [])
        if len(bi_indices) < 4:
            continue
        
        # 中枢第一笔（进入中枢）和最后一笔（离开中枢）同向则比较
        first_bi_idx = bi_indices[0]
        last_bi_idx = bi_indices[-1]
        if last_bi_idx < n and first_bi_idx < n:
            first_bi = bi_list_raw[first_bi_idx]
            last_bi = bi_list_raw[last_bi_idx]
            if first_bi.direction == last_bi.direction and first_bi.power and last_bi.power and first_bi.power > 0:
                power_ratio = last_bi.power / first_bi.power
                if power_ratio < 0.6:
                    direction_str = str(last_bi.direction)
                    sig_type = "盘整顶背驰" if direction_str == "up" or direction_str == "向上" else "盘整底背驰"
                    signals.append({
                        "type": sig_type,
                        "category": "盘整背驰",
                        "dt": str(last_bi.sdt)[:10],
                        "bi_idx": last_bi_idx,
                        "zs_idx": zs.get("idx", 0),
                        "power_ratio": round(power_ratio, 2),
                        "prev_power": round(float(first_bi.power), 1),
                        "curr_power": round(float(last_bi.power), 1),
                        "severity": "强" if power_ratio < 0.4 else "中" if power_ratio < 0.5 else "弱"
                    })
    
    # 按日期倒序排列（最新在前）
    signals.sort(key=lambda x: x["dt"], reverse=True)
    return signals


# ═══════════════════════════════════════════════
# 买卖信号生成
# ═══════════════════════════════════════════════

def generate_trade_signals(bi_list_raw, zs_list, divergence_signals):
    """基于中枢和背驰生成缠论买卖信号
    
    一买：下跌趋势 + 底背驰 → 趋势反转点
    二买：一买后回调不破新低 → 确认信号
    三买：中枢上方回调不破ZG → 强势信号
    一卖：上涨趋势 + 顶背驰 → 趋势反转点
    二卖：一卖后反弹不破新高 → 确认信号
    三卖：中枢下方反弹不破ZD → 弱势信号
    """
    trade_sigs = []
    
    # 解析趋势背驰 → 一类买卖点
    for div in divergence_signals:
        if div["category"] != "趋势背驰":
            continue
        
        bi_idx = div.get("bi_idx", 0)
        prev_bi_idx = div.get("prev_bi_idx", 0)
        if bi_idx >= len(bi_list_raw) or prev_bi_idx >= len(bi_list_raw):
            continue
        
        curr_bi = bi_list_raw[bi_idx]
        direction = str(curr_bi.direction)
        
        # 底背驰（向下笔力度衰减） → 一买
        if direction in ("down", "向下") and div["type"] == "底背驰":
            trade_sigs.append({
                "type": "一买",
                "side": "buy",
                "dt": str(curr_bi.sdt)[:10],
                "price": round(float(curr_bi.low), 2),
                "reason": f"下跌趋势底背驰（力度比{div['power_ratio']}），可能趋势反转",
                "confidence": {"强": "高", "中": "中"}.get(div["severity"], "低"),
                "div_signal": div["type"]
            })
        
        # 顶背驰（向上笔力度衰减） → 一卖
        if direction in ("up", "向上") and div["type"] == "顶背驰":
            trade_sigs.append({
                "type": "一卖",
                "side": "sell",
                "dt": str(curr_bi.sdt)[:10],
                "price": round(float(curr_bi.high), 2),
                "reason": f"上涨趋势顶背驰（力度比{div['power_ratio']}），可能趋势反转",
                "confidence": {"强": "高", "中": "中"}.get(div["severity"], "低"),
                "div_signal": div["type"]
            })
    
    # 二买/三买检测（基于中枢位置）
    for zs in zs_list:
        bi_indices = zs.get("bi_indices", [])
        if len(bi_indices) < 4:
            continue
        ZG = zs["zg"]
        ZD = zs["zd"]
        last_bi_idx = bi_indices[-1]
        
        # 三买：中枢上方回调不破ZG（离开中枢后回踩不破ZG）
        if last_bi_idx + 2 < len(bi_list_raw):
            out_bi = bi_list_raw[last_bi_idx + 1]  # 离开中枢的笔
            ret_bi = bi_list_raw[last_bi_idx + 2]  # 回踩的笔
            out_dir = str(out_bi.direction)
            ret_dir = str(ret_bi.direction)
            
            if out_dir in ("up", "向上") and ret_dir in ("down", "向下"):
                # 向上离开后向下回踩，不破ZG
                if ret_bi.low > ZG:
                    trade_sigs.append({
                        "type": "三买",
                        "side": "buy",
                        "dt": str(ret_bi.sdt)[:10],
                        "price": round(float(ret_bi.low), 2),
                        "reason": f"中枢上方回调不破ZG({ZG:.1f})，强势确认",
                        "confidence": "高",
                        "zs_idx": zs.get("idx", 0)
                    })
            
            if out_dir in ("down", "向下") and ret_dir in ("up", "向上"):
                # 向下离开后向上回抽，不破ZD
                if ret_bi.high < ZD:
                    trade_sigs.append({
                        "type": "三卖",
                        "side": "sell",
                        "dt": str(ret_bi.sdt)[:10],
                        "price": round(float(ret_bi.high), 2),
                        "reason": f"中枢下方反弹不破ZD({ZD:.1f})，弱势确认",
                        "confidence": "高",
                        "zs_idx": zs.get("idx", 0)
                    })
    
    # 按日期倒序排列（最新在前）
    trade_sigs.sort(key=lambda x: x["dt"], reverse=True)
    
    return trade_sigs


# ═══════════════════════════════════════════════
# 主分析函数
# ═══════════════════════════════════════════════

def analyze(code, freq="D", limit=500):
    """分析单只股票/指数的缠论结构
    
    Args:
        code: 股票代码 (如 000985)
        freq: K线周期 (D/W/M)
        limit: 读取K线数量
    
    Returns:
        dict: {kline_count, bi_count, fx_count, zs_count, divergence_count,
               bi_list, fx_list, zs_list, divergence_signals, trade_signals}
    """
    freq_enum = SUPPORTED_FREQ.get(freq, Freq.D)
    table = "index_daily_kline" if code.startswith("000") or code.startswith("399") else "daily_kline"
    
    # 日线数据读取范围：按日期回溯，确保三种周期都覆盖约 3 年
    # 日线模式用 max(limit, 750)；周/月线需要更多日线来合成
    if freq == "D":
        read_limit = max(limit, 750)
    else:
        read_limit = max(limit * 3, 900)
    
    conn = _connect()
    df = pd.read_sql(f"""
        SELECT date, open, high, low, close, volume, amount
        FROM {table}
        WHERE stock_code = ?
        ORDER BY date DESC
        LIMIT ?
    """, conn, params=(code, read_limit))
    conn.close()
    
    if df.empty:
        return {"error": f"无K线数据: {code}"}
    
    df = df.sort_values("date").reset_index(drop=True)
    
    # 转换为 RawBar
    df["dt"] = pd.to_datetime(df["date"])
    bars = []
    for _, row in df.iterrows():
        bars.append(RawBar(
            symbol=code, dt=row["dt"], freq=freq_enum,
            open=row.open, close=row.close, high=row.high, low=row.low,
            vol=row.volume, amount=row.amount
        ))
    
    # CZSC 计算
    czsc_obj = CZSC(bars)
    
    # ── 提取笔列表 ──
    bi_list = []
    for bi in czsc_obj.bi_list:
        bi_list.append({
            "sdt": str(bi.sdt),
            "edt": str(bi.edt),
            "direction": str(bi.direction),
            "high": float(bi.high) if bi.high is not None and bi.high == bi.high else 0,
            "low": float(bi.low) if bi.low is not None and bi.low == bi.low else 0,
            "power": float(bi.power) if bi.power is not None and bi.power == bi.power else 0,
            "slope": float(bi.slope) if bi.slope is not None and bi.slope == bi.slope else 0,
            "angle": float(bi.angle) if bi.angle is not None and bi.angle == bi.angle else 0,
            "length": int(bi.length) if bi.length else 0
        })
    
    # ── 提取分型列表 ──
    fx_list = []
    for fx in czsc_obj.fx_list:
        fx_type = getattr(fx, 'mark', getattr(fx, 'fx_type', getattr(fx, 'fx', '?')))
        fx_list.append({
            "dt": str(fx.dt),
            "fx_type": str(fx_type),
            "high": float(fx.high) if fx.high is not None and fx.high == fx.high else 0,
            "low": float(fx.low) if fx.low is not None and fx.low == fx.low else 0
        })
    
    # ── 中枢检测 ──
    zs_list = compute_zhongshu(czsc_obj.bi_list)
    
    # ── 背驰检测 ──
    divergence_signals = detect_divergence(czsc_obj.bi_list, zs_list)
    
    # ── 买卖信号 ──
    trade_signals = generate_trade_signals(czsc_obj.bi_list, zs_list, divergence_signals)
    
    # ── 未完成笔 ──
    ubi_info = None
    if czsc_obj.ubi:
        ubi_info = {
            "direction": str(czsc_obj.ubi.get("direction", "?")),
            "high": float(czsc_obj.ubi.get("high", 0)),
            "low": float(czsc_obj.ubi.get("low", 0))
        }
    
    return {
        "code": code,
        "freq": freq,
        "kline_count": len(bars),
        "bi_count": len(bi_list),
        "fx_count": len(fx_list),
        "zs_count": len(zs_list),
        "divergence_count": len(divergence_signals),
        "trade_signal_count": len(trade_signals),
        "ubi": ubi_info,
        "bi_list": bi_list,
        "fx_list": fx_list,
        "zs_list": zs_list,
        "divergence_signals": divergence_signals,
        "trade_signals": trade_signals
    }


# ═══════════════════════════════════════════════
# K线周期合成（日→周/月）
# ═══════════════════════════════════════════════

def _synthesize_klines(df, target_freq):
    """从日线 DataFrame 合成周线或月线 OHLC
    
    Args:
        df: 日线 DataFrame（含 date, open, high, low, close, volume, amount）
        target_freq: "W" 或 "M"
    
    Returns:
        DataFrame: 合成后的 OHLC，含 period_date 列
    """
    df = df.copy()
    df["date_dt"] = pd.to_datetime(df["date"])
    df = df.set_index("date_dt").sort_index()
    
    if target_freq == "W":
        # 周线：按周五收盘日合成（A股周五是每周最后交易日）
        rule = "W-FRI"
        label = "right"
    elif target_freq == "M":
        # 月线：按月最后一天合成
        rule = "ME"
        label = "right"
    else:
        return df.reset_index().rename(columns={"date_dt": "period_date"})
    
    resampled = df.resample(rule, label=label, closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum"
    }).dropna()
    
    # 如果该周/月只有一个交易日，跳过（不完整的周期）
    # 实际按 A 股规则：少于 2 个交易日的周期也保留
    
    resampled = resampled.reset_index()
    resampled["period_date"] = resampled["date_dt"].dt.strftime("%Y-%m-%d")
    return resampled


def _build_period_index_map(daily_df, target_freq, period_dates):
    """构建 日线日期 → 合成周期索引 的映射表
    
    例如：3月24日~3月28日这周的日线日期都映射到该周K线的索引
    
    Args:
        daily_df: 日线 DataFrame
        target_freq: "W" 或 "M"
        period_dates: 合成后的周期日期列表
    
    Returns:
        dict: {日线日期str: 周期索引int}
    """
    date_idx = {}
    daily_df = daily_df.copy()
    daily_df["dt"] = pd.to_datetime(daily_df["date"])
    
    for i, period_str in enumerate(period_dates):
        period_dt = pd.to_datetime(period_str)
        
        if target_freq == "W":
            # 该周：period_dt 所在周的周一~period_dt（周五）
            week_start = period_dt - pd.Timedelta(days=period_dt.weekday())
            mask = (daily_df["dt"] >= week_start) & (daily_df["dt"] <= period_dt)
        else:  # "M"
            # 该月：period_dt 所在月的第一天~最后一天
            month_start = period_dt.replace(day=1)
            # 下月第一天减一天 = 本月最后一天
            if period_dt.month == 12:
                month_end = period_dt.replace(year=period_dt.year+1, month=1, day=1) - pd.Timedelta(days=1)
            else:
                month_end = period_dt.replace(month=period_dt.month+1, day=1) - pd.Timedelta(days=1)
            mask = (daily_df["dt"] >= month_start) & (daily_df["dt"] <= month_end)
        
        matched_dates = daily_df.loc[mask, "date"].tolist()
        for d in matched_dates:
            date_idx[d] = i
    
    return date_idx


# ═══════════════════════════════════════════════
# ECharts 配置生成
# ═══════════════════════════════════════════════

def get_echarts_option(code, freq="D", limit=400, theme="dark"):
    """构建 ECharts option（含 K线 + 成交量 + 笔标记 + 中枢矩形 + 买卖点）
    
    当 freq="W" 或 "M" 时，K线图使用从日线合成的周/月 K线，
    而非原始日线 K线。CZSC 仍基于日线 RawBar 计算笔/中枢（freq 参数控制级别）。
    
    日线数据读取范围：按日期回溯 3 年（约 750 根日线），确保周/月合成后
    仍有足够数量的 K 线（周线约 150 根，月线约 36 根）。
    """
    from datetime import date, timedelta
    
    freq_enum = SUPPORTED_FREQ.get(freq, Freq.D)
    table = "index_daily_kline" if code.startswith("000") or code.startswith("399") else "daily_kline"
    chg_col = "change" if table == "index_daily_kline" else "change_pct"
    
    # 日线需要足够多数据来合成周/月线：按日期范围回溯 3 年
    if freq == "D":
        read_limit = max(limit, 750)
    else:
        read_limit = max(limit * 3, 900)  # 周/月线需要大量日线来合成
    
    conn = _connect()
    df = pd.read_sql(f"""
        SELECT date, open, high, low, close, volume, amount, {chg_col} as change
        FROM {table}
        WHERE stock_code = ?
        ORDER BY date DESC LIMIT ?
    """, conn, params=(code, read_limit))
    conn.close()
    
    if df.empty:
        return {"error": "无数据"}
    
    df = df.sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["open", "close", "high", "low"])
    
    # ── 日线 RawBar → CZSC（始终用日线，freq 参数控制笔/中枢的级别处理）──
    df["dt"] = pd.to_datetime(df["date"])
    bars = [RawBar(symbol=code, dt=row["dt"], freq=freq_enum,
                   open=row.open, close=row.close, high=row.high, low=row.low,
                   vol=row.volume, amount=row.amount) for _, row in df.iterrows()]
    czsc_obj = CZSC(bars)
    
    # ── K线数据：日线直接使用，周/月线合成 ──
    if freq == "D":
        ohlc_df = df.copy()
        ohlc_df["period_date"] = df["date"]
    else:
        ohlc_df = _synthesize_klines(df, freq)
    
    dates = ohlc_df["period_date"].tolist()
    
    # 构建 date → index 映射（bi 的日线日期 → 合成后的周/月索引）
    if freq == "D":
        date_idx = {d: i for i, d in enumerate(dates)}
    else:
        # 日线日期 → 所属周期日期 → 合成索引
        date_idx = _build_period_index_map(df, freq, dates)
    
    # ── hanako-glass 配色 ──
    is_dark = theme == "dark"
    chart_bg = "rgba(26,26,31,.6)" if is_dark else "rgba(255,255,255,.75)"
    axis_color = "rgba(200,200,200,0.3)" if is_dark else "rgba(128,128,128,0.3)"
    grid_color = "rgba(200,200,200,0.08)" if is_dark else "rgba(128,128,128,0.1)"
    up_color = "#ef4444" if is_dark else "#dc2626"
    down_color = "#10b981" if is_dark else "#059669"
    
    # ── K线数据 ──
    ohlc_data = [[row.open, row.close, row.low, row.high] for _, row in ohlc_df.iterrows()]
    
    # ── 成交量数据 ──
    vol_data = []
    for _, row in ohlc_df.iterrows():
        is_up = row.close >= row.open
        vol_data.append({"value": int(row.volume), "itemStyle": {"color": up_color if is_up else down_color}})
    
    # ── 笔标记 (markPoint) ──
    mark_points = []
    for bi in czsc_obj.bi_list:
        try:
            s = str(bi.sdt)[:10]
            if s in date_idx:
                idx = date_idx[s]
                is_down = str(bi.direction) in ("down", "向下")
                mark_points.append({
                    "name": "笔顶" if is_down else "笔底",
                    "coord": [idx, float(bi.high) if is_down else float(bi.low)],
                    "value": ("顶" if is_down else "底") + str(round(float(bi.high if is_down else bi.low), 0)),
                    "symbol": "arrow",
                    "symbolRotate": 0 if is_down else 180,
                    "symbolSize": 10,
                    "symbolOffset": [0, -6 if is_down else 6],
                    "itemStyle": {"color": up_color if is_down else down_color},
                    "label": {"show": True, "fontSize": 8, "fontWeight": "normal",
                              "color": up_color if is_down else down_color,
                              "offset": [0, -10] if is_down else [0, 10]}
                })
        except Exception:
            pass
    
    # ── 中枢矩形 (markArea) ──
    zs_list = compute_zhongshu(czsc_obj.bi_list)
    zs_mark_areas = []
    zs_mark_lines = []  # ZG/ZD 线
    
    # 中枢配色 (按层级深浅)
    zs_colors = {
        0: "rgba(245,158,11,0.12)",    # 金色（第一层中枢）
        1: "rgba(59,130,246,0.10)",    # 蓝色
        2: "rgba(168,85,247,0.10)",    # 紫色
        3: "rgba(236,72,153,0.08)",    # 粉色
    }
    
    for zi, zs in enumerate(zs_list):
        sdt = zs["start_dt"]
        edt = zs["end_dt"]
        if sdt in date_idx and edt in date_idx:
            si = date_idx[sdt]
            ei = date_idx[edt]
            ZG = zs["zg"]
            ZD = zs["zd"]
            fill_color = zs_colors.get(zi % 4, "rgba(245,158,11,0.08)")
            
            # 中枢矩形
            zs_mark_areas.append([{
                "xAxis": si,
                "yAxis": ZD,
                "itemStyle": {"color": fill_color, "borderColor": "rgba(245,158,11,0.3)", "borderWidth": 1, "borderType": "dashed"}
            }, {
                "xAxis": ei,
                "yAxis": ZG
            }])
            
            # ZG 虚线
            zs_mark_lines.append({
                "name": f"ZG{zi+1}",
                "yAxis": ZG,
                "lineStyle": {"color": "rgba(245,158,11,0.4)", "type": "dashed", "width": 1},
                "label": {"show": True, "formatter": f"ZG{zi+1}:{ZG:.0f}", "position": "end",
                          "fontSize": 9, "color": "rgba(245,158,11,0.7)"}
            })
            # ZD 虚线
            zs_mark_lines.append({
                "name": f"ZD{zi+1}",
                "yAxis": ZD,
                "lineStyle": {"color": "rgba(245,158,11,0.4)", "type": "dashed", "width": 1},
                "label": {"show": True, "formatter": f"ZD{zi+1}:{ZD:.0f}", "position": "start",
                          "fontSize": 9, "color": "rgba(245,158,11,0.7)"}
            })
    
    # ── 买卖点标记 ──
    trade_signals = generate_trade_signals(czsc_obj.bi_list, zs_list,
        detect_divergence(czsc_obj.bi_list, zs_list))
    
    buy_marks = []
    sell_marks = []
    for ts in trade_signals:
        dt = ts["dt"]
        if dt in date_idx:
            idx = date_idx[dt]
            is_buy = ts["side"] == "buy"
            mark = {
                "name": ts["type"],
                "coord": [idx, ts["price"]],
                "value": ts["type"],
                "symbol": "pin",
                "symbolSize": 20,
                "itemStyle": {"color": up_color if is_buy else down_color}
            }
            if is_buy:
                buy_marks.append(mark)
            else:
                sell_marks.append(mark)
    
    # ── 构建 Option ──
    series_kline = {
        "name": "K线",
        "type": "candlestick",
        "data": ohlc_data,
        "itemStyle": {"color": up_color, "color0": down_color,
                      "borderColor": up_color, "borderColor0": down_color},
        "markPoint": {
            "data": mark_points,
            "symbol": "arrow",
            "symbolSize": 10,
            "label": {"show": True, "fontSize": 8, "fontWeight": "normal"}
        },
        "markArea": {
            "silent": False,
            "data": zs_mark_areas
        },
        "markLine": {
            "silent": True,
            "symbol": "none",
            "data": zs_mark_lines
        }
    }
    
    series_list = [series_kline]
    
    # 买卖点独立系列
    if buy_marks:
        series_list.append({
            "name": "买点",
            "type": "scatter",
            "data": buy_marks,
            "symbol": "arrow",
            "symbolRotate": 180,
            "symbolSize": 12,
            "itemStyle": {"color": up_color},
            "label": {"show": True, "fontSize": 8, "fontWeight": "bold", "color": up_color}
        })
    
    if sell_marks:
        series_list.append({
            "name": "卖点",
            "type": "scatter",
            "data": sell_marks,
            "symbol": "pin",
            "symbolSize": 12,
            "itemStyle": {"color": down_color},
            "label": {"show": True, "fontSize": 8, "fontWeight": "bold", "color": down_color}
        })
    
    # 成交量系列
    series_list.append({
        "name": "成交量",
        "type": "bar",
        "xAxisIndex": 1,
        "yAxisIndex": 1,
        "data": vol_data
    })
    
    return {
        "backgroundColor": chart_bg,
        "animation": False,
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "cross", "crossStyle": {"color": axis_color}},
            "backgroundColor": "rgba(20,20,25,0.95)" if is_dark else "rgba(255,255,255,0.95)",
            "borderColor": "rgba(255,255,255,0.06)" if is_dark else "rgba(0,0,0,0.08)",
            "textStyle": {"fontSize": 11, "color": "#e4e4e7" if is_dark else "#1a1a2e"}
        },
        "legend": {
            "data": ["K线", "成交量"],
            "bottom": 20,
            "textStyle": {"color": axis_color, "fontSize": 10},
            "selectedMode": True
        },
        "grid": [
            {"left": "8%", "right": "4%", "top": 8, "height": "60%"},
            {"left": "8%", "right": "4%", "top": "75%", "height": "15%"}
        ],
        "xAxis": [
            {"type": "category", "data": dates, "axisLabel": {"color": axis_color, "fontSize": 9},
             "axisLine": {"lineStyle": {"color": grid_color}}},
            {"type": "category", "gridIndex": 1, "data": dates, "axisLabel": {"show": False},
             "axisLine": {"lineStyle": {"color": grid_color}}}
        ],
        "yAxis": [
            {"type": "value", "scale": True, "axisLabel": {"color": axis_color, "fontSize": 9},
             "splitLine": {"lineStyle": {"color": grid_color}}},
            {"type": "value", "gridIndex": 1, "axisLabel": {"color": axis_color, "fontSize": 9},
             "splitLine": {"show": False}}
        ],
        "dataZoom": [
            {"type": "inside", "start": 70, "end": 100},
            {"type": "slider", "start": 70, "end": 100, "height": 16, "bottom": 4}
        ],
        "series": series_list
    }


# ═══════════════════════════════════════════════
# 数据持久化
# ═══════════════════════════════════════════════

def save_to_db(code, freq, result):
    """将分析结果持久化到数据库"""
    conn = _connect()
    _ensure_tables(conn)
    
    # 清空旧数据
    conn.execute("DELETE FROM chanlun_bi WHERE stock_code=? AND freq=?", (code, freq))
    conn.execute("DELETE FROM chanlun_fx WHERE stock_code=? AND freq=?", (code, freq))
    conn.execute("DELETE FROM chanlun_zs WHERE stock_code=? AND freq=?", (code, freq))
    
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
    
    # 写入中枢
    for zs in result.get("zs_list", []):
        conn.execute("""
            INSERT INTO chanlun_zs (stock_code, freq, start_dt, end_dt, zg, zd, zz, bi_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, freq, zs["start_dt"], zs["end_dt"], zs["zg"], zs["zd"], zs["zz"], zs.get("bi_count", 0)))
    
    conn.commit()
    conn.close()
    return True


# ═══════════════════════════════════════════════
# 多周期联立分析
# ═══════════════════════════════════════════════

def multi_period_analyze(code, limit=400):
    """对同一代码进行日/周/月三周期联立分析
    
    Returns:
        dict: {
            periods: {D: {...}, W: {...}, M: {...}},
            resonance: { 共振信号分析 }
        }
    """
    results = {}
    for freq in ["D", "W", "M"]:
        try:
            r = analyze(code, freq, limit)
            results[freq] = r
        except Exception as e:
            results[freq] = {"error": str(e)}
    
    # ── 共振分析 ──
    resonance = _analyze_resonance(results)
    
    return {
        "code": code,
        "periods": results,
        "resonance": resonance
    }


def _analyze_resonance(results):
    """分析多周期共振信号
    
    共振规则：
    - 日/周/月笔方向一致 → 强趋势
    - 日/周中枢重叠 → 大级别中枢确认
    - 多周期同时出现背驰 → 高置信度反转
    """
    resonance = {
        "direction_consensus": None,   # 三周期笔方向是否一致
        "zs_overlap": False,           # 中枢是否跨周期重叠
        "divergence_resonance": [],    # 多周期背驰共振
        "trade_resonance": [],         # 多周期买卖点共振
        "strength": "弱"               # 共振强度
    }
    
    # 1. 笔方向一致检测
    dirs = {}
    for freq, r in results.items():
        if "error" in r or not r.get("bi_list"):
            continue
        last_bi = r["bi_list"][-1]
        dirs[freq] = str(last_bi["direction"])
    
    if len(dirs) == 3:
        vals = list(dirs.values())
        if vals[0] == vals[1] == vals[2]:
            resonance["direction_consensus"] = vals[0]
    
    # 2. 跨周期中枢重叠检测
    zs_ranges = {}
    for freq, r in results.items():
        if "error" in r or not r.get("zs_list"):
            continue
        # 取最后一个中枢的 ZG/ZD
        last_zs = r["zs_list"][-1]
        zs_ranges[freq] = (last_zs["zd"], last_zs["zg"])
    
    if len(zs_ranges) >= 2:
        freqs = list(zs_ranges.keys())
        for i in range(len(freqs)):
            for j in range(i+1, len(freqs)):
                zd_i, zg_i = zs_ranges[freqs[i]]
                zd_j, zg_j = zs_ranges[freqs[j]]
                # 检查重叠
                if max(zd_i, zd_j) < min(zg_i, zg_j):
                    resonance["zs_overlap"] = True
                    break
    
    # 3. 背驰共振
    div_dates = {}
    for freq, r in results.items():
        if "error" in r:
            continue
        for div in r.get("divergence_signals", []):
            dt_month = div["dt"][:7]  # YYYY-MM
            key = f"{div['type']}_{dt_month}"
            if key not in div_dates:
                div_dates[key] = []
            div_dates[key].append(freq)
    
    for key, freqs in div_dates.items():
        if len(freqs) >= 2:
            resonance["divergence_resonance"].append({
                "signal": key.split("_")[0],
                "month": key.split("_")[1],
                "freqs": freqs,
                "confidence": "高" if len(freqs) == 3 else "中"
            })
    
    # 4. 买卖点共振
    trade_dates = {}
    for freq, r in results.items():
        if "error" in r:
            continue
        for ts in r.get("trade_signals", []):
            dt_month = ts["dt"][:7]
            key = f"{ts['type']}_{dt_month}"
            if key not in trade_dates:
                trade_dates[key] = []
            trade_dates[key].append({"freq": freq, "confidence": ts["confidence"]})
    
    for key, items in trade_dates.items():
        if len(items) >= 2:
            resonance["trade_resonance"].append({
                "signal": key.split("_")[0],
                "month": key.split("_")[1],
                "details": items,
                "confidence": "高" if len(items) == 3 else "中"
            })
    
    # 5. 共振强度
    score = 0
    if resonance["direction_consensus"]:
        score += 2
    if resonance["zs_overlap"]:
        score += 2
    if resonance["divergence_resonance"]:
        score += len(resonance["divergence_resonance"]) * 2
    if resonance["trade_resonance"]:
        score += len(resonance["trade_resonance"]) * 3
    
    if score >= 6:
        resonance["strength"] = "强"
    elif score >= 3:
        resonance["strength"] = "中"
    else:
        resonance["strength"] = "弱"
    resonance["score"] = score
    
    return resonance


# ═══════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    r = analyze("000985", "D", 300)
    print(f"笔: {r['bi_count']}, 分型: {r['fx_count']}, 中枢: {r['zs_count']}, 背驰: {r['divergence_count']}, 买卖点: {r['trade_signal_count']}")
    if r["bi_list"]:
        last = r["bi_list"][-1]
        print(f"最新笔: {last['direction']} {last['sdt'][:10]}→{last['edt'][:10]} L:{last['low']:.1f} H:{last['high']:.1f} P:{last['power']:.1f}")
    if r["zs_list"]:
        print(f"\n中枢列表:")
        for zs in r["zs_list"]:
            print(f"  #{zs['idx']} {zs['start_dt']}~{zs['end_dt']} ZG:{zs['zg']:.1f} ZD:{zs['zd']:.1f} 宽:{zs['width']:.1f}({zs['width_pct']}%)")
    if r["divergence_signals"]:
        print(f"\n背驰信号:")
        for d in r["divergence_signals"]:
            print(f"  {d['type']}({d['category']}) {d['dt']} 力度比:{d['power_ratio']} {d['severity']}")
    if r["trade_signals"]:
        print(f"\n买卖信号:")
        for ts in r["trade_signals"]:
            side_sym = "🟢" if ts["side"] == "buy" else "🔴"
            print(f"  {side_sym} {ts['type']} @{ts['dt']} 价格:{ts['price']} 置信度:{ts['confidence']}")
