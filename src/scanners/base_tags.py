"""
Layer 2 形态标注器集合

对每条 Layer 1 基部突破信号，标注其形态特征得分（0~1）。
不参与过滤——只提供信息，由用户按得分自主筛选。

标注器:
  - vcp_score: VCP 波动收缩形态
  - (未来) cup_handle_score, saucer_score, double_bottom_score, ...
"""

from typing import Dict, List, Optional

# ─── VCP 默认参数 ──────────────────────────────────────

VCP_DEFAULTS = {
    'vcp_min_toc': 2,             # 最少 TOC 次数
    'vcp_max_toc': 4,             # 最多 TOC 次数
    'vcp_contraction_ratio': 0.80, # 振幅收缩率（本轮/上轮 ≤ 此值）
    'vcp_vol_contraction': 0.85,   # 量收缩率（本轮/上轮 ≤ 此值）
    'vcp_terminal_amp': 0.08,      # 末端振幅上限
    'vcp_dryup_ratio': 0.50,       # 末端量干涸阈值（/50均量）
    'vcp_peak_tolerance': 0.02,    # 波峰降低容忍（允许略高 %）
    'vcp_trough_tolerance': 0.02,  # 波谷抬高容忍（允许略低 %）
    'vcp_local_window': 5,         # 局部极值检测窗口
}


def _local_peak_indices(closes: List[float], window: int) -> List[int]:
    """找局部波峰（高点）的索引列表"""
    n = len(closes)
    peaks = []
    for i in range(n):
        lo = max(0, i - window)
        hi = min(n - 1, i + window)
        if closes[i] == max(closes[lo:hi + 1]):
            # 去重：相邻相同值只保留第一个
            if not peaks or i - peaks[-1] > window:
                peaks.append(i)
    return peaks


def _local_trough_indices(closes: List[float], window: int) -> List[int]:
    """找局部波谷（低点）的索引列表"""
    n = len(closes)
    troughs = []
    for i in range(n):
        lo = max(0, i - window)
        hi = min(n - 1, i + window)
        if closes[i] == min(closes[lo:hi + 1]):
            if not troughs or i - troughs[-1] > window:
                troughs.append(i)
    return troughs


def vcp_score(
    daily: List[Dict],
    signal: Dict,
    params: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    VCP 波动收缩形态评分

    在 [prior_high_idx, t_idx] 区间内，识别 TOC（回调段），
    验证振幅逐次收缩、波峰逐次降低、量逐次萎缩、末端干燥。

    Returns:
        {'score': 0.0~1.0, 'toc_count': 3, 'details': {...}} or None
    """
    if params is None:
        params = {}
    vp = {**VCP_DEFAULTS, **params}

    # 解析信号中的索引
    t_date = signal['signal_date']
    prior_high_date = signal.get('prior_high_date', '')
    trough_date = signal.get('trough_date', '')

    # 找对应索引
    dates = [k['date'] for k in daily]
    prior_high_idx = None
    trough_idx = None
    t_idx = None
    for i, d in enumerate(dates):
        if d == prior_high_date:
            prior_high_idx = i
        if d == trough_date:
            trough_idx = i
        if d == t_date:
            t_idx = i

    if prior_high_idx is None or t_idx is None:
        return None

    closes = [k['close'] for k in daily]
    volumes = [k['volume'] for k in daily]

    win = vp['vcp_local_window']

    # ── 在 [prior_high_idx, t_idx] 内找波峰和波谷 ──
    zone = closes[prior_high_idx:t_idx + 1]
    if len(zone) < 20:
        return {'score': 0.0, 'toc_count': 0, 'details': {'error': '区间太短 (< 20 天)'}}

    zone_peaks = _local_peak_indices(zone, win)
    zone_troughs = _local_trough_indices(zone, win)

    # 合并排序所有极值点
    all_extrema = sorted(set(zone_peaks + zone_troughs))

    if len(all_extrema) < 4:
        return {'score': 0.0, 'toc_count': 0, 'details': {'error': '极值点不足 (< 4)'}}

    # ── 构建 TOC 段（波峰 → 波谷 → 波峰 → ...）──
    # 每个 TOC 含: (peak_idx, trough_idx, next_peak_idx)
    tocs = []
    i = 0
    while i < len(all_extrema) - 2:
        p_idx = all_extrema[i]
        t_idx_rel = all_extrema[i + 1]
        np_idx = all_extrema[i + 2]

        if zone[t_idx_rel] >= zone[p_idx]:
            i += 1
            continue

        # 回调深度 ≥ 3%，才算有效的 TOC
        dd = (zone[p_idx] - zone[t_idx_rel]) / zone[p_idx]
        if dd < 0.03:
            i += 1
            continue

        tocs.append({
            'peak_idx': p_idx,
            'trough_idx': t_idx_rel,
            'next_peak_idx': np_idx,
            'drawdown': dd,
            'amplitude': (zone[p_idx] - zone[t_idx_rel]) / zone[t_idx_rel] if zone[t_idx_rel] > 0 else 0,
        })
        i += 2

    if len(tocs) < vp['vcp_min_toc']:
        return {'score': 0.0, 'toc_count': len(tocs),
                'details': {'error': f'TOC 次数不足 ({len(tocs)} < {vp["vcp_min_toc"]})'}}

    if len(tocs) > vp['vcp_max_toc']:
        tocs = tocs[:vp['vcp_max_toc']]

    # ── 4 项检查 ──
    score_detail = {}
    total_score = 0.0

    # 1. 波峰逐次降低
    peak_drop_ok = True
    peak_drops = []
    for j in range(len(tocs) - 1):
        pk1 = zone[tocs[j]['peak_idx']]
        pk2 = zone[tocs[j + 1]['peak_idx']]
        ok = pk2 <= pk1 * (1 + vp['vcp_peak_tolerance'])
        peak_drops.append({'from': round(pk1, 2), 'to': round(pk2, 2), 'ok': ok})
        if not ok:
            peak_drop_ok = False
    if peak_drop_ok and len(peak_drops) >= 1:
        total_score += 0.20
    score_detail['peak_drop'] = {'ok': peak_drop_ok, 'drops': peak_drops}

    # 2. 振幅逐次收缩
    amp_contract_ok = True
    contractions = []
    for j in range(len(tocs) - 1):
        a1 = tocs[j]['amplitude']
        a2 = tocs[j + 1]['amplitude']
        ratio = a2 / a1 if a1 > 0 else 1.0
        ok = ratio <= vp['vcp_contraction_ratio']
        contractions.append({'amp1': round(a1 * 100, 1), 'amp2': round(a2 * 100, 1),
                             'ratio': round(ratio, 2), 'ok': ok})
        if not ok:
            amp_contract_ok = False
    if amp_contract_ok and len(contractions) >= 1:
        total_score += 0.30
    score_detail['amp_contraction'] = {'ok': amp_contract_ok, 'contractions': contractions}

    # 3. 成交量逐次萎缩
    vol_daily = volumes[prior_high_idx:t_idx + 1]
    vol_contract_ok = True
    vol_ratios = []
    for j in range(len(tocs)):
        start = max(0, tocs[j]['peak_idx'])
        end = min(len(vol_daily), tocs[j].get('next_peak_idx', tocs[j]['trough_idx']) + 1)
        seg_vols = vol_daily[start:end]
        seg_avg = sum(seg_vols) / len(seg_vols) if seg_vols else 0
        tocs[j]['vol_avg'] = seg_avg

    for j in range(len(tocs) - 1):
        ratio = tocs[j + 1]['vol_avg'] / tocs[j]['vol_avg'] if tocs[j]['vol_avg'] > 0 else 1.0
        ok = ratio <= vp['vcp_vol_contraction']
        vol_ratios.append({'vol1': int(tocs[j]['vol_avg']), 'vol2': int(tocs[j + 1]['vol_avg']),
                           'ratio': round(ratio, 2), 'ok': ok})
        if not ok:
            vol_contract_ok = False
    if vol_contract_ok and len(vol_ratios) >= 1:
        total_score += 0.20
    score_detail['vol_contraction'] = {'ok': vol_contract_ok, 'ratios': vol_ratios}

    # 4. 末端收缩 + 干涸
    last_toc = tocs[-1]
    terminal_amp = last_toc['amplitude']
    term_amp_ok = terminal_amp <= vp['vcp_terminal_amp']

    # 末端量 / 50日均量
    if trough_idx is not None:
        vol_50_before = sum(volumes[max(0, t_idx - 50):t_idx]) / min(50, t_idx)
        term_vol_ratio = last_toc['vol_avg'] / vol_50_before if vol_50_before > 0 else 1.0
    else:
        term_vol_ratio = 1.0
    term_dry_ok = term_vol_ratio <= vp['vcp_dryup_ratio']

    score_detail['terminal'] = {
        'ok': term_amp_ok and term_dry_ok,
        'amp': round(terminal_amp * 100, 1),
        'amp_ok': term_amp_ok,
        'vol_ratio': round(term_vol_ratio, 2),
        'dry_ok': term_dry_ok,
    }

    if term_amp_ok:
        total_score += 0.15
    if term_dry_ok:
        total_score += 0.15

    # ── TOC 次数加分 ──
    if len(tocs) == 3:
        total_score += 0.05  # 3-C 最优
    elif len(tocs) == 4:
        total_score += 0.03

    return {
        'score': min(total_score, 1.0),
        'toc_count': len(tocs),
        'details': score_detail,
    }


def tag_signal(
    daily: List[Dict],
    signal: Dict,
    vcp_params: Optional[Dict] = None,
) -> Dict:
    """
    Layer 2 标注入口：对一条信号运行所有标注器。

    Args:
        daily: 日线数据
        signal: 单条 Layer 1 信号（含 prior_high_date, trough_date, signal_date）
        vcp_params: VCP 参数覆盖

    Returns:
        {'vcp': {'score': 0.88, ...}, 'cup_handle': None, ...}
    """
    tags = {
        'vcp': vcp_score(daily, signal, vcp_params),
        # 未来:
        # 'cup_handle': cup_handle_score(daily, signal),
        # 'saucer': saucer_score(daily, signal),
        # 'double_bottom': double_bottom_score(daily, signal),
        # 'flat_base': flat_base_score(daily, signal),
        # 'box': box_score(daily, signal),
        # 'htf': htf_score(daily, signal),
    }
    return tags
