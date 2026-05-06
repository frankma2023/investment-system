"""
指数机构吸筹/出货评级 (A/D Rating for Indices) 计算引擎

基于IBD Accumulation/Distribution Rating 理念，迁移至指数层面。
衡量机构资金在指数上的近期净流入/流出程度，输出A+~E-字母评级。

算法：
  1. MFV[t] = (2*Close - High - Low) / (High - Low) * Amount
  2. AD_Line[t] = Σ_{i=t-64}^{t} MFV[i]   (65日滚动窗口)
  3. 池内百分位排名 → 映射A+~E-评级
  4. AD_Score = (百分位 × 2) - 100   (连续得分 -100~+100)

输入：
  - pool_klines: {code: [{date, open, high, low, close, amount}]}
  - pool_definitions: {pool_name: [index_codes]}
  - as_of_date: 计算截止日期
  - window_days: 滚动窗口交易日数 (默认65)

输出：
  - rankings: [{code, ad_line, percentile, rating, ad_score}]
"""


def compute_mfv(k):
    """
    计算单日资金流量 (Money Flow Value)

    MFV = (2*Close - High - Low) / (High - Low) * Amount
    一字板（High==Low）时 MFV = 0
    """
    high = k.get('high')
    low = k.get('low')
    close = k.get('close')
    amount = k.get('amount', 0) or 0

    if high is None or low is None or close is None:
        return 0.0

    hl_range = high - low
    if hl_range <= 0 or amount == 0:
        return 0.0

    # (2*P - H - L) / (H - L) 范围 [-1, 1]
    position = (2.0 * close - high - low) / hl_range
    return position * amount


def compute_ad_line(klines, as_of_idx, window_days):
    """
    计算指定日期的滚动AD线（过去 window_days 个交易日的 MFV 累积和）

    Args:
        klines: 按日期升序的K线列表
        as_of_idx: 截止日索引
        window_days: 滚动窗口交易日数

    Returns:
        float or None: AD_Line值，数据不足返回 None
    """
    if as_of_idx < window_days - 1:
        return None

    total = 0.0
    for i in range(as_of_idx - window_days + 1, as_of_idx + 1):
        total += compute_mfv(klines[i])
    return total


def compute_ad_for_pool(pool_codes, pool_klines, as_of_date, window_days=65):
    """
    对单个分类池内所有指数计算A/D评级

    Args:
        pool_codes: 池内指数代码列表
        pool_klines: {code: [kline_dicts]}  按日期升序
        as_of_date: 计算截止日期
        window_days: 滚动窗口天数（默认65）

    Returns:
        list of dict: 按 AD_Line 降序排列
    """
    results = []

    for code in pool_codes:
        klines = pool_klines.get(code, [])
        if not klines:
            continue

        # 定位截止日索引
        as_of_idx = None
        for i, k in enumerate(klines):
            if k['date'] == as_of_date:
                as_of_idx = i
                break
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

        # 计算AD线
        ad_line = compute_ad_line(klines, as_of_idx, window_days)

        # 最新收盘价和涨跌幅
        k = klines[as_of_idx]
        change_pct = k.get('change')
        if change_pct is None:
            change_pct = k.get('change_pct', 0)

        results.append({
            'code': code,
            'date': as_of_date_actual,
            'close': k['close'],
            'change_pct': round(change_pct, 2) if change_pct else 0,
            'ad_line': ad_line,
            'percentile': None,
            'rating': None,
            'ad_score': None,
        })

    # ── 计算池内百分位排名 ──
    valid = [(i, item['ad_line']) for i, item in enumerate(results) if item['ad_line'] is not None]
    if valid:
        n = len(valid)
        valid.sort(key=lambda x: x[1], reverse=True)  # AD_Line 越大排名越高

        for rank, (idx, _) in enumerate(valid):
            beats = n - 1 - rank
            if n > 1:
                percentile = round(beats / (n - 1) * 100.0, 1)
            else:
                percentile = 50.0
            results[idx]['percentile'] = percentile
            results[idx]['rating'] = percentile_to_rating(percentile)
            results[idx]['ad_score'] = round(percentile * 2 - 100, 0)

    # 按 AD_Line 降序排列
    results.sort(key=lambda x: x.get('ad_line') or float('-inf'), reverse=True)
    return results


def percentile_to_rating(pct):
    """百分位映射为字母评级"""
    if pct >= 90:
        return 'A+'
    elif pct >= 80:
        return 'A'
    elif pct >= 70:
        return 'B+'
    elif pct >= 60:
        return 'B'
    elif pct >= 50:
        return 'C+'
    elif pct >= 40:
        return 'C'
    elif pct >= 30:
        return 'D+'
    elif pct >= 20:
        return 'D'
    elif pct >= 10:
        return 'E'
    else:
        return 'E-'


# ── 评级含义映射 ──
RATING_MEANINGS = {
    'A+': '机构强烈吸筹（最佳）',
    'A': '机构强烈吸筹',
    'B+': '机构较强烈吸筹',
    'B': '机构温和吸筹',
    'C+': '机构买入稍大于卖出，基本平衡',
    'C': '机构买卖大致平衡',
    'D+': '机构温和出货',
    'D': '机构大力出货',
    'E': '机构强烈出货',
    'E-': '机构强烈出货（最差）',
}


def detect(pool_klines, pool_definitions, as_of_date, window_days=65):
    """
    A/D评级检测主入口。

    Args:
        pool_klines:     {code: [kline_dicts]}  按日期升序
        pool_definitions: {pool_name: [index_codes]}
        as_of_date:      计算截止日期 "YYYY-MM-DD"
        window_days:     滚动窗口天数（默认65）

    Returns:
        {
            'as_of_date': str,
            'window_days': int,
            'pools': { pool_name: {'rankings': [...]} }
        }
    """
    result = {
        'as_of_date': as_of_date,
        'window_days': window_days,
        'pools': {},
    }

    for pool_name, pool_codes in pool_definitions.items():
        rankings = compute_ad_for_pool(pool_codes, pool_klines, as_of_date, window_days)
        result['pools'][pool_name] = {
            'rankings': rankings,
        }

    return result
