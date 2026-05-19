"""
峰谷检测工具模块（独立提取）

供 top_pattern、volume_divergence 等引擎共用。
"""

from typing import List, Dict, Tuple, Optional


def find_peaks_troughs(
    df: List[Dict],
    window: int = 5,
    prominence: float = 0.03,
) -> Tuple[List[Dict], List[Dict]]:
    """识别局部高点和低点，带突出度过滤。"""
    highs = [r['high'] for r in df]
    lows = [r['low'] for r in df]
    dates = [r['date'] for r in df]
    n = len(df)

    if n < 2 * window + 1:
        return [], []

    raw_peaks = []
    raw_troughs = []
    for i in range(window, n - window):
        w_high = max(highs[i - window:i + window + 1])
        if highs[i] >= w_high:
            raw_peaks.append({'idx': i, 'price': float(highs[i]), 'date': dates[i]})
        w_low = min(lows[i - window:i + window + 1])
        if lows[i] <= w_low:
            raw_troughs.append({'idx': i, 'price': float(lows[i]), 'date': dates[i]})

    if not raw_peaks and not raw_troughs:
        return [], []

    peaks = []
    for p in raw_peaks:
        left_troughs = [t for t in raw_troughs if t['idx'] < p['idx']]
        right_troughs = [t for t in raw_troughs if t['idx'] > p['idx']]
        nearest_price = None
        if left_troughs:
            nearest_price = left_troughs[-1]['price']
        if right_troughs and (nearest_price is None or right_troughs[0]['price'] > nearest_price):
            nearest_price = right_troughs[0]['price']
        if nearest_price is not None and (p['price'] - nearest_price) / nearest_price >= prominence:
            peaks.append(p)

    troughs = []
    for t in raw_troughs:
        left_peaks = [p for p in raw_peaks if p['idx'] < t['idx']]
        right_peaks = [p for p in raw_peaks if p['idx'] > t['idx']]
        nearest_price = None
        if left_peaks:
            nearest_price = left_peaks[-1]['price']
        if right_peaks and (nearest_price is None or right_peaks[0]['price'] < nearest_price):
            nearest_price = right_peaks[0]['price']
        if nearest_price is not None and (nearest_price - t['price']) / nearest_price >= prominence:
            troughs.append(t)

    return peaks, troughs


def find_highest_peak_before(peaks, trough_idx, lookback_days=60):
    candidates = [p for p in peaks if p['idx'] < trough_idx and (trough_idx - p['idx']) <= lookback_days]
    return max(candidates, key=lambda x: x['price']) if candidates else None


def find_highest_peak_after(peaks, trough_idx, lookahead_days=60):
    candidates = [p for p in peaks if p['idx'] > trough_idx and (p['idx'] - trough_idx) <= lookahead_days]
    return max(candidates, key=lambda x: x['price']) if candidates else None


def find_highest_peak_between(peaks, left_idx, right_idx):
    candidates = [p for p in peaks if left_idx < p['idx'] < right_idx]
    return max(candidates, key=lambda x: x['price']) if candidates else None
