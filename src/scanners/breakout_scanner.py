"""
标准突破买点识别引擎

基于通达信基部+突破逻辑：
  1. 120日内存在峰→谷结构(涨幅>30%, 峰值在前)
  2. 回撤12%~33%
  3. 谷底右侧反弹≥峰谷距离60%
  4. 反弹高点距今5~20天
  5. RS_20/60/250 任一≥87
  6. 昨日满足基部条件, 今日收盘突破反弹高点
  7. 峰值距今>30天

用法：python src/scanners/breakout_scanner.py --stock 600519 --date 2026-05-08
"""

import sys, os, argparse, sqlite3
from datetime import datetime, date as dt_date

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")


def load_params():
    import yaml
    cfg_path = os.path.join(PROJECT_DIR, "config", "market", "breakout.yaml")
    defaults = {
        'lookback': 120, 'min_range_pct': 30, 'drawdown_min': 12, 'drawdown_max': 33,
        'rebound_ratio': 60, 'hold_min': 5, 'hold_max': 20, 'peak_age_min': 30,
        'rs_threshold': 87, 'vol_ratio': 1.4, 'require_green': True, 'close_position_min': 60,
    }
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        defaults.update(cfg.get('breakout', {}))
    return defaults


def check_rs(conn, stock_code, target_date, threshold, mode='stock'):
    """检查RS是否达标"""
    if mode == 'index':
        row = conn.execute("""SELECT rs_20, rs_60, rs_250 FROM index_rs_daily
            WHERE stock_code = ? AND date <= ? ORDER BY date DESC LIMIT 1""",
            (stock_code, target_date)).fetchone()
        if not row:
            return False, {}
        rs = {'rs_20': row['rs_20'] or 0, 'rs_60': row['rs_60'] or 0, 'rs_250': row['rs_250'] or 0}
    else:
        row = conn.execute("""SELECT rps_20, rps_250 FROM stock_rs_daily
            WHERE stock_code = ? AND date <= ? ORDER BY date DESC LIMIT 1""",
            (stock_code, target_date)).fetchone()
        if not row:
            return False, {}
        rs = {'rs_20': row['rps_20'] or 0, 'rs_60': 0, 'rs_250': row['rps_250'] or 0}
    return (rs['rs_20'] >= threshold or rs['rs_60'] >= threshold or rs['rs_250'] >= threshold), rs


def detect(klines, params=None, rs_info=None):
    """
    klines: [{'date','open','high','low','close','volume'}, ...] 按日期升序
    rs_info: {'rs_20': int, 'rs_60': int, 'rs_250': int} 或 None
    """
    if params is None:
        params = load_params()

    LB = params['lookback']
    MIN_R = params['min_range_pct'] / 100.0
    DD_MIN = params['drawdown_min'] / 100.0
    DD_MAX = params['drawdown_max'] / 100.0
    RB = params['rebound_ratio'] / 100.0
    HOLD_MIN = params['hold_min']
    HOLD_MAX = params['hold_max']
    PEAK_AGE = params['peak_age_min']
    RS_THR = params['rs_threshold']
    VOL_R = params['vol_ratio']
    GREEN = params.get('require_green', True)
    CLOSE_POS = params.get('close_position_min', 60) / 100.0

    n = len(klines)
    if n < LB:
        return []

    # 预计算均量
    ma50_vols = []
    for i in range(n):
        if i >= 49:
            vs = [klines[j]['volume'] for j in range(i - 49, i + 1) if klines[j].get('volume') is not None]
            ma50_vols.append(sum(vs) / len(vs) if vs else 0)
        else:
            ma50_vols.append(0)

    signals = []
    for i in range(LB + 1, n):
        today = klines[i]

        # ── B6 + XG: 昨日满足基部条件 + 今日收盘突破昨日反弹高点 ──
        yesterday_base = _check_base_conditions_with_rh(klines, i - 1, params)
        if not yesterday_base:
            continue
        rh_val_yd = yesterday_base
        if today['close'] <= rh_val_yd:
            continue

        # ── 成交量 ──
        if i >= 49 and ma50_vols[i] > 0:
            vol_ratio = today['volume'] / ma50_vols[i]
            if vol_ratio < VOL_R:
                continue
        else:
            vol_ratio = 0

        # ── 阳线 ──
        if GREEN and today['close'] <= today['open']:
            continue

        # ── 收盘位置 ──
        if today['high'] != today['low']:
            pos = (today['close'] - today['low']) / (today['high'] - today['low'])
            if pos < CLOSE_POS:
                continue

        # ── 从昨日窗口提取基部元数据 ──
        yd_window = klines[i - 1 - LB:i]
        yd_highs = [(k['high'], j) for j, k in enumerate(yd_window) if k['high'] is not None]
        yd_lows = [(k['low'], j) for j, k in enumerate(yd_window) if k['low'] is not None]
        yd_hh_val, yd_hh_idx = max(yd_highs, key=lambda x: x[0])
        yd_ll_val, yd_ll_idx = min(yd_lows, key=lambda x: x[0])
        yd_rh_list = [(k['high'], j) for j, k in enumerate(yd_window[yd_ll_idx:], start=yd_ll_idx) if k['high'] is not None]
        _, yd_rh_idx = max(yd_rh_list, key=lambda x: x[0])

        signals.append({
            'date': today['date'],
            'close': today['close'],
            'volume': today['volume'],
            'peak_date': yd_window[yd_hh_idx]['date'],
            'peak_price': yd_hh_val,
            'trough_date': yd_window[yd_ll_idx]['date'],
            'trough_price': yd_ll_val,
            'rebound_date': yd_window[yd_rh_idx]['date'],
            'rebound_price': rh_val_yd,
            'drawdown': round((yd_hh_val - yd_ll_val) / yd_hh_val * 100, 1),
            'rebound_pct': round((rh_val_yd - yd_ll_val) / (yd_hh_val - yd_ll_val) * 100, 1),
            'vol_ratio': round(vol_ratio, 2),
            'rs_20': rs_info['rs_20'] if rs_info else 0,
            'rs_60': rs_info['rs_60'] if rs_info else 0,
            'rs_250': rs_info['rs_250'] if rs_info else 0,
        })

    return signals


def _check_base_conditions_with_rh(klines, i, params):
    """检查单日是否满足 B1~B4，返回反弹高点值或0"""
    LB = params['lookback']
    MIN_R = params['min_range_pct'] / 100.0
    DD_MIN = params['drawdown_min'] / 100.0
    DD_MAX = params['drawdown_max'] / 100.0
    RB = params['rebound_ratio'] / 100.0
    HOLD_MIN = params['hold_min']
    HOLD_MAX = params['hold_max']
    PEAK_AGE = params['peak_age_min']

    if i < LB:
        return 0
    window = klines[i - LB:i + 1]
    wl = len(window)

    highs = [(k['high'], j) for j, k in enumerate(window) if k['high'] is not None]
    lows = [(k['low'], j) for j, k in enumerate(window) if k['low'] is not None]
    if not highs or not lows:
        return 0

    hh_val, hh_idx = max(highs, key=lambda x: x[0])
    ll_val, ll_idx = min(lows, key=lambda x: x[0])
    if hh_idx >= ll_idx:
        return 0
    if (hh_val - ll_val) / ll_val < MIN_R:
        return 0

    dd = (hh_val - ll_val) / hh_val
    if dd < DD_MIN or dd > DD_MAX:
        return 0

    rh_list = [(k['high'], j) for j, k in enumerate(window[ll_idx:], start=ll_idx) if k['high'] is not None]
    if not rh_list:
        return 0
    rh_val, rh_idx = max(rh_list, key=lambda x: x[0])
    if (rh_val - ll_val) / (hh_val - ll_val) < RB:
        return 0

    days_from_rh = wl - 1 - rh_idx
    if days_from_rh < HOLD_MIN or days_from_rh > HOLD_MAX:
        return 0

    # peak age
    if wl - 1 - hh_idx < PEAK_AGE:
        return 0

    return rh_val


def detect_for_stock(stock_code, target_date, params=None, mode='stock'):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    table = 'index_daily_kline' if mode == 'index' else 'daily_kline'
    kf = "AND kline_type='normal'" if mode == 'index' else ''
    rows = conn.execute(f"SELECT date, open, high, low, close, volume FROM {table} WHERE stock_code=? {kf} AND date<=? ORDER BY date", (stock_code, target_date)).fetchall()

    if len(rows) < 120:
        conn.close(); return []

    klines = [dict(r) for r in rows]
    rs_ok, rs_info = check_rs(conn, stock_code, target_date, params.get('rs_threshold', 87) if params else 87, mode)
    if not rs_ok:
        conn.close(); return []

    signals = detect(klines, params, rs_info)
    conn.close()
    return signals


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", type=str, default="600519")
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--mode", type=str, default="stock")
    args = parser.parse_args()
    target = args.date or dt_date.today().strftime("%Y-%m-%d")

    params = load_params()
    signals = detect_for_stock(args.stock, target, params, args.mode)
    print(f"突破信号数: {len(signals)}")
    for s in signals[-8:]:
        print(f"  {s['date']} 峰{s['peak_date']}({s['peak_price']:.0f}) 谷{s['trough_date']}({s['trough_price']:.0f}) 反弹{s['rebound_price']:.0f} 回撤{s['drawdown']}% 量比{s['vol_ratio']}")
