"""缠论 vs 欧奈尔回测对比引擎

对观察池股票回溯 3 个月的缠论信号表现。
运行: cd D:\hanako\investment-system && python src/scanners/chanlun_backtest_compare.py
"""

import sys, os, sqlite3, json, random
from datetime import datetime, timedelta

# 确保 src/ 在 sys.path 中
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

DB_PATH = os.path.join(SRC_DIR, '..', 'data', 'lixinger.db')
MONTHS_BACK = 3
HORIZONS = [5, 10, 20]
RANDOM_SAMPLES = 3


def get_obs_stocks():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT stock_code FROM discipline_observation_pool
        WHERE date = (SELECT MAX(date) FROM discipline_observation_pool)
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_close_prices(code, since_date):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT date, close FROM daily_kline
        WHERE stock_code = ? AND date >= ?
        ORDER BY date
    """, (code, since_date)).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def compute_forward_returns(prices, price_dates, entry_dt, entry_price):
    """计算 entry 日买入后的 N 日收益"""
    try:
        idx = price_dates.index(entry_dt)
    except ValueError:
        return None
    result = {}
    for h in HORIZONS:
        fut_idx = idx + h
        if fut_idx < len(price_dates):
            fut_close = prices[price_dates[fut_idx]]
            result[h] = round((fut_close - entry_price) / entry_price * 100, 2)
        else:
            return None  # 数据不足
    return result


def run_backtest():
    from scanners.chanlun import analyze

    stocks = get_obs_stocks()
    cutoff = (datetime.now() - timedelta(days=MONTHS_BACK * 30)).strftime('%Y-%m-%d')
    # 日线数据范围需要覆盖信号日期 + 最大持有期
    price_since = (datetime.now() - timedelta(days=MONTHS_BACK * 35 + max(HORIZONS))).strftime('%Y-%m-%d')

    print(f'回测开始: {len(stocks)} 只股票, 起点 {cutoff}')

    all_signals = []
    random_entries = []

    for i, code in enumerate(stocks):
        # 获取价格数据
        prices = get_close_prices(code, price_since)
        if len(prices) < 60:
            continue

        # 缠论分析
        try:
            r = analyze(code, 'D', 500, data_mode='stock')
        except Exception as e:
            if (i + 1) % 100 == 0:
                print(f'  [{i+1}/{len(stocks)}] {code} 分析失败: {e}')
            continue

        # 处理买入信号
        for ts in r.get('trade_signals', []):
            if ts['side'] != 'buy':
                continue
            dt = ts['dt']
            if dt < cutoff or ts['price'] is None or dt not in prices:
                continue

            returns = compute_forward_returns(prices, sorted(prices.keys()), dt, ts['price'])
            if returns is None:
                continue

            record = {
                'code': code,
                'type': ts['type'],
                'side': 'buy',
                'dt': dt,
                'price': ts['price'],
                'confidence': ts.get('confidence', '低'),
                'returns': returns
            }
            all_signals.append(record)

            # 随机对比点（同股票，不同日期，等量采样）
            price_dates = sorted(prices.keys())
            signal_dates = {s['dt'] for s in all_signals[-5:]}
            candidates = [d for d in price_dates if d >= cutoff and d <= max(price_dates) and d not in signal_dates]
            if len(candidates) >= RANDOM_SAMPLES:
                for rd in random.sample(candidates, min(RANDOM_SAMPLES, len(candidates))):
                    r_returns = compute_forward_returns(prices, price_dates, rd, prices[rd])
                    if r_returns:
                        random_entries.append({
                            'code': code, 'type': '随机', 'dt': rd,
                            'price': prices[rd], 'returns': r_returns
                        })

        if (i + 1) % 100 == 0:
            print(f'  进度: {i+1}/{len(stocks)} (信号: {len(all_signals)}, 随机: {len(random_entries)})')

    print(f'完成: {len(stocks)} 只, {len(all_signals)} 个信号, {len(random_entries)} 个随机点')
    return compute_stats(all_signals, random_entries), all_signals, random_entries


def compute_stats(signals, randoms):
    stats = {}
    for h in HORIZONS:
        h_str = f'{h}d'
        s = [x for x in signals if h in x['returns']]
        r = [x for x in randoms if h in x['returns']]

        # A: 缠论 vs 随机
        s_ret = [x['returns'][h] for x in s]
        r_ret = [x['returns'][h] for x in r]
        stats[f'A_{h_str}'] = {
            'label': '缠论 vs 随机',
            'chanlun_avg': round(sum(s_ret) / len(s_ret), 2) if s_ret else 0,
            'chanlun_win': round(sum(1 for v in s_ret if v > 0) / len(s_ret) * 100, 1) if s_ret else 0,
            'chanlun_n': len(s_ret),
            'random_avg': round(sum(r_ret) / len(r_ret), 2) if r_ret else 0,
            'random_win': round(sum(1 for v in r_ret if v > 0) / len(r_ret) * 100, 1) if r_ret else 0,
            'random_n': len(r_ret),
        }

        # B: 高/中/低置信度
        for conf in ['高', '中', '低']:
            cs = [x for x in s if x['confidence'] == conf and h in x['returns']]
            ret = [x['returns'][h] for x in cs]
            stats[f'B_{h_str}_{conf}'] = {
                'avg': round(sum(ret) / len(ret), 2) if ret else 0,
                'win': round(sum(1 for v in ret if v > 0) / len(ret) * 100, 1) if ret else 0,
                'n': len(ret)
            }

        # C: 一买 vs 三买
        for tp in ['一买', '三买']:
            ts = [x for x in s if x['type'] == tp and h in x['returns']]
            ret = [x['returns'][h] for x in ts]
            stats[f'C_{h_str}_{tp}'] = {
                'avg': round(sum(ret) / len(ret), 2) if ret else 0,
                'win': round(sum(1 for v in ret if v > 0) / len(ret) * 100, 1) if ret else 0,
                'n': len(ret)
            }

    return stats


if __name__ == '__main__':
    stats, signals, randoms = run_backtest()

    out_dir = os.path.join(SRC_DIR, '..', 'web', 'chanlun-backtest-compare')
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, 'data.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f'\nJSON: {out_dir}/data.json')
    print(f'\n=== 回测摘要 ===')
    for k, v in sorted(stats.items()):
        print(f'  {k}: {v}')
