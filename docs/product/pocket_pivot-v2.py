"""
口袋支点(Pocket Pivot)识别引擎 v2 — 修复版

五步规则（RS 不作为硬过滤，仅输出）：
  1. 趋势基础: close > SMA50, SMA50斜率≥0, close > SMA10
  2. 日内行为: 收盘位置≥50%, 阳线
  3. 成交量: vol > 过去10日最大阴线量
  4. 延伸区: 距65日低点≤50%
  5. RS 输出: 查询 RPS 值附加到信号（不满足不丢弃信号）

类型：延续口袋支点 / 10日线反弹口袋支点

用法：
  cd D:\hanako\investment-system
  python src\pocket_pivot.py --stock 600519 --debug
  python src\pocket_pivot.py --stock 600519 --date 2026-05-08
"""

import sys, os, argparse, sqlite3, yaml
from datetime import datetime, date as dt_date

# ── 项目路径探测 ──
_REAL_PROJECT = r"D:\hanako\investment-system"
_candidate = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.exists(os.path.join(_candidate, "data", "lixinger.db")):
    PROJECT_DIR = _candidate
else:
    PROJECT_DIR = _REAL_PROJECT

sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")


def load_params():
    cfg_path = os.path.join(PROJECT_DIR, "config", "market", "pocket_pivot.yaml")
    defaults = {
        'sma10_check': True, 'sma50_check': True, 'sma50_slope_10d': 0.002,
        'close_position_min': 0.50, 'require_green': True,
        'vol_down_lookback': 10, 'vol_fallback_enabled': True,
        'extension_lookback': 65, 'extension_max_pct': 0.50,
        'rs_threshold': 80, 'rs_dual_require': False,
        'ma10_bounce_proximity': 0.02,
        'exclude_limit_up': True, 'min_listing_days': 120,
    }
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        defaults.update(cfg.get('pocket_pivot', {}))
    return defaults


def detect(klines, params=None, rs_info=None, debug=False):
    """
    klines: [{'date','open','high','low','close','volume'}, ...] 升序
    rs_info: {'rs_20': int, 'rs_250': int} (缺失时填 0，不作为过滤条件)
    """
    if params is None:
        params = load_params()

    SMA10_EN = params.get('sma10_check', True)
    SMA50_EN = params.get('sma50_check', True)
    SMA50_SLOPE = params.get('sma50_slope_10d', 0.002)
    CLOSE_POS = params.get('close_position_min', 0.50)
    GREEN = params.get('require_green', True)
    VOL_LB = params.get('vol_down_lookback', 10)
    VOL_FB = params.get('vol_fallback_enabled', True)
    EXT_LB = params.get('extension_lookback', 65)
    EXT_MAX = params.get('extension_max_pct', 0.50)
    MA10_PROX = params.get('ma10_bounce_proximity', 0.02)
    EXCL_UP = params.get('exclude_limit_up', True)

    n = len(klines)
    if n < 120:
        if debug:
            print(f"  [数据不足] 仅 {n} 条K线, 需要 ≥ 120")
        return []

    # ── 预计算均线（不含当天 —— fix Bug #2） ──
    sma10 = [0] * n
    sma50 = [0] * n
    for i in range(n):
        if i >= 10:
            cs = [klines[j]['close'] for j in range(i - 10, i) if klines[j].get('close') is not None]
            sma10[i] = sum(cs) / len(cs) if cs else 0
        if i >= 50:
            cs = [klines[j]['close'] for j in range(i - 50, i) if klines[j].get('close') is not None]
            sma50[i] = sum(cs) / len(cs) if cs else 0

    # ── debug 计数器 ──
    stats = {
        'scanned': 0, 'trend_ok': 0, 'intraday_ok': 0,
        'vol_ok': 0, 'ext_ok': 0, 'signal': 0,
        'fail_reasons': {},
    }

    signals = []
    for i in range(65, n):
        stats['scanned'] += 1
        k = klines[i]
        close = k['close']
        if close is None:
            continue

        # ── 步骤 1: 趋势 ──
        trend_fail = None
        if SMA50_EN and (sma50[i] <= 0 or close <= sma50[i]):
            trend_fail = 'trend_sma50'
        elif SMA50_EN and sma50[i] > 0 and i >= 10:
            if sma50[i-10] > 0 and (sma50[i] - sma50[i-10]) / sma50[i-10] < SMA50_SLOPE:
                trend_fail = 'trend_sma50_slope'
        if trend_fail is None and SMA10_EN and sma10[i] > 0 and close <= sma10[i]:
            trend_fail = 'trend_sma10'
        if trend_fail:
            if debug:
                _bump(stats, trend_fail, k['date'],
                      f"C={close:.2f} SMA10={sma10[i]:.2f} SMA50={sma50[i]:.2f}")
            continue
        stats['trend_ok'] += 1

        # ── 步骤 2: 日内 ──
        if k['high'] != k['low']:
            pos = (close - k['low']) / (k['high'] - k['low'])
        else:
            pos = 1.0
        if pos < CLOSE_POS:
            if debug:
                _bump(stats, 'intraday_pos', k['date'], f"收盘位置 {pos:.0%} < {CLOSE_POS:.0%}")
            continue
        if GREEN and close <= k['open']:
            if debug:
                _bump(stats, 'intraday_green', k['date'],
                      f"开 ¥{k['open']:.2f} 收 ¥{close:.2f} → 阴线")
            continue
        if EXCL_UP and k['high'] == k['low'] and close >= k['open']:
            if debug:
                _bump(stats, 'intraday_limit_up', k['date'], "一字涨停")
            continue
        stats['intraday_ok'] += 1

        # ── 步骤 3: 成交量 (fix Bug #4: 显式初始化 vol_ratio) ──
        vol_ratio = 0
        max_down_vol = 0
        has_down = False
        for j in range(max(0, i - VOL_LB), i):
            if klines[j].get('close') and klines[j].get('open') and klines[j]['close'] < klines[j]['open']:
                v = klines[j].get('volume') or 0
                if v > max_down_vol:
                    max_down_vol = v
                has_down = True
        if has_down and max_down_vol > 0:
            vol_ratio = k['volume'] / max_down_vol
            if k['volume'] <= max_down_vol:
                if debug:
                    _bump(stats, 'vol_down', k['date'],
                          f"量 {k['volume']:.0f} ≤ 最大阴线量 {max_down_vol:.0f} (ratio={vol_ratio:.2f})")
                continue
        elif VOL_FB:
            if i >= 50:
                vs = [klines[j]['volume'] for j in range(i-50, i) if klines[j].get('volume') is not None]
                ma50v = sum(vs) / len(vs) if vs else 0
                vol_ratio = k['volume'] / ma50v if ma50v > 0 else 0
                if ma50v > 0 and k['volume'] <= ma50v * 1.5:
                    if debug:
                        _bump(stats, 'vol_fallback', k['date'],
                              f"量 {k['volume']:.0f} ≤ 1.5×MA50({ma50v:.0f}) ratio={vol_ratio:.2f}")
                    continue
        else:
            if debug:
                _bump(stats, 'vol_no_data', k['date'], "无阴线且 fallback 关闭")
            continue
        stats['vol_ok'] += 1

        # ── 步骤 4: 延伸区 ──
        if EXT_LB > 0:
            low_65 = min(klines[j]['close'] for j in range(max(0, i-EXT_LB), i) if klines[j].get('close') is not None)
            if low_65 > 0 and close > low_65 * (1 + EXT_MAX):
                if debug:
                    _bump(stats, 'extension', k['date'],
                          f"C={close:.2f} > 65d低点×1.5={low_65*1.5:.2f} (距低点{(close/low_65-1)*100:.0f}%)")
                continue
        stats['ext_ok'] += 1

        # ── 步骤 5: RS 仅输出，不丢弃信号 ──
        rs_out = {'rs_20': rs_info['rs_20'] if rs_info else 0,
                  'rs_250': rs_info['rs_250'] if rs_info else 0}

        # ── 类型判定 (fix Bug #3: 10日线反弹加 close > yesterday_close) ──
        ptype = 'continuation'
        if sma10[i] > 0 and k['low'] <= sma10[i] * (1 + MA10_PROX):
            yesterday_close = klines[i-1].get('close') if i > 0 else 0
            if yesterday_close and close > yesterday_close:
                ptype = '10ma_bounce'

        stats['signal'] += 1
        signals.append({
            'date': k['date'], 'close': close, 'volume': k['volume'],
            'close_position': round(pos, 2),
            'vol_ratio': round(vol_ratio, 2),
            'sma50': round(sma50[i], 2), 'sma10': round(sma10[i], 2),
            'rs_20': rs_out['rs_20'], 'rs_250': rs_out['rs_250'],
            'pivot_type': ptype,
        })

    if debug:
        _print_debug_summary(stats, n)

    return signals


def _bump(stats, reason, date, detail=""):
    if reason not in stats['fail_reasons']:
        stats['fail_reasons'][reason] = {'count': 0, 'samples': []}
    stats['fail_reasons'][reason]['count'] += 1
    if len(stats['fail_reasons'][reason]['samples']) < 3:
        stats['fail_reasons'][reason]['samples'].append(f"{date}: {detail}")


def _print_debug_summary(stats, total_klines):
    scanned = stats['scanned']
    print(f"\n{'='*60}")
    print(f"  DEBUG — 口袋支点过滤漏斗（总K线: {total_klines}, 扫描: {scanned} 天）")
    print(f"{'='*60}")
    print(f"  扫描天数:              {scanned:>6}")
    print(f"  趋势通过 (SMA):        {stats['trend_ok']:>6}  ({stats['trend_ok']/max(scanned,1)*100:5.1f}%)")
    print(f"  日内行为通过:          {stats['intraday_ok']:>6}  ({stats['intraday_ok']/max(stats['trend_ok'],1)*100:5.1f}%)")
    print(f"  成交量通过:            {stats['vol_ok']:>6}  ({stats['vol_ok']/max(stats['intraday_ok'],1)*100:5.1f}%)")
    print(f"  延伸区通过:            {stats['ext_ok']:>6}  ({stats['ext_ok']/max(stats['vol_ok'],1)*100:5.1f}%)")
    print(f"  最终信号:              {stats['signal']:>6}")

    if stats['fail_reasons']:
        print(f"\n  失败原因分布 (top 10):")
        sorted_reasons = sorted(stats['fail_reasons'].items(), key=lambda x: -x[1]['count'])
        for reason, info in sorted_reasons[:10]:
            pct = info['count'] / max(scanned, 1) * 100
            bar = '█' * int(pct / 2)
            print(f"    {reason:<22s} {info['count']:>5}  ({pct:5.1f}%) {bar}")
            for sample in info['samples'][:1]:
                print(f"      例: {sample}")
    print(f"{'='*60}\n")


def get_rs(conn, stock_code, target_date):
    """获取 RS 值，失败返回全 0 —— 不阻塞信号生成"""
    row = conn.execute("""SELECT rps_20, rps_250 FROM stock_rs_daily
        WHERE stock_code=? AND date<=? ORDER BY date DESC LIMIT 1""",
        (stock_code, target_date)).fetchone()
    if not row:
        return {'rs_20': 0, 'rs_250': 0}
    return {'rs_20': row['rps_20'] or 0, 'rs_250': row['rps_250'] or 0}


def detect_for_stock(stock_code, target_date, params=None, debug=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""SELECT date,open,high,low,close,volume FROM daily_kline
        WHERE stock_code=? AND date<=? ORDER BY date""",
        (stock_code, target_date)).fetchall()
    if len(rows) < 120:
        conn.close()
        if debug:
            print(f"  [数据不足] {stock_code} 仅 {len(rows)} 条K线, 需要 ≥ 120")
        return []
    klines = [dict(r) for r in rows]
    rs_info = get_rs(conn, stock_code, target_date)
    conn.close()
    return detect(klines, params, rs_info, debug=debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", type=str, default="600519")
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--debug", action="store_true", default=False,
                        help="打印每层过滤漏斗统计")
    args = parser.parse_args()
    target = args.date or dt_date.today().strftime("%Y-%m-%d")
    params = load_params()
    signals = detect_for_stock(args.stock, target, params, debug=args.debug)
    print(f"\n{args.stock} @ {target}  口袋支点信号: {len(signals)}")
    for s in signals[-8:]:
        print(f"  {s['date']}  C={s['close']:.2f}  pos={s['close_position']}  "
              f"vol_r={s['vol_ratio']}  RPS20={s['rs_20']}  RPS250={s['rs_250']}  "
              f"type={s['pivot_type']}")
