"""
标准突破买点识别引擎 (v2 — debug 增强版)

基于通达信基部+突破逻辑：
  1. 120日内存在峰→谷结构(涨幅>30%, 峰值在前)
  2. 回撤12%~33%
  3. 谷底右侧反弹≥峰谷距离60%
  4. 反弹高点距今5~20天
  5. RS_20/60/250 任一≥87
  6. 昨日满足基部条件, 今日收盘突破反弹高点
  7. 峰值距今>30天

用法：
  cd D:\hanako\investment-system
  python src\breakout_scanner.py --stock 600519 --debug --no-rs   # debug 模式（推荐先跑这个）
  python src\breakout_scanner.py --stock 600519 --date 2026-05-08
  python src\breakout_scanner.py --stock 000858 --debug --no-rs   # 测试五粮液
"""

import sys, os, argparse, sqlite3
from datetime import datetime, date as dt_date

# ── 实际项目路径（拷到 src/ 下时会自动计算，在 docs/ 下调试时用硬编码） ──
_REAL_PROJECT = r"D:\hanako\investment-system"
_candidate = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 如果从 src/ 运行，两层 dirname 即为项目根；否则退回到硬编码路径
if os.path.exists(os.path.join(_candidate, "data", "lixinger.db")):
    PROJECT_DIR = _candidate
else:
    PROJECT_DIR = _REAL_PROJECT

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


def detect(klines, params=None, rs_info=None, debug=False):
    """
    klines: [{'date','open','high','low','close','volume'}, ...] 按日期升序
    rs_info: {'rs_20': int, 'rs_60': int, 'rs_250': int} 或 None
    debug: 打印每层过滤统计
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
    if n < LB + 1:   # fix: 121 条才够跑
        if debug:
            print(f"  [数据不足] 仅 {n} 条K线, 需要 ≥ {LB+1}")
        return []

    # 预计算均量（不包含当天 —— fix Bug #2）
    ma50_vols = []
    for i in range(n):
        if i >= 50:
            vs = [klines[j]['volume'] for j in range(i - 50, i) if klines[j].get('volume') is not None]
            ma50_vols.append(sum(vs) / len(vs) if vs else 0)
        else:
            ma50_vols.append(0)

    # debug 计数器
    stats = {
        'scanned': 0,         # 进入循环的天数
        'base_ok': 0,         # 基部条件通过
        'breakout_ok': 0,     # 突破收盘价通过
        'vol_ok': 0,          # 量比通过
        'green_ok': 0,        # 阳线通过
        'close_pos_ok': 0,    # 收盘位置通过
        'signal': 0,          # 最终信号
        'base_fail_reasons': {},  # 基部条件失败原因分布
    }

    signals = []
    for i in range(LB + 1, n):
        stats['scanned'] += 1
        today = klines[i]

        # ── B6 + XG: 昨日满足基部条件 + 今日收盘突破昨日反弹高点 ──
        base_result = _check_base_conditions_with_rh(klines, i - 1, params, debug_stats=(stats if debug else None))
        yesterday_base = base_result if isinstance(base_result, (int, float)) else base_result[0]
        if not yesterday_base:
            continue
        stats['base_ok'] += 1
        rh_val_yd = yesterday_base
        if today['close'] <= rh_val_yd:
            if debug:
                _bump_reason(stats, 'breakout_close', today['date'],
                    f"收盘 ¥{today['close']:.2f} ≤ 反弹高点 ¥{rh_val_yd:.2f}")
            continue
        stats['breakout_ok'] += 1

        # ── 成交量 ──
        if i >= 50 and ma50_vols[i] > 0:
            vol_ratio = today['volume'] / ma50_vols[i]
            if vol_ratio < VOL_R:
                if debug:
                    _bump_reason(stats, 'vol_ratio', today['date'],
                        f"量比 {vol_ratio:.2f} < {VOL_R}  (ma50={ma50_vols[i]:.0f})")
                continue
        else:
            vol_ratio = 0
            if debug:
                _bump_reason(stats, 'vol_ratio', today['date'], "MA50 数据不足")
            continue
        stats['vol_ok'] += 1

        # ── 阳线 ──
        if GREEN and today['close'] <= today['open']:
            if debug:
                _bump_reason(stats, 'green_candle', today['date'],
                    f"开 ¥{today['open']:.2f} 收 ¥{today['close']:.2f}  → 阴线")
            continue
        stats['green_ok'] += 1

        # ── 收盘位置 ──
        if today['high'] != today['low']:
            pos = (today['close'] - today['low']) / (today['high'] - today['low'])
            if pos < CLOSE_POS:
                if debug:
                    _bump_reason(stats, 'close_pos', today['date'],
                        f"收盘位置 {pos:.0%} < {CLOSE_POS:.0%}")
                continue
        stats['close_pos_ok'] += 1

        # ── 从昨日窗口提取基部元数据 ──
        yd_window = klines[i - 1 - LB:i]
        yd_highs = [(k['high'], j) for j, k in enumerate(yd_window) if k['high'] is not None]
        yd_lows = [(k['low'], j) for j, k in enumerate(yd_window) if k['low'] is not None]
        yd_hh_val, yd_hh_idx = max(yd_highs, key=lambda x: x[0])
        yd_ll_val, yd_ll_idx = min(yd_lows, key=lambda x: x[0])
        yd_rh_list = [(k['high'], j) for j, k in enumerate(yd_window[yd_ll_idx:], start=yd_ll_idx) if k['high'] is not None]
        _, yd_rh_idx = max(yd_rh_list, key=lambda x: x[0])

        stats['signal'] += 1
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

    if debug:
        _print_debug_summary(stats, n, LB)

    return signals


def _check_base_conditions_with_rh(klines, i, params, debug_stats=None):
    """检查单日是否满足 B1~B4，返回反弹高点值 或 (0, None)"""
    LB = params['lookback']
    MIN_R = params['min_range_pct'] / 100.0
    DD_MIN = params['drawdown_min'] / 100.0
    DD_MAX = params['drawdown_max'] / 100.0
    RB = params['rebound_ratio'] / 100.0
    HOLD_MIN = params['hold_min']
    HOLD_MAX = params['hold_max']
    PEAK_AGE = params['peak_age_min']

    if i < LB:
        return 0 if debug_stats is None else (0, 'i<LB')
    window = klines[i - LB:i + 1]
    wl = len(window)

    highs = [(k['high'], j) for j, k in enumerate(window) if k['high'] is not None]
    lows = [(k['low'], j) for j, k in enumerate(window) if k['low'] is not None]
    if not highs or not lows:
        return 0 if debug_stats is None else (0, 'no_highs_or_lows')

    hh_val, hh_idx = max(highs, key=lambda x: x[0])
    ll_val, ll_idx = min(lows, key=lambda x: x[0])

    # B1: 峰在谷前
    if hh_idx >= ll_idx:
        if debug_stats:
            _bump_reason(debug_stats, 'B1_peak_before_trough', klines[i]['date'],
                f"峰idx={hh_idx} 谷idx={ll_idx}  → 峰不在谷前")
        return 0 if debug_stats is None else (0, 'B1')

    # B1.5: 前置上涨检查 (fix Bug #3)
    pre_peak_lows = [(k['low'], j) for j, k in enumerate(window[:hh_idx]) if k['low'] is not None]
    if pre_peak_lows:
        pl_val, _ = min(pre_peak_lows, key=lambda x: x[0])
        prior_advance = (hh_val - pl_val) / pl_val
        if prior_advance < MIN_R:
            if debug_stats:
                _bump_reason(debug_stats, 'B1_prior_advance', klines[i]['date'],
                    f"前置涨幅 {prior_advance:.1%} < {MIN_R:.0%}  (峰前最低 ¥{pl_val:.2f} → 峰 ¥{hh_val:.2f})")
            return 0 if debug_stats is None else (0, 'B1.5')
    else:
        # 无峰前数据，退化为总振幅检查
        total_range = (hh_val - ll_val) / hh_val
        if total_range < MIN_R:
            if debug_stats:
                _bump_reason(debug_stats, 'B1_range', klines[i]['date'],
                    f"总振幅 {total_range:.1%} < {MIN_R:.0%}")
            return 0 if debug_stats is None else (0, 'B1.5')

    # B2: 回撤检查
    dd = (hh_val - ll_val) / hh_val
    if dd < DD_MIN or dd > DD_MAX:
        if debug_stats:
            _bump_reason(debug_stats, 'B2_drawdown', klines[i]['date'],
                f"回撤 {dd:.1%} 不在 [{DD_MIN:.0%}, {DD_MAX:.0%}]")
        return 0 if debug_stats is None else (0, 'B2')

    # B3: 反弹检查
    rh_list = [(k['high'], j) for j, k in enumerate(window[ll_idx:], start=ll_idx) if k['high'] is not None]
    if not rh_list:
        if debug_stats:
            _bump_reason(debug_stats, 'B3_no_rebound', klines[i]['date'], "谷底右侧无反弹高点")
        return 0 if debug_stats is None else (0, 'B3')
    rh_val, rh_idx = max(rh_list, key=lambda x: x[0])
    rebound_ratio = (rh_val - ll_val) / (hh_val - ll_val) if (hh_val - ll_val) > 0 else 0
    if rebound_ratio < RB:
        if debug_stats:
            _bump_reason(debug_stats, 'B3_rebound', klines[i]['date'],
                f"反弹比例 {rebound_ratio:.1%} < {RB:.0%}  (反弹 ¥{rh_val:.2f})")
        return 0 if debug_stats is None else (0, 'B3')

    # B4: 反弹距今检查
    days_from_rh = wl - 1 - rh_idx
    if days_from_rh < HOLD_MIN or days_from_rh > HOLD_MAX:
        if debug_stats:
            _bump_reason(debug_stats, 'B4_hold_days', klines[i]['date'],
                f"反弹距今 {days_from_rh} 天 不在 [{HOLD_MIN}, {HOLD_MAX}]")
        return 0 if debug_stats is None else (0, 'B4')

    # B7: 峰龄检查
    peak_age = wl - 1 - hh_idx
    if peak_age < PEAK_AGE:
        if debug_stats:
            _bump_reason(debug_stats, 'B7_peak_age', klines[i]['date'],
                f"峰龄 {peak_age} 天 < {PEAK_AGE}")
        return 0 if debug_stats is None else (0, 'B7')

    return rh_val if debug_stats is None else (rh_val, None)


def _bump_reason(stats, reason, date, detail=""):
    """记录失败原因"""
    if reason not in stats['base_fail_reasons']:
        stats['base_fail_reasons'][reason] = {'count': 0, 'samples': []}
    stats['base_fail_reasons'][reason]['count'] += 1
    if len(stats['base_fail_reasons'][reason]['samples']) < 3:
        stats['base_fail_reasons'][reason]['samples'].append(f"{date}: {detail}")


def _print_debug_summary(stats, total_klines, LB):
    """打印 debug 统计"""
    scanned = stats['scanned']
    print(f"\n{'='*60}")
    print(f"  DEBUG — 过滤漏斗（总K线: {total_klines}, 扫描窗口: {scanned} 天）")
    print(f"{'='*60}")
    print(f"  扫描天数:              {scanned:>6}")
    print(f"  基部条件通过 (B1~B7):  {stats['base_ok']:>6}  ({stats['base_ok']/max(scanned,1)*100:5.1f}%)")
    print(f"  ├ 突破收盘 > 反弹高点:  {stats['breakout_ok']:>6}  ({stats['breakout_ok']/max(stats['base_ok'],1)*100:5.1f}%)")
    print(f"  ├ 量比 ≥ 阈值:         {stats['vol_ok']:>6}  ({stats['vol_ok']/max(stats['breakout_ok'],1)*100:5.1f}%)")
    print(f"  ├ 阳线:                {stats['green_ok']:>6}  ({stats['green_ok']/max(stats['vol_ok'],1)*100:5.1f}%)")
    print(f"  ├ 收盘位置 ≥ 阈值:     {stats['close_pos_ok']:>6}")
    print(f"  └ 最终信号:            {stats['signal']:>6}")

    if stats['base_fail_reasons']:
        print(f"\n  基部条件失败原因分布 (top 10):")
        sorted_reasons = sorted(stats['base_fail_reasons'].items(),
                                key=lambda x: -x[1]['count'])
        for reason, info in sorted_reasons[:10]:
            pct = info['count'] / max(scanned, 1) * 100
            bar = '█' * int(pct / 2)
            print(f"    {reason:<25s} {info['count']:>5}  ({pct:5.1f}%) {bar}")
            for sample in info['samples'][:1]:
                print(f"      例: {sample}")

    print(f"{'='*60}\n")


def detect_for_stock(stock_code, target_date, params=None, mode='stock', debug=False, skip_rs=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    table = 'index_daily_kline' if mode == 'index' else 'daily_kline'
    kf = "AND kline_type='normal'" if mode == 'index' else ''
    rows = conn.execute(f"SELECT date, open, high, low, close, volume FROM {table} WHERE stock_code=? {kf} AND date<=? ORDER BY date", (stock_code, target_date)).fetchall()

    if len(rows) < 121:   # fix: Bug #5
        conn.close()
        if debug:
            print(f"  [数据不足] {stock_code} 仅 {len(rows)} 条K线, 需要 ≥ 121")
        return []

    klines = [dict(r) for r in rows]

    # RS 检查 (可跳过 —— 修复 Bug #1)
    if skip_rs:
        rs_ok, rs_info = True, {'rs_20': 0, 'rs_60': 0, 'rs_250': 0}
        if debug:
            print(f"  [RS 跳过] --no-rs 模式, RS 门禁已关闭")
    else:
        rs_ok, rs_info = check_rs(conn, stock_code, target_date,
                                  params.get('rs_threshold', 87) if params else 87, mode)
        if not rs_ok:
            conn.close()
            if debug:
                print(f"  [RS 不达标] {stock_code} RS < {params.get('rs_threshold', 87)}")
            return []

    signals = detect(klines, params, rs_info, debug=debug)
    conn.close()
    return signals


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", type=str, default="600519")
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--mode", type=str, default="stock")
    parser.add_argument("--debug", action="store_true", default=False,
                        help="打印每层过滤漏斗统计")
    parser.add_argument("--no-rs", action="store_true", default=False,
                        help="跳过 RS 检查（表数据缺失时使用）")
    args = parser.parse_args()
    target = args.date or dt_date.today().strftime("%Y-%m-%d")

    params = load_params()
    signals = detect_for_stock(args.stock, target, params, args.mode,
                               debug=args.debug, skip_rs=args.no_rs)
    print(f"\n{args.stock} @ {target}  突破信号数: {len(signals)}")
    for s in signals[-8:]:
        print(f"  {s['date']}  峰{s['peak_date']} ({s['peak_price']:.0f})  "
              f"谷{s['trough_date']} ({s['trough_price']:.0f})  "
              f"反弹{s['rebound_price']:.0f}  回撤{s['drawdown']}%  "
              f"反弹比{s['rebound_pct']}%  量比{s['vol_ratio']}")
