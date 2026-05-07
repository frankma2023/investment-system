"""
src/analysis/financial.py — 财务分析引擎

四大模块:
  1. DCF估值: 自由现金流折现 → 目标价
  2. 可比公司分析 (Comps): 同行业倍数比较 → 估值区间
  3. 盈利趋势分析 (Earnings): 季度盈利变化 → 趋势判断
  4. 三表联动预测 (3-Statement): IS→BS→CF 推导

数据源: stock_financials_annual, stock_financials_quarterly,
        fundamental_indicator, stock_sw_industry
"""

import sqlite3
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "lixinger.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ═══════════════════════════════════════════
# 1. DCF 估值模型
# ═══════════════════════════════════════════

def dcf_valuation(stock_code, assumptions=None):
    """
    简化DCF估值。基于最近年报数据，预测5年自由现金流，折现到企业价值。

    Args:
        stock_code: 股票代码
        assumptions: {
            growth_rates: [0.12, 0.10, 0.08, 0.06, 0.05],  # 5年营收增长率
            ebitda_margin: None,      # None=用历史毛利率近似
            tax_rate: 0.25,
            da_pct: 0.03,             # D&A占营收比
            capex_pct: 0.05,          # CapEx占营收比
            nwc_pct: 0.01,            # NWC变动占增量营收比
            wacc: 0.10,               # 加权平均资本成本
            terminal_g: 0.025,        # 永续增长率
            projection_years: 5
        }
    Returns: dict with enterprise_value, equity_value, target_price, sensitivity
    """
    db = get_db()

    # 默认假设
    if assumptions is None:
        assumptions = {}
    g = assumptions.get('growth_rates', [0.12, 0.10, 0.08, 0.06, 0.05])
    tax = assumptions.get('tax_rate', 0.25)
    da_pct = assumptions.get('da_pct', 0.03)
    capex_pct = assumptions.get('capex_pct', 0.05)
    nwc_pct = assumptions.get('nwc_pct', 0.01)
    wacc = assumptions.get('wacc', 0.10)
    t_g = assumptions.get('terminal_g', 0.025)

    # 取最近年报
    annual = db.execute('''SELECT * FROM stock_financials_annual
        WHERE stock_code = ? ORDER BY report_date DESC LIMIT 1''',
        (stock_code,)).fetchone()

    if not annual:
        db.close()
        return {'error': f'{stock_code} 无年报数据'}

    revenue = annual['revenue'] or 0
    gross_margin = (annual['gross_margin'] or 20) / 100.0
    if revenue <= 0:
        db.close()
        return {'error': f'{stock_code} 营收数据异常'}

    # EBITDA估计 = 营收 × EBITDA利润率（用毛利率近似，扣除SG&A约5%）
    ebitda_margin = assumptions.get('ebitda_margin', gross_margin - 0.05)

    # 取最新市值和净债务
    funda = db.execute('''SELECT value FROM fundamental_indicator
        WHERE stock_code = ? AND metric_code = 'mc'
        ORDER BY date DESC LIMIT 1''', (stock_code,)).fetchone()
    market_cap = funda['value'] if funda else 0

    asset_ratio = (annual['asset_liability_ratio'] or 40) / 100.0
    net_debt = market_cap * 0.15  # 简化：净债务≈市值的15%

    # ── FCF预测 ──
    rev = revenue
    pv_fcfs = []
    fcf_details = []
    for yr in range(len(g)):
        rev = rev * (1 + g[yr])
        ebitda = rev * ebitda_margin
        da = rev * da_pct
        ebit = ebitda - da
        nopat = ebit * (1 - tax)
        capex = rev * capex_pct
        prev_rev = rev / (1 + g[yr])
        dnwc = (rev - prev_rev) * nwc_pct
        ufcf = nopat + da - capex - dnwc
        period = yr + 0.5
        pv = ufcf / ((1 + wacc) ** period)
        pv_fcfs.append(pv)
        fcf_details.append({'year': yr + 1, 'revenue': round(rev, 1), 'ufcf': round(ufcf, 1), 'pv': round(pv, 1)})

    last_fcf = fcf_details[-1]['ufcf']
    tv = last_fcf * (1 + t_g) / (wacc - t_g)
    pv_tv = tv / ((1 + wacc) ** (len(g) + 0.5))
    enterprise_value = sum(pv_fcfs) + pv_tv
    equity_value = enterprise_value - net_debt

    # 股票名称
    info = db.execute('SELECT name FROM stock_basic WHERE stock_code=?',
                      (stock_code,)).fetchone()
    name = info['name'] if info else stock_code

    # 估算股本
    pe_row = db.execute('''SELECT value FROM fundamental_indicator
        WHERE stock_code = ? AND metric_code = 'pe_ttm'
        ORDER BY date DESC LIMIT 1''', (stock_code,)).fetchone()
    pe = pe_row['value'] if pe_row else 20

    price_row = db.execute('''SELECT value FROM fundamental_indicator
        WHERE stock_code = ? AND metric_code = 'sp'
        ORDER BY date DESC LIMIT 1''', (stock_code,)).fetchone()
    current_price = price_row['value'] if price_row else (market_cap / 1000 if market_cap > 0 else 10)
    shares = market_cap / current_price if current_price > 0 else 10000
    target_price = equity_value / shares if shares > 0 else 0
    db.close()

    # 敏感性分析
    sensitivity = []
    for w in [0.08, 0.09, 0.10, 0.11, 0.12]:
        ev = sum(ufcf / ((1 + w) ** (yr + 0.5)) for yr, ufcf in enumerate(
            [d['ufcf'] for d in fcf_details]))
        tv_s = last_fcf * (1 + t_g) / (w - t_g)
        ev += tv_s / ((1 + w) ** (len(g) + 0.5))
        tp = (ev - net_debt) / shares if shares > 0 else 0
        sensitivity.append({'wacc': f'{w*100:.0f}%', 'target_price': round(tp, 2)})

    return {
        'stock_code': stock_code,
        'name': name,
        'method': 'DCF',
        'current_price': round(current_price, 2),
        'base_revenue': round(revenue, 1),
        'ebitda_margin': f'{ebitda_margin*100:.1f}%',
        'wacc': f'{wacc*100:.0f}%',
        'terminal_growth': f'{t_g*100:.1f}%',
        'projections': fcf_details,
        'terminal_value': round(pv_tv, 1),
        'enterprise_value': round(enterprise_value, 1),
        'equity_value': round(equity_value, 1),
        'target_price': round(target_price, 2),
        'upside_pct': round((target_price/current_price - 1) * 100, 1) if current_price > 0 else None,
        'sensitivity': sensitivity,
    }


# ═══════════════════════════════════════════
# 2. 可比公司分析 (Comps)
# ═══════════════════════════════════════════

def comps_analysis(stock_code, peer_codes=None):
    """
    可比公司估值。在同行业中找可比公司，用中位数倍数估值。

    Args:
        stock_code: 目标股票代码
        peer_codes: 可比公司列表(None=自动找同行业)
    """
    db = get_db()

    # 获取目标公司行业
    industry = db.execute('''SELECT industry_name FROM stock_sw_industry
        WHERE stock_code = ?''', (stock_code,)).fetchone()

    if not industry:
        db.close()
        return {'error': f'{stock_code} 无行业分类'}

    ind_name = industry['industry_name']

    # 自动找同行业公司
    if not peer_codes:
        peers = db.execute('''SELECT stock_code FROM stock_sw_industry
            WHERE industry_name = ? AND stock_code != ?
            LIMIT 20''', (ind_name, stock_code)).fetchall()
        peer_codes = [p['stock_code'] for p in peers]

    if not peer_codes:
        db.close()
        return {'error': f'{ind_name} 行业无可比公司'}

    # 收集所有公司（目标+可比）的财务数据
    all_codes = [stock_code] + peer_codes
    ph = ','.join(['?' for _ in all_codes])

    # 最近年报数据
    annuals = db.execute(f'''SELECT stock_code, revenue, revenue_yoy, gross_margin,
        roe, net_profit, asset_liability_ratio
        FROM stock_financials_annual WHERE stock_code IN ({ph})
        ORDER BY report_date DESC''',
        all_codes).fetchall()

    # 去重（每个股票只取最新）
    seen_codes = set()
    ann_data = {}
    for a in annuals:
        if a['stock_code'] not in seen_codes:
            seen_codes.add(a['stock_code'])
            ann_data[a['stock_code']] = a

    # 估值倍数
    multiples = db.execute(f'''SELECT stock_code, metric_code, value
        FROM fundamental_indicator WHERE stock_code IN ({ph})
        AND metric_code IN ('pe_ttm', 'pb', 'ps_ttm', 'mc')
        AND date >= date('now', '-30 days')
        ORDER BY date DESC''',
        all_codes).fetchall()

    mult_data = {}
    for m in multiples:
        if m['stock_code'] not in mult_data:
            mult_data[m['stock_code']] = {}
        if m['metric_code'] not in mult_data[m['stock_code']]:
            mult_data[m['stock_code']][m['metric_code']] = m['value']

    # 名称
    names = db.execute(f'''SELECT stock_code, name FROM stock_basic
        WHERE stock_code IN ({ph})''', all_codes).fetchall()
    name_map = {n['stock_code']: n['name'] for n in names}
    db.close()

    # 构建可比表格
    def get_metric(code, mkey, fmt='.1f'):
        v = mult_data.get(code, {}).get(mkey)
        return round(v, 1) if v else None

    peers_table = []
    pe_vals, pb_vals, ps_vals, rev_growth_vals, roe_vals = [], [], [], [], []

    for code in all_codes:
        a = ann_data.get(code, {})
        pe = get_metric(code, 'pe_ttm')
        pb = get_metric(code, 'pb')
        ps = get_metric(code, 'ps_ttm')
        rg = a.get('revenue_yoy')
        roe_val = a.get('roe')

        row = {
            'code': code, 'name': name_map.get(code, code),
            'revenue': round(a.get('revenue', 0) or 0, 1),
            'revenue_growth': round(rg, 1) if rg else None,
            'gross_margin': round(a.get('gross_margin', 0) or 0, 1),
            'roe': round(roe_val, 1) if roe_val else None,
            'pe': pe, 'pb': pb, 'ps': ps,
        }
        peers_table.append(row)

        if code != stock_code:
            if pe: pe_vals.append(pe)
            if pb: pb_vals.append(pb)
            if ps: ps_vals.append(ps)
            if rg: rev_growth_vals.append(rg)
            if roe_val: roe_vals.append(roe_val)

    # 中位数统计
    def median(vals):
        if not vals: return None
        sv = sorted(vals)
        n = len(sv)
        return sv[n // 2] if n % 2 else (sv[n // 2 - 1] + sv[n // 2]) / 2

    med_pe = median(pe_vals)
    med_pb = median(pb_vals)
    med_ps = median(ps_vals)

    # 目标公司数据
    target = peers_table[0] if peers_table else {}
    target_revenue = target.get('revenue', 0)
    target_equity = target_revenue * 0.3  # 简化：净资产≈营收×30%

    # 估值
    valuations = {}
    if med_pe and target.get('net_profit'):
        np = ann_data.get(stock_code, {}).get('net_profit', 0) or 0
        if np > 0:
            valuations['PE法'] = round(med_pe * np / 10000, 1)  # 亿
    if med_pb:
        valuations['PB法'] = round(med_pb * target_equity / 10000, 1)
    if med_ps and target_revenue > 0:
        valuations['PS法'] = round(med_ps * target_revenue / 10000, 1)

    avg_val = sum(valuations.values()) / len(valuations) if valuations else 0

    return {
        'stock_code': stock_code,
        'name': name_map.get(stock_code, stock_code),
        'industry': ind_name,
        'method': 'Comparable Company Analysis',
        'peer_count': len(peer_codes),
        'peers': peers_table,
        'median_multiples': {'pe': round(med_pe, 1) if med_pe else None,
                             'pb': round(med_pb, 1) if med_pb else None,
                             'ps': round(med_ps, 1) if med_ps else None},
        'implied_valuations': valuations,
        'average_valuation': round(avg_val, 1),
    }


# ═══════════════════════════════════════════
# 3. 盈利趋势分析 (Earnings Analysis)
# ═══════════════════════════════════════════

def earnings_analysis(stock_code, quarters=8):
    """
    季度盈利趋势分析。分析近N个季度的营收/净利变化。

    Returns: dict with trends, surprises, acceleration detection
    """
    db = get_db()

    # 季度数据
    rows = db.execute('''SELECT * FROM stock_financials_quarterly
        WHERE stock_code = ? ORDER BY report_date DESC LIMIT ?''',
        (stock_code, quarters)).fetchall()

    if not rows:
        db.close()
        return {'error': f'{stock_code} 无季度财务数据'}

    name_row = db.execute('SELECT name FROM stock_basic WHERE stock_code=?',
                          (stock_code,)).fetchone()
    name = name_row['name'] if name_row else stock_code
    db.close()

    quarters_data = []
    for r in reversed(rows):  # 从旧到新
        quarters_data.append({
            'report_date': r['report_date'],
            'revenue': round(r['revenue_single'] or 0, 1),
            'revenue_yoy': round(r['revenue_yoy'] or 0, 1),
            'revenue_qoq': round(r['revenue_qoq'] or 0, 1),
            'net_profit': round(r['net_profit_single'] or 0, 1),
            'net_profit_yoy': round(r['net_profit_yoy'] or 0, 1),
            'net_profit_qoq': round(r['net_profit_qoq'] or 0, 1),
            'gross_margin': round(r['gross_margin_single'] or 0, 1),
            'roe': round(r['roe_single'] or 0, 1),
        })

    if len(quarters_data) < 3:
        return {'error': f'{stock_code} 季度数据不足(需≥3)', 'quarters': quarters_data}

    # 趋势判断
    recent = quarters_data[-3:]  # 最近3个季度
    rev_trend = [q['revenue_yoy'] for q in recent]
    np_trend = [q['net_profit_yoy'] for q in recent]

    # 加速/减速判断
    rev_accel = rev_trend[-1] - rev_trend[0] if len(rev_trend) >= 2 else 0
    np_accel = np_trend[-1] - np_trend[0] if len(np_trend) >= 2 else 0

    # 盈利质量
    last = quarters_data[-1]
    margin_trend = [q['gross_margin'] for q in recent]

    if rev_accel > 5 and np_accel > 5:
        trend = '强劲增长 · 营收净利双加速'
    elif rev_accel > 0 and np_accel > 0:
        trend = '温和增长 · 趋势向好'
    elif rev_accel < -5 and np_accel < -5:
        trend = '明显减速 · 关注拐点'
    elif rev_accel < 0:
        trend = '增速放缓 · 营收先于净利减速'
    else:
        trend = '趋势分化 · 需进一步分析'

    return {
        'stock_code': stock_code,
        'name': name,
        'method': 'Earnings Trend Analysis',
        'quarters': quarters_data,
        'revenue_trend': rev_trend,
        'profit_trend': np_trend,
        'revenue_acceleration': round(rev_accel, 1),
        'profit_acceleration': round(np_accel, 1),
        'margin_trend': margin_trend,
        'trend_summary': trend,
        'latest': {
            'revenue_yoy': last['revenue_yoy'],
            'net_profit_yoy': last['net_profit_yoy'],
            'gross_margin': last['gross_margin'],
            'roe': last['roe'],
        }
    }


# ═══════════════════════════════════════════
# 4. 三表联动预测 (简化版)
# ═══════════════════════════════════════════

def three_statement_projection(stock_code, assumptions=None):
    """
    三表联动预测：基于最近年报，推导利润表→资产负债表→现金流量表。

    Args:
        assumptions: {
            growth_rates: [0.12, 0.10, 0.08],  # 3年营收增长率
            gross_margin: None,    # None=用历史值
            tax_rate: 0.25,
            da_pct: 0.03,
            capex_pct: 0.05,
            nwc_pct: 0.12,        # NWC占营收的%
        }
    """
    db = get_db()

    if assumptions is None:
        assumptions = {}
    g_list = assumptions.get('growth_rates', [0.12, 0.10, 0.08])
    tax = assumptions.get('tax_rate', 0.25)
    da_pct = assumptions.get('da_pct', 0.03)
    capex_pct = assumptions.get('capex_pct', 0.05)
    nwc_pct = assumptions.get('nwc_pct', 0.12)

    annual = db.execute('''SELECT * FROM stock_financials_annual
        WHERE stock_code = ? ORDER BY report_date DESC LIMIT 1''',
        (stock_code,)).fetchone()

    if not annual:
        db.close()
        return {'error': f'{stock_code} 无年报数据'}

    name_row = db.execute('SELECT name FROM stock_basic WHERE stock_code=?',
                          (stock_code,)).fetchone()
    name = name_row['name'] if name_row else stock_code
    db.close()

    base_revenue = annual['revenue'] or 0
    gm = (annual['gross_margin'] or 30) / 100.0
    gm = assumptions.get('gross_margin', gm)

    if base_revenue <= 0:
        return {'error': '营收数据异常'}

    projections = []
    rev = base_revenue

    for yr, g in enumerate(g_list):
        rev = rev * (1 + g)
        gross_profit = rev * gm
        sga = rev * 0.08  # SG&A≈营收8%
        da = rev * da_pct
        ebit = gross_profit - sga - da
        interest = rev * 0.01  # 简化利息
        pretax = ebit - interest
        net_income = pretax * (1 - tax)

        # 资产负债表
        nwc = rev * nwc_pct
        capex = rev * capex_pct

        # 现金流量表
        ocf = net_income + da  # 简化：OCF≈净利+D&A
        fcf = ocf - capex

        projections.append({
            'year': yr + 1,
            'income_statement': {
                'revenue': round(rev, 1),
                'gross_profit': round(gross_profit, 1),
                'ebit': round(ebit, 1),
                'net_income': round(net_income, 1),
                'gross_margin': f'{gm*100:.1f}%',
                'net_margin': f'{net_income/rev*100:.1f}%' if rev > 0 else 'N/A',
            },
            'balance_sheet': {
                'nwc': round(nwc, 1),
                'capex': round(capex, 1),
            },
            'cash_flow': {
                'operating_cf': round(ocf, 1),
                'free_cf': round(fcf, 1),
            }
        })

    return {
        'stock_code': stock_code,
        'name': name,
        'method': '3-Statement Projection',
        'base_revenue': round(base_revenue, 1),
        'base_gross_margin': f'{gm*100:.1f}%',
        'projections': projections,
    }


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

if __name__ == '__main__':
    import sys, json

    if len(sys.argv) < 3:
        print("用法: python financial.py <method> <stock_code>")
        print("  method: dcf | comps | earnings | model")
        sys.exit(1)

    method = sys.argv[1]
    code = sys.argv[2]

    if method == 'dcf':
        result = dcf_valuation(code)
    elif method == 'comps':
        result = comps_analysis(code)
    elif method == 'earnings':
        result = earnings_analysis(code)
    elif method == 'model':
        result = three_statement_projection(code)
    else:
        print(f"未知方法: {method}")
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
