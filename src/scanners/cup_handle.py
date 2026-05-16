"""
杯柄形态（Cup with Handle）识别引擎 v1.0

O'Neil 经典中轴买点。日线全流程识别。
对齐 product/杯柄形态突破检测引擎_产品需求书.md v1.0

检测流程:
  3.1 前置条件 → 3.2 杯身识别(3步) → 3.3 柄部检测 → 3.4 突破验证 → 3.5 假突破排除 → 3.6 RS验证
"""

import sys, os, argparse, sqlite3, yaml, math
from datetime import datetime, date as dt_date
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
    "description": "识别欧奈尔经典杯柄形态突破买点，对齐产品需求书v1.0"
}


def load_params():
    cfg_path = os.path.join(PROJECT_DIR, "config", "market", "cup_handle.yaml")
    defaults = {
        'lookback': 120, 'prior_high_mode': 'simple', 'min_prior_advance': 0.30,
        'cup_min_age': 35, 'cup_max_age': 325,
        'min_descent_days': 10, 'min_ascent_days': 10, 'min_market_cap': 0,
        'cup_drawdown_min': 0.12, 'cup_drawdown_max': 0.33,
        'cup_bottom_check': True, 'cup_bottom_flatness': 0.08,
        'cup_recovery': 0.90,
        'ascent_descent_check': True, 'ascent_descent_ratio': 0.50,
        'vol_bottom_max': 0.60, 'vol_contraction': 0.65,
        'handle_required': True, 'handle_min_days': 5, 'handle_max_days': 30,
        'handle_max_drawdown': 0.12, 'handle_position_ratio': 0.50,
        'handle_vol_ratio': 0.50,
        'breakout_buffer': 0.01, 'breakout_vol_ratio': 1.4,
        'require_green': True, 'close_position_min': 0.50,
        'fake_breakout_lookback': 5,
        'rs_required': False, 'rs_threshold': 80,
    }
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        defaults.update(cfg.get('cup_handle', {}))
    return defaults


# ─── 工具函数 ──────────────────────────────────────────

def _sma(arr: List[float], n: int) -> float:
    """简单移动平均，末尾n个"""
    if len(arr) < n:
        return sum(arr) / max(len(arr), 1)
    return sum(arr[-n:]) / n


def _sma_before(arr: List[float], n: int, idx: int) -> float:
    """idx之前n个的移动平均（不含idx）"""
    start = max(0, idx - n)
    vals = arr[start:idx]
    return sum(vals) / max(len(vals), 1)


def _linear_slope(y: List[float]) -> float:
    """线性回归斜率"""
    n = len(y)
    if n < 2:
        return 0
    xs = list(range(n))
    xm = (n - 1) / 2; ym = sum(y) / n
    num = sum((xs[i] - xm) * (y[i] - ym) for i in range(n))
    den = sum((xs[i] - xm) ** 2 for i in range(n))
    return num / den if den else 0


def _count_between(dates: List[str], start: str, end: str) -> int:
    """区间内交易日数"""
    return sum(1 for d in dates if start <= d <= end)


def _slice(daily: List[Dict], start_date: str, end_date: str) -> List[Dict]:
    return [k for k in daily if start_date <= k['date'] <= end_date]


def _weekly_returns(closes: List[float]) -> List[float]:
    """5日窗口近似周收益率"""
    if len(closes) < 6:
        return []
    return [(closes[i] - closes[i-5]) / closes[i-5] for i in range(5, len(closes), 5)
            if closes[i-5] > 0]


# ─── 3.1 前置条件 ─────────────────────────────────────

def _check_prior_advance(daily: List[Dict], prior_high_date: str,
                         prior_high_price: float, params: Dict) -> float:
    """条件0.1: 前置上涨验证，返回涨幅%"""
    lookback = params['prior_advance_lookback'] if 'prior_advance_lookback' in params else params['lookback']
    min_adv = params['min_prior_advance']
    
    ph_idx = next((i for i, k in enumerate(daily) if k['date'] >= prior_high_date), None)
    if ph_idx is None or ph_idx < 10:
        return 0
    
    low = float('inf')
    for i in range(max(0, ph_idx - lookback), ph_idx):
        if daily[i]['close'] < low:
            low = daily[i]['close']
    
    if low <= 0:
        return 0
    return (prior_high_price - low) / low


# ─── 3.2.1 定位前高和杯底 ──────────────────────────────

def _find_prior_high_and_bottom(
    daily: List[Dict], t_idx: int, params: Dict
) -> Optional[Dict]:
    """步骤1: 定位前高和杯底"""
    lookback = params['lookback']
    cup_min_age = params['cup_min_age']
    cup_max_age = params['cup_max_age']
    min_descent = params['min_descent_days']
    min_ascent = params['min_ascent_days']
    dd_min = params['cup_drawdown_min']
    dd_max = params['cup_drawdown_max']
    
    t_date = daily[t_idx]['date']
    
    # 1.1 前高: lookback内最高收盘价(默认simple模式)
    search_start = max(0, t_idx - cup_max_age)
    search_end = t_idx - cup_min_age
    
    if search_end <= search_start:
        return None
    
    prior_high = 0; prior_idx = None
    for i in range(search_start, search_end + 1):
        if daily[i]['close'] > prior_high:
            prior_high = daily[i]['close']
            prior_idx = i
    
    if prior_idx is None or prior_high <= 0:
        return None
    
    # 1.2 杯底: 前高之后的最低收盘价
    bottom = float('inf'); bottom_idx = None
    for i in range(prior_idx + 1, t_idx):
        if daily[i]['close'] < bottom:
            bottom = daily[i]['close']
            bottom_idx = i
    
    if bottom_idx is None or bottom <= 0:
        return None
    
    # 校验距离
    if t_idx - prior_idx < cup_min_age:
        return None
    if bottom_idx - prior_idx < min_descent:
        return None
    if t_idx - bottom_idx < min_ascent:
        return None
    
    # 1.3 回调深度
    drawdown = (prior_high - bottom) / prior_high
    if drawdown < dd_min or drawdown > dd_max:
        return None
    
    # 1.4 杯底不是尖底(可关)
    if params.get('cup_bottom_check', True):
        flatness = params['cup_bottom_flatness']
        start_5 = max(0, bottom_idx - 5)
        end_5 = min(len(daily) - 1, bottom_idx + 5)
        closes_5 = [daily[i]['close'] for i in range(start_5, end_5 + 1)]
        low_5 = min(closes_5); high_5 = max(closes_5)
        amp = (high_5 - low_5) / low_5 if low_5 > 0 else 1
        if amp > flatness:
            return None
    
    return {
        'prior_high': prior_high, 'prior_idx': prior_idx,
        'prior_high_date': daily[prior_idx]['date'],
        'bottom': bottom, 'bottom_idx': bottom_idx,
        'bottom_date': daily[bottom_idx]['date'],
        'drawdown': drawdown,
        'descent_days': bottom_idx - prior_idx,
        'cup_weeks': (t_idx - prior_idx) // 5,
    }


# ─── 3.2.2 验证杯身回升 ──────────────────────────────

def _check_recovery(
    daily: List[Dict], cup: Dict, t_idx: int, params: Dict
) -> bool:
    """步骤2: 验证杯身回升"""
    prior_high = cup['prior_high']; bottom = cup['bottom']
    bottom_idx = cup['bottom_idx']; prior_idx = cup['prior_idx']
    recovery_pct = params['cup_recovery']
    
    # 2.1 回升到前高N%以上
    max_after_bottom = max(k['close'] for k in daily[bottom_idx:t_idx + 1])
    if max_after_bottom < prior_high * recovery_pct:
        return False
    
    # 2.2 回升路径: 斜率>0 + 无单周暴涨>20%
    ascent = daily[bottom_idx:t_idx + 1]
    asc_closes = [k['close'] for k in ascent]
    slope = _linear_slope(asc_closes)
    if slope <= 0:
        return False
    
    # 周收益率检查
    weekly_ret = _weekly_returns(asc_closes)
    for r in weekly_ret:
        if r > 0.20:
            return False
    
    # 2.3 左右侧速度对比(可关)
    if params.get('ascent_descent_check', True):
        descent_weeks = cup['descent_days'] // 5
        ascent_weeks = (t_idx - bottom_idx) // 5
        ratio = params['ascent_descent_ratio']
        if descent_weeks > 0 and ascent_weeks < descent_weeks * ratio:
            return False
    
    return True


# ─── 3.2.3 验证成交量 ────────────────────────────────

def _check_volume(
    daily: List[Dict], cup: Dict, t_idx: int, params: Dict
) -> Optional[Tuple[float, float]]:
    """步骤3: 成交量验证。返回(杯底量/50均, 下行后半/前半)或None"""
    bottom_idx = cup['bottom_idx']; prior_idx = cup['prior_idx']
    vol_bottom_max = params['vol_bottom_max']
    vol_cont = params['vol_contraction']
    
    # 50日均量(t-50到t-1)
    sma50_vol = _sma_before([k['volume'] for k in daily], 50, t_idx)
    if sma50_vol <= 0:
        return None
    
    # 3.1 杯底量萎缩
    start_b = max(0, bottom_idx - 10)
    end_b = min(len(daily) - 1, bottom_idx + 15)
    b_vols = [daily[i]['volume'] for i in range(start_b, end_b + 1)]
    if b_vols:
        avg_b_vol = sum(b_vols) / len(b_vols)
        if avg_b_vol / sma50_vol > vol_bottom_max:
            return None
    vol_b_ratio = avg_b_vol / sma50_vol if b_vols and sma50_vol > 0 else 1
    
    # 3.2 下行段越跌量越小
    descent = daily[prior_idx:bottom_idx + 1]
    if len(descent) >= 4:
        mid = len(descent) // 2
        first_vol = sum(k['volume'] for k in descent[:mid]) / mid
        second_vol = sum(k['volume'] for k in descent[mid:]) / (len(descent) - mid)
        if first_vol > 0 and second_vol / first_vol > vol_cont:
            return None
        vol_cont_val = second_vol / first_vol if first_vol > 0 else 1
    else:
        vol_cont_val = 1
    
    # 3.3 回升段量 ≥ 下行后半量
    ascent = daily[bottom_idx:t_idx + 1]
    descent_second = daily[prior_idx + len(descent)//2:bottom_idx + 1]
    asc_avg_vol = sum(k['volume'] for k in ascent) / max(len(ascent), 1)
    desc2_avg_vol = sum(k['volume'] for k in descent_second) / max(len(descent_second), 1)
    if desc2_avg_vol > 0 and asc_avg_vol < desc2_avg_vol:
        return None
    
    return (vol_b_ratio, vol_cont_val)


# ─── 3.3 柄部检测 ────────────────────────────────────

def _find_handle(
    daily: List[Dict], cup: Dict, t_idx: int, params: Dict
) -> Optional[Dict]:
    """柄部检测 H1-H6"""
    prior_high = cup['prior_high']; bottom = cup['bottom']
    bottom_idx = cup['bottom_idx']
    h_min = params['handle_min_days']; h_max = params['handle_max_days']
    h_dd_max = params['handle_max_drawdown']
    h_pos = params['handle_position_ratio']
    h_vol_r = params['handle_vol_ratio']
    
    # H1: 回升段最高收盘 (杯口日期)
    ascent = daily[bottom_idx:t_idx + 1]
    cup_mouth_price = max(k['close'] for k in ascent)
    if cup_mouth_price < prior_high * 0.85:
        return None
    
    # 找到杯口日期(最后一次达到该价的交易日)
    cup_mouth_idx = None
    for i in range(len(ascent) - 1, -1, -1):
        if ascent[i]['close'] >= cup_mouth_price * 0.99:
            cup_mouth_idx = bottom_idx + i
            break
    
    if cup_mouth_idx is None or t_idx - cup_mouth_idx < h_min:
        return None
    
    # H2: 杯口之后到检测日之间的最低点 = 柄部低点
    handle_seg = daily[cup_mouth_idx:t_idx + 1]
    if len(handle_seg) < h_min or len(handle_seg) > h_max:
        return None
    
    handle_high_price = cup_mouth_price
    handle_low_price = min(k['close'] for k in handle_seg)
    handle_low_idx = cup_mouth_idx + next(i for i, k in enumerate(handle_seg) if k['close'] <= handle_low_price * 1.001)
    
    # 柄部回调
    h_dd = (handle_high_price - handle_low_price) / handle_high_price
    if h_dd > h_dd_max:
        return None
    
    # H3: 柄部位置在上半部
    cup_height = prior_high - bottom
    if handle_low_price < bottom + cup_height * h_pos:
        return None
    
    # H4: 柄部成交量萎缩
    h_avg_vol = sum(k['volume'] for k in handle_seg) / len(handle_seg)
    cup_body = daily[cup['prior_idx']:t_idx + 1]
    cup_avg_vol = sum(k['volume'] for k in cup_body) / max(len(cup_body), 1)
    if cup_avg_vol > 0 and h_avg_vol / cup_avg_vol > h_vol_r:
        return None
    
    # H5: 柄部斜率 ≤ 0
    h_closes = [k['close'] for k in handle_seg]
    slope = _linear_slope(h_closes)
    if slope > 0.001:
        return None
    
    # H6: 柄部低点 ≥ SMA50
    sma50_idx = _sma_before([k['close'] for k in daily], 50, t_idx)
    if sma50_idx > 0 and handle_low_price < sma50_idx:
        return None
    
    return {
        'handle_high_price': handle_high_price,
        'handle_low_price': handle_low_price,
        'handle_high_date': daily[cup_mouth_idx]['date'],
        'handle_low_date': daily[handle_low_idx]['date'],
        'handle_drawdown': h_dd,
        'handle_days': len(handle_seg),
        'handle_vol_ratio': h_avg_vol / cup_avg_vol if cup_avg_vol > 0 else 0,
    }


# ─── 3.4 突破验证 ────────────────────────────────────

def _check_breakout(
    daily: List[Dict], t_idx: int, cup: Dict, handle: Optional[Dict], params: Dict
) -> Optional[float]:
    """突破日验证 B1-B5，返回买点或None"""
    t_row = daily[t_idx]; t_close = t_row['close']; t_vol = t_row['volume']
    t_open = t_row['open']; t_high = t_row['high']; t_low = t_row['low']
    buffer = params['breakout_buffer']
    vol_ratio_req = params['breakout_vol_ratio']
    
    # B1: 买点
    if handle:
        buy_point = handle['handle_high_price'] + buffer
    else:
        buy_point = cup['prior_high'] + buffer
    
    if t_close < buy_point:
        return None
    
    # B2: 成交量放大 (50日均量取[t-50, t-1])
    sma50_vol = _sma_before([k['volume'] for k in daily], 50, t_idx)
    if sma50_vol <= 0 or t_vol < sma50_vol * vol_ratio_req:
        return None
    
    # B3: 阳线(可关)
    if params.get('require_green', True) and t_close <= t_open:
        return None
    
    # B4: 收盘高位
    if t_high > t_low:
        pos = (t_close - t_low) / (t_high - t_low)
        if pos < params['close_position_min']:
            return None
    
    # B5: 均线多头
    sma50_c = _sma([k['close'] for k in daily[:t_idx+1]], 50)
    if t_close <= sma50_c:
        return None
    if t_idx >= 150:
        sma150_c = _sma([k['close'] for k in daily[:t_idx+1]], 150)
        if t_close <= sma150_c:
            return None
    
    return buy_point


# ─── 3.5 虚假突破排除 ────────────────────────────────

def _check_false_breakout(
    daily: List[Dict], t_idx: int, buy_point: float, handle: Optional[Dict], params: Dict
) -> bool:
    """返回True=假突破，信号作废"""
    t_row = daily[t_idx]
    lookback = params['fake_breakout_lookback']
    
    # 成交量不足
    sma50_vol = _sma_before([k['volume'] for k in daily], 50, t_idx)
    if t_row['volume'] < sma50_vol:
        return True
    
    # 前N日有放量下跌
    for i in range(max(0, t_idx - lookback), t_idx):
        row = daily[i]
        if row['close'] < row['open'] and row['volume'] > sma50_vol * 1.3:
            return True
    
    # 柄部形成期间成交量放大
    if handle:
        hd = handle.get('handle_days', 10)
        handle_seg = daily[max(0, t_idx - hd):t_idx]
        if len(handle_seg) >= 3:
            h_vols = [k['volume'] for k in handle_seg]
            if max(h_vols) > min(h_vols) * 2:
                return True
    
    return False


# ─── 主检测函数 ──────────────────────────────────────

def detect(
    daily: List[Dict],
    params: Optional[Dict] = None,
    market_cap: Optional[float] = None,
    rs_info: Optional[Dict] = None,
) -> List[Dict]:
    """检测杯柄形态突破信号"""
    if params is None:
        params = load_params()
    
    n = len(daily)
    min_bars = params['lookback'] + 50
    if n < min_bars:
        return []
    
    # 市值过滤
    if market_cap is not None and params['min_market_cap'] > 0:
        if market_cap < params['min_market_cap']:
            return []
    
    signals = []
    lookback = params['lookback']
    
    # 遍历每个可能检测日
    for t_idx in range(min_bars, n):
        t_row = daily[t_idx]; t_date = t_row['date']
        
        # ── 条件0.2: SMA50趋势 ──
        sma50_c = _sma([k['close'] for k in daily[:t_idx+1]], 50)
        if t_row['close'] <= sma50_c:
            continue
        
        # ── 3.2.1 定位前高和杯底 ──
        cup = _find_prior_high_and_bottom(daily, t_idx, params)
        if cup is None:
            continue
        
        # ── 条件0.1: 前置上涨 ──
        prior_adv = _check_prior_advance(daily, cup['prior_high_date'], cup['prior_high'], params)
        if prior_adv < params['min_prior_advance']:
            continue
        
        # ── 3.2.2 杯身回升验证 ──
        if not _check_recovery(daily, cup, t_idx, params):
            continue
        
        # ── 3.2.3 成交量验证 ──
        vol_result = _check_volume(daily, cup, t_idx, params)
        if vol_result is None:
            continue
        vol_b_ratio, vol_cont_val = vol_result
        
        # ── 3.3 柄部检测 ──
        handle = _find_handle(daily, cup, t_idx, params)
        has_handle = handle is not None
        if params.get('handle_required', True) and not has_handle:
            continue
        
        # ── 3.4 突破验证 ──
        buy_point = _check_breakout(daily, t_idx, cup, handle, params)
        if buy_point is None:
            continue
        
        # ── 3.5 虚假突破排除 ──
        if _check_false_breakout(daily, t_idx, buy_point, handle, params):
            continue
        
        # ── 3.6 RS验证(可关) ──
        if params.get('rs_required', False) and rs_info:
            rs_ok = (rs_info.get('rs_20', 0) >= params['rs_threshold'] or
                     rs_info.get('rs_60', 0) >= params['rs_threshold'] or
                     rs_info.get('rs_250', 0) >= params['rs_threshold'])
            if not rs_ok:
                continue
        
        # ── 输出 ──
        t_row = daily[t_idx]
        sma50_v = _sma_before([k['volume'] for k in daily], 50, t_idx)
        signal = {
            'signal_date': t_date,
            'pattern_type': 'cup_with_handle' if has_handle else 'cup_no_handle',
            'prior_high_date': cup['prior_high_date'],
            'prior_high_price': round(float(cup['prior_high']), 2),
            'bottom_date': cup['bottom_date'],
            'bottom_price': round(float(cup['bottom']), 2),
            'bottom_amp_5d': round(
                (max(k['close'] for k in daily[max(0,cup['bottom_idx']-5):cup['bottom_idx']+6]) -
                 min(k['close'] for k in daily[max(0,cup['bottom_idx']-5):cup['bottom_idx']+6])) /
                min(k['close'] for k in daily[max(0,cup['bottom_idx']-5):cup['bottom_idx']+6]) * 100, 1
            ),
            'drawdown_pct': round(cup['drawdown'] * 100, 1),
            'descent_days': cup['descent_days'],
            'ascent_days': t_idx - cup['bottom_idx'],
            'handle_high_date': handle['handle_high_date'] if has_handle else None,
            'handle_high_price': round(float(handle['handle_high_price']), 2) if has_handle else None,
            'handle_low_date': handle['handle_low_date'] if has_handle else None,
            'handle_low_price': round(float(handle['handle_low_price']), 2) if has_handle else None,
            'handle_drawdown_pct': round(handle['handle_drawdown'] * 100, 1) if has_handle else None,
            'handle_vol_ratio': round(float(handle.get('handle_vol_ratio', 0)), 3) if has_handle else None,
            'buy_point': round(float(buy_point), 2),
            'breakout_close': round(float(t_row['close']), 2),
            'breakout_vol_ratio': round(t_row['volume'] / sma50_v, 2) if sma50_v > 0 else 0,
            'breakout_chg_pct': round((t_row['close'] - t_row['open']) / t_row['open'] * 100, 2) if t_row['open'] > 0 else 0,
            'close_position': round((t_row['close'] - t_row['low']) / (t_row['high'] - t_row['low']), 2) if t_row['high'] > t_row['low'] else 1,
            'prior_advance_pct': round(prior_adv * 100, 1),
            'market_cap': round(float(market_cap), 1) if market_cap else None,
            'close_vs_sma50': round(t_row['close'] / sma50_c, 3) if sma50_c > 0 else 0,
        }
        signals.append(signal)
    
    return signals


# ─── CLI ─────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='杯柄形态识别')
    parser.add_argument('--stock', type=str, default='600519')
    parser.add_argument('--date', type=str, default=datetime.now().strftime('%Y-%m-%d'))
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    klines = conn.execute("""
        SELECT date, open, high, low, close, volume FROM daily_kline
        WHERE stock_code=? AND date<=? AND date>=date(?,'-600 days')
        ORDER BY date
    """, (args.stock, args.date, args.date)).fetchall()
    conn.close()

    if len(klines) < 170:
        print(f"K线不足: {len(klines)}")
        sys.exit(1)

    daily = [dict(r) for r in klines]
    params = load_params()
    sigs = detect(daily, params)

    print(f"🔍 {args.stock} @ {args.date}")
    print(f"   杯柄形态突破信号: {len(sigs)}")
    for s in sigs:
        print(f"   📅 {s['signal_date']} {s['pattern_type']} 买点={s['buy_point']}")
        print(f"      前高={s['prior_high_price']}({s['prior_high_date']}) 杯底={s['bottom_price']}({s['bottom_date']})")
        print(f"      回调={s['drawdown_pct']}% 下行={s['descent_days']}天 回升={s['ascent_days']}天")
        if s['handle_high_price']:
            print(f"      柄部高={s['handle_high_price']} 柄部低={s['handle_low_price']} 回撤={s['handle_drawdown_pct']}%")
        print(f"      突破量比={s['breakout_vol_ratio']} 涨幅={s['breakout_chg_pct']}%")
