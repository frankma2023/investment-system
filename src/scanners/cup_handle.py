"""
杯柄形态（Cup with Handle）识别引擎 v1.0

O'Neil 经典中轴买点。周线识别杯体 + 日线精确验证柄部。

核心规则：
  1. 杯体: 周线级别 U 形回调 12%~33%，持续 7~65 周
  2. 杯底: 成交量萎缩，U 形对称
  3. 杯柄: 回升至左沿附近后小幅回调 8%~12%，1~2 周
  4. 买点: 突破柄部高点 + 放量确认

参考: William J. O'Neil《笑傲股市》第4版
"""

import sys, os, argparse, sqlite3, yaml, math
from datetime import datetime, date as dt_date, timedelta
from typing import Optional, Dict, List, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")

ENGINE_META = {
    "name": "cup_handle",
    "display_name": "杯柄形态",
    "category": "pattern",
    "version": "1.0",
    "description": "识别欧奈尔经典杯柄形态（Cup with Handle）突破买点，周线杯体+日线柄部"
}


def load_params():
    cfg_path = os.path.join(PROJECT_DIR, "config", "market", "cup_handle.yaml")
    defaults = {
        'min_prior_advance': 0.30, 'prior_advance_lookback': 120,
        'cup_depth_min': 0.12, 'cup_depth_max': 0.33,
        'cup_duration_min_weeks': 7, 'cup_duration_max_weeks': 65,
        'cup_u_shape_ratio': 0.30, 'cup_left_lip_window': 13,
        'handle_enabled': True, 'handle_required': True,
        'handle_position_min': 0.50,
        'handle_depth_min': 0.08, 'handle_depth_max': 0.12,
        'handle_duration_min_days': 5, 'handle_duration_max_days': 30,
        'handle_slope_max': 0.001,
        'cup_bottom_vol_ratio': 0.60, 'handle_vol_ratio': 0.50,
        'breakout_vol_ratio': 1.5, 'breakout_buffer': 0.01,
        'close_position_min': 0.50, 'require_green': True,
    }
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        defaults.update(cfg.get('cup_handle', {}))
    return defaults


# ─── 工具 ─────────────────────────────────────────────

def _aggregate_weekly(daily: List[Dict]) -> List[Dict]:
    """日K线聚合为周K线"""
    if not daily:
        return []
    result = []
    current_week = None
    wk = None
    for row in daily:
        d = row['date']
        if isinstance(d, str):
            dt = datetime.strptime(d, '%Y-%m-%d').date()
        else:
            dt = d
        iso = dt.isocalendar()
        key = (iso[0], iso[1])
        if key != current_week:
            if wk:
                result.append(wk)
            current_week = key
            wk = {'date': dt.strftime('%Y-%m-%d'), 'open': row['open'], 'high': row['high'],
                  'low': row['low'], 'close': row['close'], 'volume': row['volume']}
        else:
            wk['high'] = max(wk['high'], row['high'])
            wk['low'] = min(wk['low'], row['low'])
            wk['close'] = row['close']
            wk['volume'] += row['volume']
            wk['date'] = dt.strftime('%Y-%m-%d')
    if wk:
        result.append(wk)
    return result


def _sma(values: List[float], n: int) -> float:
    if len(values) < n:
        return sum(values) / max(len(values), 1)
    return sum(values[-n:]) / n


def _linear_slope(y: List[float]) -> float:
    n = len(y)
    if n < 2:
        return 0
    xs = list(range(n))
    xm = (n - 1) / 2; ym = sum(y) / n
    num = sum((xs[i] - xm) * (y[i] - ym) for i in range(n))
    den = sum((xs[i] - xm) ** 2 for i in range(n))
    return num / den if den else 0


def _get_segment(klines: List[Dict], start_date: str, end_date: str) -> List[Dict]:
    return [k for k in klines if start_date <= k['date'] <= end_date]


def _count_days(klines: List[Dict], start: str, end: str) -> int:
    return len(_get_segment(klines, start, end))


# ─── 杯柄检测 ────────────────────────────────────────

def detect(
    daily_klines: List[Dict],
    params: Optional[Dict] = None,
    market_cap: Optional[float] = None,
) -> List[Dict]:
    """
    检测杯柄形态突破信号。
    
    Args:
        daily_klines: 日K线，升序
        params: 参数字典
    Returns:
        信号列表
    """
    if params is None:
        params = load_params()
    
    if len(daily_klines) < 500:
        return []

    weekly = _aggregate_weekly(daily_klines)
    signals = []

    # 遍历检测日
    for t_idx in range(len(daily_klines) - 1, len(daily_klines) - 120, -1):
        if t_idx < 150:
            continue
        t_row = daily_klines[t_idx]
        t_close = t_row['close']; t_date = t_row['date']
        t_open = t_row['open']; t_vol = t_row['volume']

        # 趋势确认
        if t_idx < 50:
            continue
        sma50 = _sma([k['close'] for k in daily_klines[t_idx-49:t_idx+1]], 50)
        sma50_vol = _sma([k['volume'] for k in daily_klines[t_idx-49:t_idx+1]], 50)
        if t_close <= sma50:
            continue

        # 收盘位置 + 阳线
        if params.get('require_green', True) and t_close <= t_open:
            continue
        if t_row['high'] > t_row['low']:
            pos = (t_close - t_row['low']) / (t_row['high'] - t_row['low'])
            if pos < params['close_position_min']:
                continue

        # ── 杯体检测（周线） ──
        cup = _find_cup(weekly, daily_klines, t_date, params)
        if cup is None:
            continue
        
        left_lip, left_lip_date, cup_bottom, cup_bottom_date, cup_weeks = cup

        # ── 杯柄检测（日线） ──
        handle = None
        if params.get('handle_enabled', True):
            handle = _find_handle(
                daily_klines, weekly, left_lip, left_lip_date,
                cup_bottom, cup_bottom_date, t_date, t_close, params
            )
        
        has_handle = handle is not None
        if params.get('handle_required', True) and not has_handle:
            continue

        # ── 突破确认 ──
        buy_point = left_lip + params['breakout_buffer']
        if has_handle:
            buy_point = handle['handle_high'] + params['breakout_buffer']
        
        if t_close < buy_point:
            continue

        # 成交量确认
        if t_vol < sma50_vol * params['breakout_vol_ratio']:
            continue

        # ── 输出信号 ──
        signal = {
            'signal_date': t_date,
            'pattern_type': 'cup_with_handle' if has_handle else 'cup',
            'left_lip_date': left_lip_date,
            'left_lip_price': round(float(left_lip), 2),
            'cup_bottom_date': cup_bottom_date,
            'cup_bottom_price': round(float(cup_bottom), 2),
            'cup_drawdown_pct': round((left_lip - cup_bottom) / left_lip * 100, 1),
            'cup_duration_weeks': cup_weeks,
            'buy_point': round(float(buy_point), 2),
            'breakout_vol_ratio': round(t_vol / sma50_vol, 2) if sma50_vol > 0 else 0,
            'breakout_chg_pct': round((t_close - t_open) / t_open * 100, 2) if t_open > 0 else 0,
            'handle_flag': has_handle,
            'handle_high': round(float(handle['handle_high']), 2) if has_handle else None,
            'handle_low': round(float(handle['handle_low']), 2) if has_handle else None,
            'handle_drawdown_pct': round(handle['handle_drawdown'] * 100, 1) if has_handle else None,
            'close_vs_sma50': round(t_close / sma50, 3),
        }
        signals.append(signal)

    return signals


# ─── 杯体检测 ────────────────────────────────────────

def _find_cup(
    weekly: List[Dict],
    daily: List[Dict],
    t_date: str,
    params: Dict
) -> Optional[Tuple[float, str, float, str, int]]:
    """
    周线杯体检测。
    返回: (left_lip_price, left_lip_date, bottom_price, bottom_date, cup_weeks) 或 None
    """
    cup_min_w = params['cup_duration_min_weeks']
    cup_max_w = params['cup_duration_max_weeks']
    depth_min = params['cup_depth_min']
    depth_max = params['cup_depth_max']
    u_ratio = params['cup_u_shape_ratio']
    lip_window = params['cup_left_lip_window']

    # 找到检测日在周线中的位置
    t_week_idx = len(weekly) - 1
    for wi, w in enumerate(weekly):
        if w['date'] >= t_date:
            t_week_idx = wi
            break

    # 回溯找左沿（局部高点）
    left_lip = 0; left_lip_idx = None
    search_end = max(0, t_week_idx - cup_min_w)
    for i in range(search_end, max(0, t_week_idx - cup_max_w - 1), -1):
        if i >= len(weekly):
            continue
        # 局部高点: 前后 lip_window 周内最高
        lo = max(0, i - lip_window)
        hi = min(len(weekly) - 1, i + lip_window)
        is_local = True
        for j in range(lo, hi + 1):
            if weekly[j]['close'] > weekly[i]['close']:
                is_local = False
                break
        if is_local and weekly[i]['close'] > left_lip:
            left_lip = weekly[i]['close']
            left_lip_idx = i

    if left_lip_idx is None or left_lip <= 0:
        return None

    # 在左沿之后找杯底
    cup_bottom = float('inf'); cup_bottom_idx = None
    for i in range(left_lip_idx + 1, min(t_week_idx, len(weekly))):
        if weekly[i]['close'] < cup_bottom:
            cup_bottom = weekly[i]['close']
            cup_bottom_idx = i

    if cup_bottom_idx is None or cup_bottom <= 0:
        return None

    # 回调深度验证
    drawdown = (left_lip - cup_bottom) / left_lip
    if drawdown < depth_min or drawdown > depth_max:
        return None

    # 杯体时长验证
    cup_weeks = cup_bottom_idx - left_lip_idx
    if cup_weeks < cup_min_w or cup_weeks > cup_max_w:
        return None

    # U 形对称性: 底前时间 / 底后时间 ≥ u_ratio
    # 底后 = 杯底到回升至左沿附近
    recovery_weeks = t_week_idx - cup_bottom_idx
    if cup_weeks > 0 and recovery_weeks > 0:
        # 杯底前半 / 杯底后半 应接近 (U 形而非 V 形)
        front_half = cup_bottom_idx - left_lip_idx
        if front_half > 0 and recovery_weeks > 0:
            symmetry = min(front_half, recovery_weeks) / max(front_half, recovery_weeks)
            if symmetry < u_ratio:
                return None

    # 杯底成交量萎缩
    if len(daily) > 50:
        cup_bottom_date = weekly[cup_bottom_idx]['date']
        vol_start = max(0, daily.index([k for k in daily if k['date'] >= cup_bottom_date][0]) if any(k['date'] >= cup_bottom_date for k in daily) else 0)
        b_vols = [daily[i]['volume'] for i in range(max(0, vol_start - 10), min(len(daily), vol_start + 15))]
        if b_vols:
            avg_bottom_vol = sum(b_vols) / len(b_vols)
            sma50_v = _sma([k['volume'] for k in daily[max(0, vol_start-49):vol_start+1]], 50)
            if sma50_v > 0 and avg_bottom_vol / sma50_v > params['cup_bottom_vol_ratio']:
                return None

    left_lip_date = weekly[left_lip_idx]['date']
    cup_bottom_date = weekly[cup_bottom_idx]['date']

    return (left_lip, left_lip_date, cup_bottom, cup_bottom_date, cup_weeks)


# ─── 杯柄检测 ────────────────────────────────────────

def _find_handle(
    daily: List[Dict],
    weekly: List[Dict],
    left_lip: float,
    left_lip_date: str,
    cup_bottom: float,
    cup_bottom_date: str,
    t_date: str,
    t_close: float,
    params: Dict
) -> Optional[Dict]:
    """
    日线杯柄检测。
    柄部: 回升至左沿附近后的小幅回调(8%-12%)，成交量萎缩。
    """
    h_pos_min = params['handle_position_min']
    h_depth_min = params['handle_depth_min']
    h_depth_max = params['handle_depth_max']
    h_days_min = params['handle_duration_min_days']
    h_days_max = params['handle_duration_max_days']
    h_slope_max = params['handle_slope_max']
    h_vol_ratio = params['handle_vol_ratio']

    # 杯体高度
    cup_height = left_lip - cup_bottom
    if cup_height <= 0:
        return None

    # 从杯底到检测日的回升段
    ascent = _get_segment(daily, cup_bottom_date, t_date)
    if len(ascent) < 20:
        return None

    # 找柄部高点: 回升段中最后一次 close ≥ left_lip * 0.85 的局部高点
    handle_high = 0; handle_high_idx = None
    for i in range(len(ascent) - h_days_min - 1, 5, -1):
        if ascent[i]['close'] >= left_lip * 0.85:
            # 检查是否局部高点（前后各3天）
            lo = max(0, i - 3); hi = min(len(ascent) - 1, i + 3)
            is_local = True
            for j in range(lo, hi + 1):
                if ascent[j]['close'] > ascent[i]['close']:
                    is_local = False; break
            if is_local and ascent[i]['close'] > handle_high:
                handle_high = ascent[i]['close']
                handle_high_idx = i

    if handle_high_idx is None:
        return None

    # 柄部 = 从柄部高点到检测日
    handle_seg = ascent[handle_high_idx:]
    if len(handle_seg) < h_days_min or len(handle_seg) > h_days_max:
        return None

    # 柄部低点
    handle_low = min(k['close'] for k in handle_seg)

    # 柄部回撤
    h_drawdown = (handle_high - handle_low) / handle_high if handle_high > 0 else 0
    if h_drawdown < h_depth_min or h_drawdown > h_depth_max:
        return None

    # 柄部位置: 必须在杯体上半部
    if handle_low < cup_bottom + cup_height * h_pos_min:
        return None

    # 柄部斜率
    h_closes = [k['close'] for k in handle_seg]
    slope = _linear_slope(h_closes)
    if slope > h_slope_max:
        return None

    # 柄部成交量萎缩
    h_vols = [k['volume'] for k in handle_seg]
    if h_vols:
        avg_h_vol = sum(h_vols) / len(h_vols)
        # 杯体整体均量
        cup_daily = _get_segment(daily, left_lip_date, t_date)
        avg_cup_vol = sum(k['volume'] for k in cup_daily) / max(len(cup_daily), 1)
        if avg_cup_vol > 0 and avg_h_vol / avg_cup_vol > h_vol_ratio:
            return None

    return {
        'handle_high': handle_high,
        'handle_low': handle_low,
        'handle_drawdown': h_drawdown,
        'handle_days': len(handle_seg),
    }


# ─── CLI ─────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='杯柄形态识别')
    parser.add_argument('--stock', type=str, default='600519', help='股票代码')
    parser.add_argument('--date', type=str, default=datetime.now().strftime('%Y-%m-%d'))
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    klines = conn.execute("""
        SELECT date, open, high, low, close, volume FROM daily_kline
        WHERE stock_code=? AND date<=? AND date>=date(?,'-600 days')
        ORDER BY date
    """, (args.stock, args.date, args.date)).fetchall()

    if len(klines) < 500:
        print(f"K线不足: {len(klines)}")
        sys.exit(1)

    daily = [dict(r) for r in klines]
    params = load_params()
    signals = detect(daily, params)

    print(f"🔍 {args.stock} @ {args.date}")
    print(f"   杯柄形态突破信号: {len(signals)}")
    for s in signals:
        print(f"   📅 {s['signal_date']} {s['pattern_type']}")
        print(f"      左沿={s['left_lip_price']} 杯底={s['cup_bottom_price']} 回调={s['cup_drawdown_pct']}%")
        print(f"      买点={s['buy_point']} 量比={s['breakout_vol_ratio']}")
        if s['handle_flag']:
            print(f"      柄高={s['handle_high']} 柄低={s['handle_low']} 回撤={s['handle_drawdown_pct']}%")

    conn.close()
