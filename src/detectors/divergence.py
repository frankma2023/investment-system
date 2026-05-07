"""
指数背离检测引擎

四种背离类型:
  1. 量价背离 (volume_price): 快/慢两种模式
  2. RSI背离 (rsi): 固定70/30 + 可选动态分位
  3. MACD背离 (macd): 标准12/26/9
  4. 成分股上涨比例背离 (breadth): 全成分股或前20权重股

信号等级: 1=潜在, 2=确认, 3=强烈
数据存入 index_divergence_daily 表。
"""


def compute_ema(values, period):
    """指数移动平均"""
    if len(values) < period:
        return [None] * len(values)
    result = [None] * len(values)
    # 首个EMA用SMA替代
    sma = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    result[period - 1] = sma
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(closes, period=14):
    """RSI指标"""
    if len(closes) < period + 1:
        return [None] * len(closes)

    rsi = [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)

        if i + 1 < len(closes):
            diff = closes[i] - closes[i - 1]
            gain = max(diff, 0)
            loss = max(-diff, 0)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

    return rsi


def compute_macd(closes, fast=12, slow=26, signal=9):
    """MACD: 返回 (macd_line, signal_line, histogram)"""
    ema_fast = compute_ema(closes, fast)
    ema_slow = compute_ema(closes, slow)

    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    signal_line = compute_ema([v if v is not None else 0 for v in macd_line], signal)
    # 只从有效位置开始
    start = slow + signal - 1
    for i in range(start):
        if signal_line[i] is not None:
            signal_line[i] = None

    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]

    return macd_line, signal_line, histogram


def find_peak_in_window(values, end_idx, window):
    """在 [end_idx-window+1, end_idx] 中找峰值"""
    start = max(0, end_idx - window + 1)
    best_idx = start
    for i in range(start, end_idx + 1):
        if values[i] is not None and (values[best_idx] is None or values[i] > values[best_idx]):
            best_idx = i
    return best_idx, values[best_idx]


def find_trough_in_window(values, end_idx, window):
    """在 [end_idx-window+1, end_idx] 中找谷值"""
    start = max(0, end_idx - window + 1)
    best_idx = start
    for i in range(start, end_idx + 1):
        if values[i] is not None and (values[best_idx] is None or values[i] < values[best_idx]):
            best_idx = i
    return best_idx, values[best_idx]


# ═══════════════════════════════════════════
# 背离检测函数
# ═══════════════════════════════════════════


def detect_volume_price_divergence(klines, params, as_of_idx):
    """
    量价背离检测。返回 dict 或 None。

    params: { mode, ma_days, lookback, min_strength }
    """
    mode = params.get('mode', 'slow')
    ma_days = params.get('ma_days', 5)
    lookback = params.get('lookback', 10)
    min_strength = params.get('min_strength', 3.0)

    if as_of_idx < max(ma_days, lookback):
        return None

    closes = [k['close'] for k in klines]
    volumes = [k.get('volume', 0) or 0 for k in klines]

    if mode == 'fast':
        # 点对点: 今日 vs 昨日
        if as_of_idx < 1:
            return None
        p_change = (closes[as_of_idx] - closes[as_of_idx - 1]) / closes[as_of_idx - 1] * 100
        v_change = (volumes[as_of_idx] - volumes[as_of_idx - 1]) / max(volumes[as_of_idx - 1], 1) * 100
    else:
        # 均线趋势: MA vs N日前MA
        if as_of_idx < lookback:
            return None
        ma_now = sum(closes[as_of_idx - ma_days + 1:as_of_idx + 1]) / ma_days
        ma_past = sum(closes[as_of_idx - lookback - ma_days + 1:as_of_idx - lookback + 1]) / ma_days
        p_change = (ma_now - ma_past) / ma_past * 100

        vma_now = sum(volumes[as_of_idx - ma_days + 1:as_of_idx + 1]) / ma_days
        vma_past = sum(volumes[as_of_idx - lookback - ma_days + 1:as_of_idx - lookback + 1]) / ma_days
        v_change = (vma_now - vma_past) / max(vma_past, 1) * 100

    strength = abs(p_change) + abs(v_change)
    if strength < min_strength:
        return None

    if p_change > 0 and v_change < 0:
        return {'type': 'top', 'level': 1, 'strength': round(strength, 1),
                'detail': f'价涨{round(p_change,1)}% 量缩{round(abs(v_change),1)}%'}
    elif p_change < 0 and v_change > 0:
        return {'type': 'bottom', 'level': 1, 'strength': round(strength, 1),
                'detail': f'价跌{round(abs(p_change),1)}% 量增{round(v_change,1)}%'}
    return None


def detect_rsi_divergence(klines, params, as_of_idx):
    """
    RSI背离检测。

    params: { period, lookback, overbought, oversold, dynamic_percentile }
    """
    period = params.get('period', 14)
    lookback = params.get('lookback', 20)
    ob = params.get('overbought', 70)
    os = params.get('oversold', 30)
    dynamic = params.get('dynamic_percentile', False)

    if as_of_idx < period + lookback:
        return None

    closes = [k['close'] for k in klines]
    rsi = compute_rsi(closes, period)

    if rsi[as_of_idx] is None:
        return None

    cur_rsi = rsi[as_of_idx]
    cur_price = closes[as_of_idx]

    if dynamic:
        # 动态分位: 取过去250日RSI的90%/10%分位
        hist_start = max(0, as_of_idx - 250)
        hist_rsi = [v for v in rsi[hist_start:as_of_idx + 1] if v is not None]
        if len(hist_rsi) >= 100:
            hist_rsi.sort()
            ob = hist_rsi[int(len(hist_rsi) * 0.9)]
            os = hist_rsi[int(len(hist_rsi) * 0.1)]

    # 顶背离检查
    peak_idx, peak_rsi = find_peak_in_window(rsi, as_of_idx - 1, lookback)
    price_peak = max(closes[max(0, as_of_idx - lookback):as_of_idx])
    if cur_price > price_peak and cur_rsi < peak_rsi and cur_rsi > ob and peak_rsi is not None:
        return {'type': 'top', 'level': 1,
                'detail': f'RSI顶背离: 价格新高, RSI{round(cur_rsi,1)}<峰值{round(peak_rsi,1)}'}

    # 底背离检查
    trough_idx, trough_rsi = find_trough_in_window(rsi, as_of_idx - 1, lookback)
    price_trough = min(closes[max(0, as_of_idx - lookback):as_of_idx])
    if cur_price < price_trough and cur_rsi > trough_rsi and cur_rsi < os and trough_rsi is not None:
        return {'type': 'bottom', 'level': 1,
                'detail': f'RSI底背离: 价格新低, RSI{round(cur_rsi,1)}>谷值{round(trough_rsi,1)}'}

    return None


def detect_macd_divergence(klines, params, as_of_idx):
    """
    MACD背离检测。

    params: { fast, slow, signal, lookback }
    """
    fast = params.get('fast', 12)
    slow = params.get('slow', 26)
    signal = params.get('signal', 9)
    lookback = params.get('lookback', 20)

    if as_of_idx < slow + signal + lookback:
        return None

    closes = [k['close'] for k in klines]
    _, _, hist = compute_macd(closes, fast, slow, signal)

    if hist[as_of_idx] is None:
        return None

    cur_hist = hist[as_of_idx]
    cur_price = closes[as_of_idx]

    # 顶背离: 价格 > 前高, MACD柱 < 前峰值, 柱 > 0
    price_peak = max(closes[max(0, as_of_idx - lookback):as_of_idx])
    hist_peak_idx, hist_peak = find_peak_in_window(hist, as_of_idx - 1, lookback)
    if cur_price > price_peak and hist_peak is not None and cur_hist < hist_peak and cur_hist > 0:
        return {'type': 'top', 'level': 1,
                'detail': f'MACD顶背离: 价格新高, 柱线走低'}

    # 底背离: 价格 < 前低, MACD柱 > 前谷值, 柱 < 0
    price_trough = min(closes[max(0, as_of_idx - lookback):as_of_idx])
    hist_trough_idx, hist_trough = find_trough_in_window(hist, as_of_idx - 1, lookback)
    if cur_price < price_trough and hist_trough is not None and cur_hist > hist_trough and cur_hist < 0:
        return {'type': 'bottom', 'level': 1,
                'detail': f'MACD底背离: 价格新低, 柱线走高'}

    return None


def detect_breadth_divergence(klines, advance_ratios, as_of_idx, params):
    """
    成分股上涨比例背离。

    advance_ratios: 每日上涨比例列表(与klines等长)
    params: { consecutive_days, top_threshold, bottom_threshold }
    """
    cd = params.get('consecutive_days', 2)
    top_th = params.get('top_threshold', 50)
    bot_th = params.get('bottom_threshold', 40)

    if as_of_idx < cd or not advance_ratios or as_of_idx >= len(advance_ratios):
        return None

    closes = [k['close'] for k in klines]
    cur_ratio = advance_ratios[as_of_idx]

    # 顶背离: 涨 + 参与度降 + < 50%
    if closes[as_of_idx] > closes[as_of_idx - 1] and cur_ratio < advance_ratios[as_of_idx - 1] and cur_ratio < top_th:
        # 检查连续天数
        ok = True
        for j in range(as_of_idx - cd + 1, as_of_idx + 1):
            if j <= 0 or closes[j] <= closes[j - 1] or advance_ratios[j] >= advance_ratios[j - 1]:
                ok = False
                break
        if ok:
            return {'type': 'top', 'level': 1,
                    'detail': f'成分股背离: 指数涨, 上涨占比仅{round(cur_ratio,1)}%'}

    # 底背离: 跌 + 参与度升 + < 40%
    if closes[as_of_idx] < closes[as_of_idx - 1] and cur_ratio > advance_ratios[as_of_idx - 1] and cur_ratio < bot_th:
        ok = True
        for j in range(as_of_idx - cd + 1, as_of_idx + 1):
            if j <= 0 or closes[j] >= closes[j - 1] or advance_ratios[j] <= advance_ratios[j - 1]:
                ok = False
                break
        if ok:
            return {'type': 'bottom', 'level': 1,
                    'detail': f'成分股背离: 指数跌, 上涨占比改善至{round(cur_ratio,1)}%'}

    return None


# ═══════════════════════════════════════════
# 确认等级升级
# ═══════════════════════════════════════════


def confirm_divergence(klines, as_of_idx, div_result, confirm_window=20):
    """
    根据价格确认升级背离等级。

    顶背离: 价格跌破 confirm_window 日低点 → 确认(2)
           均线死叉(5穿10) → 强烈(3)
    底背离: 价格突破 confirm_window 日高点 → 确认(2)
           均线金叉(5穿10) → 强烈(3)
    """
    if div_result is None:
        return None

    closes = [k['close'] for k in klines]
    div_type = div_result['type']

    if as_of_idx < confirm_window:
        return div_result

    if div_type == 'top':
        # 跌破20日低点 → 确认
        low_20 = min(closes[max(0, as_of_idx - confirm_window + 1):as_of_idx + 1])
        if closes[as_of_idx] < closes[as_of_idx - 1] and closes[as_of_idx] <= low_20 * 1.01:
            div_result['level'] = 2
        # 5日线穿10日线 → 强烈
        ma5 = sum(closes[max(0, as_of_idx - 4):as_of_idx + 1]) / min(5, as_of_idx + 1)
        ma10 = sum(closes[max(0, as_of_idx - 9):as_of_idx + 1]) / min(10, as_of_idx + 1)
        ma5_prev = sum(closes[max(0, as_of_idx - 5):as_of_idx]) / min(5, as_of_idx) if as_of_idx >= 5 else ma5
        ma10_prev = sum(closes[max(0, as_of_idx - 10):as_of_idx]) / min(10, as_of_idx) if as_of_idx >= 10 else ma10
        if ma5_prev > ma10_prev and ma5 < ma10:
            div_result['level'] = 3
    else:
        # 突破20日高点 → 确认
        high_20 = max(closes[max(0, as_of_idx - confirm_window + 1):as_of_idx + 1])
        if closes[as_of_idx] > closes[as_of_idx - 1] and closes[as_of_idx] >= high_20 * 0.99:
            div_result['level'] = 2
        # 5日线穿10日线 → 强烈
        ma5 = sum(closes[max(0, as_of_idx - 4):as_of_idx + 1]) / min(5, as_of_idx + 1)
        ma10 = sum(closes[max(0, as_of_idx - 9):as_of_idx + 1]) / min(10, as_of_idx + 1)
        ma5_prev = sum(closes[max(0, as_of_idx - 5):as_of_idx]) / min(5, as_of_idx) if as_of_idx >= 5 else ma5
        ma10_prev = sum(closes[max(0, as_of_idx - 10):as_of_idx]) / min(10, as_of_idx) if as_of_idx >= 10 else ma10
        if ma5_prev < ma10_prev and ma5 > ma10:
            div_result['level'] = 3

    return div_result


# ═══════════════════════════════════════════
# 共振评分
# ═══════════════════════════════════════════


def compute_resonance(divergences, rs_rating, ad_rating, crowd_level):
    """
    计算共振强度。

    divergences: {vp, rsi, macd, breadth} 四个背离结果(None或dict)
    返回 (resonance_level, alert_text)
    """

    # 极端信号判定
    bearish_modules = []
    bullish_modules = []

    if rs_rating in ('A+', 'A'):
        bullish_modules.append('RS强度' + rs_rating)
    elif rs_rating in ('D', 'E'):
        bearish_modules.append('RS强度' + rs_rating)

    if ad_rating in ('A+', 'A'):
        bullish_modules.append('A/D评级' + ad_rating)
    elif ad_rating in ('D', 'E'):
        bearish_modules.append('A/D评级' + ad_rating)

    if crowd_level == '高拥挤':
        bearish_modules.append('拥挤度高')
    elif crowd_level in ('低拥挤',):
        bullish_modules.append('拥挤度低')

    # 收集背离
    top_divs = [k for k, v in divergences.items() if v and v.get('type') == 'top']
    bot_divs = [k for k, v in divergences.items() if v and v.get('type') == 'bottom']

    has_top = len(top_divs) > 0
    has_bot = len(bot_divs) > 0

    # 共振判定
    if has_top and len(bearish_modules) >= 2:
        return ('高', f'{" ".join(bearish_modules)} + {",".join(top_divs)}顶背离 → 高共振 · 强烈回调风险')
    if has_bot and len(bullish_modules) >= 2:
        return ('高', f'{" ".join(bullish_modules)} + {",".join(bot_divs)}底背离 → 高共振 · 强烈反转机会')
    if has_top and len(bearish_modules) >= 1:
        return ('中', f'{" ".join(bearish_modules)} + {",".join(top_divs)}顶背离 → 中共振')
    if has_bot and len(bullish_modules) >= 1:
        return ('中', f'{" ".join(bullish_modules)} + {",".join(bot_divs)}底背离 → 中共振')
    if has_top and len(top_divs) >= 2:
        return ('中', f'{",".join(top_divs)}双重顶背离 → 中共振')
    if has_bot and len(bot_divs) >= 2:
        return ('中', f'{",".join(bot_divs)}双重底背离 → 中共振')
    if has_top:
        return ('低', f'{",".join(top_divs)}顶背离')
    if has_bot:
        return ('低', f'{",".join(bot_divs)}底背离')

    return ('无', '')
