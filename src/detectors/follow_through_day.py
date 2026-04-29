"""
追盘日 (Follow-Through Day) 检测引擎
按时间顺序扫描K线，维护反弹尝试状态机。

规则：
  Day 1(反弹尝试日): 创20日新低 AND (收盘>昨收 OR 收盘>中价)
  FTD(D+4~10): 收涨 + 放量(>前日) + 收盘在上半部
  失效: 破位(5天收盘<FTD最低) | 无力上涨(10天涨<2%) | 回撤过深(15天回撤>涨幅50%) | 抛盘覆盖(20天≥3个)

返回: (rally_attempts, active_ftds, failed_ftds)
"""

def detect(klines, config, distribution_signals=None):
    """
    klines:   [{'date','open','close','high','low','volume','change_pct','prev_close'}, ...]
    config:   配置字典 (follow_through_day.yaml 内容)
    distribution_signals: 抛盘日信号列表 [{'date', 'type', 'weight'}, ...]

    Returns: (rally_attempts, active_ftds, failed_ftds)
    """
    if not klines:
        return [], [], []

    # ── 读取配置 ──────────────────────────────────────
    rc = config.get('rally', {})
    new_low_days = rc.get('new_low_days', 20)
    close_strength = rc.get('close_strength', 'either')
    protection_days = rc.get('protection_days', 5)

    fc = config.get('ftd', {})
    window_start = fc.get('window_start', 4)
    window_end = fc.get('window_end', 10)
    min_gain_pct = fc.get('min_gain_pct', 0.0)
    min_vol_ratio = fc.get('min_vol_ratio_prev', 1.0)
    vol_ma10_enabled = fc.get('vol_ratio_ma10_enabled', False)
    vol_ma10_threshold = fc.get('vol_ratio_ma10', 0.0)
    close_pos_min = fc.get('close_position_min', 50)

    rfc = config.get('rally_failure', {})
    reset_start = rfc.get('reset_window_start', 2)
    reset_end = rfc.get('reset_window_end', 10)
    no_ftd_days = rfc.get('no_ftd_days', 10)

    fac = config.get('failure', {})
    breakdown_days = fac.get('breakdown_days', 5)
    weak_days = fac.get('weak_continuation_days', 10)
    weak_min_gain = fac.get('weak_continuation_min_gain', 2.0)
    retrace_enabled = fac.get('retracement_enabled', True)
    retrace_days = fac.get('retracement_days', 15)
    retrace_ratio = fac.get('retracement_ratio', 0.618)
    min_retrace_pct = fac.get('min_retracement_pct', 2.0)
    dist_days = fac.get('distribution_cover_days', 20)
    dist_count = fac.get('distribution_cover_count', 3)

    # ── 索引抛盘日 ────────────────────────────────────
    dist_set = set()
    dist_by_date = {}
    if distribution_signals:
        for ds in distribution_signals:
            d = ds['date']
            w = ds.get('weight', 1)
            dist_set.add(d)
            dist_by_date[d] = w

    # ── 索引K线 ──────────────────────────────────────
    n = len(klines)
    by_idx = {k['date']: i for i, k in enumerate(klines)}

    # ── 辅助函数 ──────────────────────────────────────
    def new_n_day_low(idx):
        """当日最低 < 最近 N 日最低（含当日）"""
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

    def is_ftd_day(idx):
        """判断单日是否满足追盘日条件"""
        k = klines[idx]
        # 涨幅
        gain = k['close'] > k.get('prev_close', 0)
        if min_gain_pct > 0:
            if k.get('change_pct', 0) < min_gain_pct:
                return False
        elif not gain:
            return False
        # 量比(前日)
        prev_idx = idx - 1
        if prev_idx >= 0 and klines[prev_idx].get('volume', 0) > 0:
            vr = k['volume'] / klines[prev_idx]['volume']
        else:
            vr = 0
        if vr < min_vol_ratio:
            return False
        # 量比(MA10) - 可选
        if vol_ma10_enabled and vol_ma10_threshold > 0:
            vols = [klines[j]['volume'] for j in range(max(0, idx - 9), idx + 1)]
            ma10 = sum(vols) / len(vols)
            if ma10 > 0 and k['volume'] / ma10 < vol_ma10_threshold:
                return False
        # 收盘位置
        tr = k['high'] - k['low']
        if tr > 0:
            pos = (k['close'] - k['low']) / tr * 100
        else:
            pos = 100
        if pos < close_pos_min:
            return False
        return True

    def get_dist_count_in_window(date, days):
        """统计 date 之后 days 天内的抛盘日加权数量"""
        di = by_idx.get(date)
        if di is None:
            return 0
        count = 0
        for j in range(di + 1, min(di + days + 1, n)):
            d = klines[j]['date']
            if d in dist_set:
                count += dist_by_date.get(d, 1)
        return count

    def get_max_gain_in_window(date, days):
        """计算 date 之后 days 天内累计最大涨幅"""
        di = by_idx.get(date)
        if di is None:
            return 0
        base_close = klines[di]['close']
        if base_close <= 0:
            return 0
        max_gain = 0
        for j in range(di + 1, min(di + days + 1, n)):
            g = (klines[j]['close'] - base_close) / base_close * 100
            if g > max_gain:
                max_gain = g
        return max_gain

    def get_low_since_date(date, end_date=None):
        """获取 date 之后所有K线的最低价（截止 end_date）"""
        di = by_idx.get(date)
        if di is None:
            return float('inf')
        end_i = by_idx.get(end_date, n - 1) if end_date else n - 1
        return min(klines[j]['low'] for j in range(di, min(end_i + 1, n)))

    def check_retracement(ftd_idx, days, ratio, min_retrace):
        """回撤过深：FTD后days天内从最高点回撤 > 最大涨幅 × ratio（先过绝对值门槛）"""
        ftd_close = klines[ftd_idx]['close']
        if ftd_close <= 0:
            return False, None, None, None, None
        peak_close = ftd_close
        peak_date = klines[ftd_idx]['date']
        for j in range(ftd_idx + 1, min(ftd_idx + days + 1, n)):
            c = klines[j]['close']
            if c > peak_close:
                peak_close = c
                peak_date = klines[j]['date']
            if peak_close > ftd_close:
                dd = round((peak_close - c) / peak_close * 100, 1)
                if dd < min_retrace:
                    continue
                mg = round((peak_close - ftd_close) / ftd_close * 100, 1)
                if mg > 0 and dd > ratio * mg:
                    return True, dd, mg, klines[j]['date'], peak_date
        return False, None, None, None, None

    # ── 状态机主循环 ─────────────────────────────────
    rally_attempts = []
    active_ftds = []
    failed_ftds = []

    day1_idx = None    # 当前反弹尝试日的索引
    day1_date = None
    day1_low = None

    i = 0
    while i < n:
        k = klines[i]
        date = k['date']

        # ── 检查追盘日窗口 ──────────────────────────
        if day1_idx is not None:
            days_from_d1 = i - day1_idx
            if window_start <= days_from_d1 <= window_end:
                if is_ftd_day(i):
                    # FTD 触发了！
                    ftd = {
                        'date': date,
                        'ftd_type': 'normal',
                        'rally_date': day1_date,
                        'days_from_d1': days_from_d1,
                        'gain_pct': round(k.get('change_pct', 0), 2),
                        'close': k['close'],
                        'close_position': round(
                            (k['close'] - k['low']) / (k['high'] - k['low']) * 100, 1
                        ) if k['high'] != k['low'] else 100,
                        'failed': False,
                        'failure_reason': ''
                    }

                    # ── 检查失效条件（按优先级）──────────
                    # 1) 破位失效：FTD后breakdown_days天内收盘 < FTD最低价
                    ftd_idx = i
                    ftd_low = k['low']
                    if not ftd['failed'] and breakdown_days > 0:
                        for j in range(ftd_idx + 1, min(ftd_idx + breakdown_days + 1, n)):
                            if klines[j]['close'] < ftd_low:
                                ftd['failed'] = True
                                ftd['failure_reason'] = f'破位失效: {klines[j]["date"]} 收盘{round(klines[j]["close"],2)} < FTD最低{round(ftd_low,2)}'
                                break

                    # 2) 无力上涨
                    if not ftd['failed'] and weak_days > 0:
                        mg = get_max_gain_in_window(date, weak_days)
                        if mg < weak_min_gain:
                            ftd['failed'] = True
                            ftd['failure_reason'] = f'无力上涨: FTD后{weak_days}天最大涨幅{round(mg,1)}% < {weak_min_gain}%'

                    # 3) 回撤过深
                    if not ftd['failed'] and retrace_enabled and retrace_days > 0:
                        ret_failed, ret_dd, ret_mg, ret_date, peak_date = check_retracement(ftd_idx, retrace_days, retrace_ratio, min_retrace_pct)
                        if ret_failed:
                            ftd['failed'] = True
                            ftd['failure_reason'] = f'回撤过深: {ret_date} 从{peak_date}高点回撤{ret_dd}% > 最大涨幅{ret_mg}%的{int(retrace_ratio*100)}%'

                    # 4) 抛盘日覆盖
                    if not ftd['failed'] and dist_days > 0:
                        dc = get_dist_count_in_window(date, dist_days)
                        if dc >= dist_count:
                            ftd['failed'] = True
                            ftd['failure_reason'] = f'抛盘日覆盖: FTD后{dist_days}天内{dist_count}个抛盘日(加权{round(dc,1)})'

                    if ftd['failed']:
                        failed_ftds.append(ftd)
                    else:
                        active_ftds.append(ftd)

                    # FTD触发后，Day1已完成使命
                    day1_idx = None
                    day1_date = None
                    day1_low = None
                    i += 1
                    continue

            elif days_from_d1 > no_ftd_days:
                # 超过反弹尝试窗口，反弹尝试失败，计数器归零
                day1_idx = None
                day1_date = None
                day1_low = None

        # ── 检查反弹尝试保护窗口 ────────────────────
        if day1_idx is not None:
            # Day 1~protection_days: 任意一天收盘<Day1最低 → 反弹失败
            days_from_d1 = i - day1_idx
            if 1 <= days_from_d1 <= protection_days:
                if k['close'] < day1_low:
                    # 反弹失败，查看是否触发新反弹
                    day1_idx = None
                    day1_date = None
                    day1_low = None
                    # 不continue — 继续检查下面是否新反弹

        # ── 检查新反弹尝试日（仅在第 reset_start~reset_end 天内允许重置）─────
        if is_rally_day(i):
            if day1_idx is not None:
                days_from_d1 = i - day1_idx
                if k['low'] < day1_low:
                    if reset_start <= days_from_d1 <= reset_end:
                        # 窗口内出现更低低点+收盘强势 → 重置为新Day1
                        pass  # 继续往下，用新Day1覆盖
                    else:
                        # 窗口外，不重置
                        i += 1
                        continue
                else:
                    # 低点不够低，不重置
                    i += 1
                    continue

            # 记录反弹尝试（新Day1或更新Day1）
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

    return rally_attempts, active_ftds, failed_ftds
