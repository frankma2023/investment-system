"""
指数相对强度 (Index Relative Strength) 计算引擎

功能：
  1. 多周期收益率计算 (20/60/120/250 交易日)
  2. 分类池内独立百分位排名 (RS 0-99)
  3. 三层强势池筛选 (L1 > L2 > L3 优先级)

输入：
  - index_klines: {code: [{date, close, ...}]}  按指数分组的历史K线
  - pools: {pool_name: [index_code, ...]}        分类池定义
  - as_of_date: str                              计算截止日期
  - tier_params: dict                            三层强势池阈值

输出：
  - rankings: [{code, name, RS_20, RS_60, RS_120, RS_250, ...}]
  - tiers: {L1: [...], L2: [...], L3: [...]}
"""


def compute_return(klines, as_of_idx, lookback_days):
    """
    计算区间收益率 RET_N = (P_today / P_{t-N}) - 1

    Args:
        klines: 按时间升序排列的K线列表
        as_of_idx: 截止日在 klines 中的索引
        lookback_days: 回看交易日数

    Returns:
        float or None: 收益率（小数形式），数据不足返回 None
    """
    if as_of_idx < lookback_days:
        return None
    today_close = klines[as_of_idx]['close']
    past_close = klines[as_of_idx - lookback_days]['close']
    if past_close == 0:
        return None
    return (today_close / past_close) - 1


def compute_rs_for_pool(pool_codes, pool_klines, as_of_date):
    """
    对单个分类池内所有指数计算多周期RS

    Args:
        pool_codes: 池内指数代码列表
        pool_klines: {code: [kline_dicts]}  按日期升序
        as_of_date: 计算截止日期

    Returns:
        list of dict: 每个指数的RS结果，按 RS_120 降序排列
    """
    results = []
    periods = [
        ('RET_20', 20),
        ('RET_60', 60),
        ('RET_120', 120),
        ('RET_250', 250),
    ]

    for code in pool_codes:
        klines = pool_klines.get(code, [])
        if not klines:
            continue

        # 定位截止日的索引
        as_of_idx = None
        for i, k in enumerate(klines):
            if k['date'] == as_of_date:
                as_of_idx = i
                break
        # 如果当日无数据（非交易日），回退到最近一个交易日
        if as_of_idx is None:
            for i in range(len(klines) - 1, -1, -1):
                if klines[i]['date'] <= as_of_date:
                    as_of_idx = i
                    as_of_date_actual = klines[i]['date']
                    break
            else:
                continue
        else:
            as_of_date_actual = as_of_date

        # 计算各周期收益率
        rets = {}
        for field, days in periods:
            r = compute_return(klines, as_of_idx, days)
            rets[field] = r

        # 获取最新收盘价和涨跌幅
        k = klines[as_of_idx]
        # index_daily_kline 用 'change' 字段存涨跌幅(%)，非 'change_pct'
        change_pct = k.get('change')
        if change_pct is None:
            change_pct = k.get('change_pct', 0)

        # 计算N日均线（用于L3条件判断）
        ma_days_max = 60
        close_above_ma = {}
        for ma_d in [5, 10, 20, 30, 50, 60]:
            if as_of_idx >= ma_d - 1:
                ma_val = sum(klines[j]['close'] for j in range(as_of_idx - ma_d + 1, as_of_idx + 1)) / ma_d
                close_above_ma[f'MA{ma_d}'] = k['close'] > ma_val
            else:
                close_above_ma[f'MA{ma_d}'] = False

        results.append({
            'code': code,
            'date': as_of_date_actual,
            'close': k['close'],
            'change_pct': round(change_pct, 2) if change_pct else 0,
            'RET_20': rets['RET_20'],
            'RET_60': rets['RET_60'],
            'RET_120': rets['RET_120'],
            'RET_250': rets['RET_250'],
            'RS_20': None,
            'RS_60': None,
            'RS_120': None,
            'RS_250': None,
            'close_above_ma': close_above_ma,
        })

    # ── 计算百分位排名 ──────────────────────────────
    for field, _ in periods:
        # 收集有效收益率
        valid = [(i, item[field]) for i, item in enumerate(results) if item[field] is not None]
        if not valid:
            continue
        n = len(valid)
        # 按收益率降序排列（高收益 = 高排名）
        valid.sort(key=lambda x: x[1], reverse=True)

        # RET_20 → RS_20 字段名映射
        rs_field = field.replace('RET', 'RS')

        for rank, (idx, _) in enumerate(valid):
            # 高于数 = n - 1 - rank  (比自己低的个数)
            beats = n - 1 - rank
            # RS = round(高于数 / (N-1) * 99)，范围 0-99
            if n > 1:
                rs = round(beats / (n - 1) * 99)
            else:
                rs = 50  # 池内仅1个指数，取中性值
            results[idx][rs_field] = rs

    # 按 RS_120 降序排列（默认排序）
    results.sort(key=lambda x: x.get('RS_120') or 0, reverse=True)
    return results


def classify_tiers(pool_results, tier_params):
    """
    对池内RS结果应用三层强势池筛选，L1 > L2 > L3 优先级。

    Args:
        pool_results: compute_rs_for_pool 的输出
        tier_params: {L1: {RS_120, RS_250, RS_60}, L2: {RS_20, RS_60, RS_120}, L3: {RS_60, RS_120, RS_20_max}}

    Returns:
        {L1: [...], L2: [...], L3: [...]}
    """
    tiers = {'L1': [], 'L2': [], 'L3': []}

    for item in pool_results:
        rs20 = item.get('RS_20')
        rs60 = item.get('RS_60')
        rs120 = item.get('RS_120')
        rs250 = item.get('RS_250')

        # 跳过RS数据不完整的指数
        if None in (rs20, rs60, rs120, rs250):
            continue

        # L1: 绝对强势池
        t1 = tier_params.get('L1', {})
        if (rs120 >= t1.get('RS_120', 90) and
            rs250 >= t1.get('RS_250', 85) and
            rs60 >= t1.get('RS_60', 80)):
            tiers['L1'].append(item)
            continue

        # L2: 短期爆发池
        t2 = tier_params.get('L2', {})
        if (rs20 >= t2.get('RS_20', 95) and
            rs60 >= t2.get('RS_60', 85) and
            rs120 >= t2.get('RS_120', 70)):
            item['momentum_delta'] = round(rs20 - rs60, 1) if rs20 is not None and rs60 is not None else None
            tiers['L2'].append(item)
            continue

        # L3: 潜在共振池
        t3 = tier_params.get('L3', {})
        if (rs60 >= t3.get('RS_60', 85) and
            rs120 >= t3.get('RS_120', 80) and
            rs20 < t3.get('RS_20_max', 90)):
            # MA 均线条件（可选）
            ma_days = t3.get('ma_days', 0)
            if ma_days > 0:
                ma_key = f'MA{ma_days}'
                if item.get('close_above_ma', {}).get(ma_key, False):
                    item['ma_days'] = ma_days
                    tiers['L3'].append(item)
            else:
                # ma_days=0 表示不检查均线
                tiers['L3'].append(item)
            continue

    return tiers


def detect(pool_klines, pool_definitions, as_of_date, tier_params=None):
    """
    指数RS检测主入口。

    Args:
        pool_klines:     {code: [kline_dicts]}  按日期升序
        pool_definitions: {pool_name: [index_codes]}
        as_of_date:      计算截止日期 "YYYY-MM-DD"
        tier_params:     {L1: {}, L2: {}, L3: {}}  阈值配置，None 则使用默认值

    Returns:
        {
            'as_of_date': str,
            'pools': {
                pool_name: {
                    'rankings': [...],  按 RS_120 降序
                    'tiers': {L1:[], L2:[], L3:[]},
                    'top10': [...],
                }
            }
        }
    """
    if tier_params is None:
        tier_params = {
            'L1': {'RS_120': 90, 'RS_250': 85, 'RS_60': 80},
            'L2': {'RS_20': 95, 'RS_60': 85, 'RS_120': 70},
            'L3': {'RS_60': 85, 'RS_120': 80, 'RS_20_max': 90, 'ma_days': 20},
        }

    result = {
        'as_of_date': as_of_date,
        'pools': {},
    }

    for pool_name, pool_codes in pool_definitions.items():
        rankings = compute_rs_for_pool(pool_codes, pool_klines, as_of_date)
        tiers = classify_tiers(rankings, tier_params)

        # 补充指数名称（从 pool_klines 无法获取名称，调用方负责补）
        top10 = rankings[:10]

        result['pools'][pool_name] = {
            'rankings': rankings,
            'tiers': tiers,
            'top10': top10,
        }

    return result
