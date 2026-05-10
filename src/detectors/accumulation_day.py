"""
吸筹日 (Accumulation Day) 检测引擎
追盘日（FTD）的增强变体：在 FTD 基础上附加更严苛的成交量、收盘强度条件。

与 FTD 的关系：FTD 满足 → 进一步检查 → 满足额外条件 = 吸筹日
吸筹日不是独立信号，而是 FTD 的高置信度版本。

规则（基于吸筹日_v4.md v1.1）：
  Day 1(反弹尝试日): 创20日新低 AND 收盘强势
  吸筹日(D+4~7): 
    ① 收涨 ≥ 1.0%
    ② 成交量 > 前日 1.2倍 AND > 20日均量 1.1倍（比FTD严格：两者都要）
    ③ 收盘强度：振幅≥2%→分位≥0.6 | 振幅<2%→close≥open | high=low→通过
    ④ 可选：无抛盘日干扰(过去5日)
"""

def detect(klines, config, distribution_signals=None):
    """
    klines:   [{'date','open','close','high','low','volume','change_pct','prev_close'}, ...]
    config:   配置字典 (accumulation_day.yaml 内容)
    distribution_signals: 抛盘日信号列表 [{'date', 'type', 'weight'}, ...]

    Returns: (rally_attempts, accumulation_signals)
    accumulation_signals: [{'date','rally_date','days_from_d1','gain_pct','close','close_position',
                            'volume','vol_ratio_prev','vol_ratio_ma20','met_price','met_volume',
                            'met_close_pos','met_no_dist','signal_level'}, ...]
    """
    if not klines:
        return [], []

    # ── 读取配置 ──
    rc = config.get('rally', {})
    new_low_days = rc.get('new_low_days', 20)
    close_strength = rc.get('close_strength', 'either')
    protection_days = rc.get('protection_days', 5)

    ac = config.get('accumulation', {})
    window_start = ac.get('window_start', 4)
    window_end = ac.get('window_end', 7)
    min_gain_pct = ac.get('min_gain_pct', 1.0)
    vol_ratio_prev = ac.get('vol_ratio_prev', 1.2)
    vol_ratio_ma20 = ac.get('vol_ratio_ma20', 1.1)
    close_pos_min = ac.get('close_position_min', 0.6)
    narrow_range_pct = ac.get('narrow_range_pct', 0.02)
    require_no_dist = ac.get('require_no_dist', True)

    rfc = config.get('rally_failure', {})
    reset_start = rfc.get('reset_window_start', 2)
    reset_end = rfc.get('reset_window_end', 10)
    no_signal_days = rfc.get('no_signal_days', 10)

    # ── 索引抛盘日 ──
    dist_set = set()
    if distribution_signals:
        for ds in distribution_signals:
            dist_set.add(ds['date'])

    # ── 索引K线 ──
    n = len(klines)
    by_idx = {k['date']: i for i, k in enumerate(klines)}

    # ── 辅助函数 ──
    def new_n_day_low(idx):
        """当日最低价是最近 N 日最低（含当日）"""
        if idx < new_low_days - 1:
            return False
        window_lows = [klines[j]['low'] for j in range(idx - new_low_days + 1, idx + 1)]
        return klines[idx]['low'] == min(window_lows)

    def close_strong(k):
        """收盘强势：收涨 OR 收盘>中价"""
        gain = k['close'] > k.get('prev_close', 0)
        above_mid = k['close'] > (k['low'] + k['high']) * 0.5
        if close_strength == 'either':
            return gain or above_mid
        else:
            return gain and above_mid

    def is_rally_day(idx):
        """判断是否为反弹尝试日 (Day 1)"""
        k = klines[idx]
        return new_n_day_low(idx) and close_strong(k)

    def check_close_position(k):
        """收盘强度检查：振幅≥2%用分位, <2%用close≥open, high=low直接通过"""
        if k['high'] == k['low']:
            return True, 100.0
        amplitude = (k['high'] - k['low']) / k['close']
        if amplitude < narrow_range_pct:
            passed = k['close'] >= k['open']
            pos = (k['close'] - k['low']) / (k['high'] - k['low']) * 100 if k['high'] != k['low'] else 100
            return passed, round(pos, 1)
        else:
            pos = (k['close'] - k['low']) / (k['high'] - k['low'])
            return pos >= close_pos_min, round(pos * 100, 1)

    def has_dist_in_past(date, days=5):
        """检查过去 days 天内是否有抛盘日"""
        di = by_idx.get(date)
        if di is None:
            return False
        for j in range(max(0, di - days), di):
            if klines[j]['date'] in dist_set:
                return True
        return False

    def is_accumulation_day(idx):
        """判断是否满足吸筹日条件"""
        k = klines[idx]

        # ① 涨幅
        if k.get('change_pct', 0) < min_gain_pct:
            return None

        # ② 成交量：前日比 AND 20日均量比（两者都要）
        prev_idx = idx - 1
        vr_prev = k['volume'] / klines[prev_idx]['volume'] if prev_idx >= 0 and klines[prev_idx].get('volume', 0) > 0 else 0
        vol_window = klines[max(0, idx - 20):idx]
        ma20 = sum(v['volume'] for v in vol_window) / len(vol_window) if vol_window else 0
        vr_ma20 = k['volume'] / ma20 if ma20 > 0 else 0

        met_vol = vr_prev >= vol_ratio_prev and vr_ma20 >= vol_ratio_ma20

        # ③ 收盘强度
        met_pos, pos_val = check_close_position(k)

        # ④ 无抛盘日干扰
        no_dist = not has_dist_in_past(k['date']) if require_no_dist else True

        # 返回详细元数据
        return {
            'met_price': True,
            'met_volume': met_vol,
            'met_close_pos': met_pos,
            'met_no_dist': no_dist,
            'vol_ratio_prev': round(vr_prev, 2),
            'vol_ratio_ma20': round(vr_ma20, 2),
            'close_position': pos_val,
            'passed': True and met_vol and met_pos and no_dist,  # 'True' is price (already checked above)
        }

    # ── 状态机主循环 ──
    rally_attempts = []
    accumulation_signals = []

    day1_idx = None
    day1_date = None
    day1_low = None

    i = 0
    while i < n:
        k = klines[i]
        date = k['date']

        # ── 检查吸筹日窗口 ──
        if day1_idx is not None:
            days_from_d1 = i - day1_idx
            if window_start <= days_from_d1 <= window_end:
                result = is_accumulation_day(i)
                if result and result['passed']:
                    signal = {
                        'date': date,
                        'signal_type': 'accumulation',
                        'rally_date': day1_date,
                        'days_from_d1': days_from_d1,
                        'gain_pct': round(k.get('change_pct', 0), 2),
                        'close': k['close'],
                        'close_position': result['close_position'],
                        'volume': k['volume'],
                        'vol_ratio_prev': result['vol_ratio_prev'],
                        'vol_ratio_ma20': result['vol_ratio_ma20'],
                        'met_price': result['met_price'],
                        'met_volume': result['met_volume'],
                        'met_close_pos': result['met_close_pos'],
                        'met_no_dist': result['met_no_dist'],
                    }
                    accumulation_signals.append(signal)

                    day1_idx = None
                    day1_date = None
                    day1_low = None
                    i += 1
                    continue

            elif days_from_d1 > no_signal_days:
                day1_idx = None
                day1_date = None
                day1_low = None

        # ── 反弹尝试保护窗口 ──
        if day1_idx is not None:
            days_from_d1 = i - day1_idx
            if 1 <= days_from_d1 <= protection_days:
                if k['close'] < day1_low:
                    day1_idx = None
                    day1_date = None
                    day1_low = None

        # ── 检查新反弹尝试日 ──
        if is_rally_day(i):
            if day1_idx is not None:
                days_from_d1 = i - day1_idx
                if k['low'] < day1_low:
                    if reset_start <= days_from_d1 <= reset_end:
                        pass  # 重置
                    else:
                        i += 1
                        continue
                else:
                    i += 1
                    continue

            tr = k['high'] - k['low']
            pos = round((k['close'] - k['low']) / tr * 100, 1) if tr > 0 else 100
            day1_idx = i
            day1_date = date
            day1_low = k['low']
            rally_attempts.append({
                'date': date,
                'low': k['low'],
                'close': k['close'],
                'gain_pct': round(k.get('change_pct', 0), 2),
                'close_position': pos,
                'new_n_day_low': True,
                'n_days': new_low_days,
            })

        i += 1

    return rally_attempts, accumulation_signals
