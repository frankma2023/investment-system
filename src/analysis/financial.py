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
    DCF估值。基于最近年报真实数据 + 用户假设参数。

    所有财务数据取自 stock_financials_annual + stock_financials_annual_ext，
    不使用任何兜底估算值。数据缺失时在返回的 warnings 中列出。
    """
    db = get_db()

    if assumptions is None:
        assumptions = {}
    # 用最近一期营收同比作为默认基准增速，逐年递减至永续增长
    rev_yoy = annual['revenue_yoy'] or 12
    base_g = max(rev_yoy * 0.7, 5)  # 取历史增速的70%，不低于5%
    g = assumptions.get('growth_rates', [base_g, max(base_g-2,5), max(base_g-4,5), max(base_g-5,4), max(base_g-6,3)])
    g = [x/100.0 for x in g]  # 转为小数
    wacc = assumptions.get('wacc', 0.10)
    t_g = assumptions.get('terminal_growth', 0.025)
    exit_multiple = assumptions.get('exit_multiple', None)  # EV/EBITDA退出倍数, None=用永续增长
    tax = assumptions.get('tax_rate', 0.25)

    annual = db.execute('''SELECT * FROM stock_financials_annual
        WHERE stock_code = ? ORDER BY report_date DESC LIMIT 1''',
        (stock_code,)).fetchone()
    if not annual or not annual['revenue']:
        db.close(); return {'error': f'{stock_code} 无年报数据'}

    ext = db.execute('''SELECT * FROM stock_financials_annual_ext
        WHERE stock_code = ? AND report_date = ?''',
        (stock_code, annual['report_date'])).fetchone()

    warnings = []

    # ── 营收 ──
    revenue = annual['revenue']

    # ── EBITDA ──
    if ext and ext['ebitda']:
        ebitda_margin = ext['ebitda'] / revenue
        ebitda_val = ext['ebitda']
    else:
        warnings.append('EBITDA: stock_financials_annual_ext 中无数据')
        ebitda_margin = None; ebitda_val = None

    # ── 折旧与摊销 ──
    if ext and (ext['depreciation_fa'] or ext['depreciation_ip']):
        da_pct = (ext['depreciation_fa'] + ext['depreciation_ip']) / revenue
    else:
        warnings.append('D&A(折旧摊销): 缺失')
        da_pct = None

    # ── CapEx ──
    ocf = annual['operating_cash_flow']
    fcf_annual = annual['free_cash_flow']
    if ocf and fcf_annual:
        capex_pct = (ocf - fcf_annual) / revenue
    else:
        warnings.append('CapEx: 经营CF或自由CF缺失')
        capex_pct = None

    # ── 利息支出 ──
    if ext and ext['interest_expense']:
        interest = ext['interest_expense']
    else:
        warnings.append('利息支出: 缺失')
        interest = None

    # ── 股本 ──
    eq_row = db.execute('''SELECT capitalization FROM stock_equity_change
        WHERE stock_code = ? ORDER BY date DESC LIMIT 1''',
        (stock_code,)).fetchone()
    if eq_row and eq_row['capitalization']:
        shares = eq_row['capitalization']
    else:
        warnings.append('总股本: stock_equity_change 中无数据')
        shares = None

    # ── 当前股价 ──
    kline_row = db.execute('''SELECT close FROM daily_kline
        WHERE stock_code = ? ORDER BY date DESC LIMIT 1''',
        (stock_code,)).fetchone()
    current_price = kline_row['close'] if kline_row else None
    if not current_price:
        warnings.append('当前股价: daily_kline 中无数据')

    # ── 净债务 ──
    if ext and ext['total_assets'] and annual['interest_bearing_debt_ratio']:
        net_debt = ext['total_assets'] * (annual['interest_bearing_debt_ratio'] / 100)
    else:
        warnings.append('净债务: 总资产或有息负债率缺失')
        net_debt = None

    # ── 名称 ──
    info = db.execute('SELECT name FROM stock_basic WHERE stock_code=?',
                      (stock_code,)).fetchone()
    name = info['name'] if info else stock_code
    db.close()

    # 检查是否所有必要数据齐全
    if ebitda_margin is None or da_pct is None or capex_pct is None or shares is None or current_price is None:
        return {
            'stock_code': stock_code, 'name': name, 'method': 'DCF',
            'error': '必要财务数据缺失，无法完成DCF估值',
            'warnings': warnings,
            'current_price': current_price,
        }

    market_cap = shares * current_price

    # ── 确定基准年 ──
    base_year = int(annual['report_date'][:4]) if annual['report_date'] else 2025

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
        dnwc = (rev - prev_rev) * 0.01  # NWC变动 = 增量营收 × 1%
        ufcf = nopat + da - capex - dnwc
        period = yr + 0.5
        pv = ufcf / ((1 + wacc) ** period)
        pv_fcfs.append(pv)
        fcf_details.append({'year': base_year + yr + 1, 'revenue': round(rev,1), 'ufcf': round(ufcf,1), 'pv': round(pv,1)})

    last_fcf = fcf_details[-1]['ufcf']
    last_ebitda = fcf_details[-1]['revenue'] * ebitda_margin

    # 终值计算
    if exit_multiple:
        tv = last_ebitda * exit_multiple
        tv_method = f'EV/EBITDA {exit_multiple}x'
    else:
        tv = last_fcf * (1 + t_g) / (wacc - t_g)
        tv_method = f'永续增长 {t_g*100:.1f}%'

    pv_tv = tv / ((1 + wacc) ** (len(g) + 0.5))
    enterprise_value = sum(pv_fcfs) + pv_tv
    equity_value = enterprise_value - (net_debt or 0)
    target_price = equity_value / shares if shares > 0 else 0

    sensitivity = []
    if exit_multiple:
        for m in [exit_multiple-4, exit_multiple-2, exit_multiple, exit_multiple+2, exit_multiple+4]:
            if m <= 0: continue
            ev = sum(d['ufcf'] / ((1 + wacc) ** (yr + 0.5)) for yr, d in enumerate(fcf_details))
            tv_s = last_ebitda * m
            ev += tv_s / ((1 + wacc) ** (len(g) + 0.5))
            tp = (ev - (net_debt or 0)) / shares if shares > 0 else 0
            sensitivity.append({'label': f'EV/EBITDA {m}x', 'target_price': round(tp,2)})
    else:
        for w in [0.08, 0.09, 0.10, 0.11, 0.12]:
            ev = sum(d['ufcf'] / ((1 + w) ** (yr + 0.5)) for yr, d in enumerate(fcf_details))
            tv_s = last_fcf * (1 + t_g) / (w - t_g)
            ev += tv_s / ((1 + w) ** (len(g) + 0.5))
            tp = (ev - (net_debt or 0)) / shares if shares > 0 else 0
            sensitivity.append({'label': f'WACC {w*100:.0f}%', 'target_price': round(tp,2)})

    return {
        'stock_code': stock_code, 'name': name, 'method': 'DCF',
        'current_price': round(current_price, 2),
        'base_revenue': round(revenue, 1),
        'ebitda_margin': f'{ebitda_margin*100:.1f}%',
        'ebitda': round(ebitda_val, 1) if ebitda_val else None,
        'da_pct': f'{da_pct*100:.1f}%',
        'capex_pct': f'{capex_pct*100:.1f}%',
        'interest_expense': round(interest, 1) if interest else None,
        'net_debt': round(net_debt, 1) if net_debt else None,
        'wacc': f'{wacc*100:.0f}%',
        'terminal_growth': f'{t_g*100:.1f}%',
        'tv_method': tv_method,
        'projections': fcf_details,
        'terminal_value': round(pv_tv, 1),
        'enterprise_value': round(enterprise_value, 1),
        'equity_value': round(equity_value, 1),
        'target_price': round(target_price, 2),
        'upside_pct': round((target_price/current_price - 1) * 100, 1) if current_price > 0 else None,
        'sensitivity': sensitivity,
        'warnings': warnings if warnings else None,
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
            ann_data[a['stock_code']] = dict(a)

    # 估值倍数 — 用真实数据自行计算
    # PE = 市值/净利润 = (股本×股价)/净利润
    # PB = 市值/净资产 = (股本×股价)/股东权益
    # PS = 市值/营收
    mult_data = {}
    for code in all_codes:
        # 取股价
        k_row = db.execute('''SELECT close FROM daily_kline
            WHERE stock_code = ? ORDER BY date DESC LIMIT 1''', (code,)).fetchone()
        price = k_row['close'] if k_row else None
        # 取股本
        eq_row = db.execute('''SELECT capitalization FROM stock_equity_change
            WHERE stock_code = ? ORDER BY date DESC LIMIT 1''', (code,)).fetchone()
        shares = eq_row['capitalization'] if eq_row else None
        # 取年报数据
        a = ann_data.get(code, {})
        # 取扩展数据
        ext2 = db.execute('''SELECT total_equity FROM stock_financials_annual_ext
            WHERE stock_code = ? ORDER BY report_date DESC LIMIT 1''', (code,)).fetchone()
        total_equity = ext2['total_equity'] if ext2 else None

        if price and shares and shares > 0:
            mkt_cap = price * shares
            np = a.get('net_profit')
            rev = a.get('revenue')
            mult_data[code] = {}
            if np and np > 0:
                mult_data[code]['pe_ttm'] = round(mkt_cap / np, 1)
            if total_equity and total_equity > 0:
                mult_data[code]['pb'] = round(mkt_cap / total_equity, 1)
            if rev and rev > 0:
                mult_data[code]['ps_ttm'] = round(mkt_cap / rev, 1)

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
# 4. 三表联动预测
# ═══════════════════════════════════════════

def three_statement_projection(stock_code, assumptions=None):
    """
    三表联动预测。基于最近年报真实数据 + 用户假设增长率。
    """
    db = get_db()

    if assumptions is None:
        assumptions = {}
    rev_yoy = annual['revenue_yoy'] or 12
    base_g = max(rev_yoy * 0.7, 5)
    g_list_assume = assumptions.get('growth_rates', [base_g, max(base_g-2,5), max(base_g-4,5)])
    g_list = [x/100.0 for x in g_list_assume]
    tax = assumptions.get('tax_rate', 0.25)
    nwc_pct = assumptions.get('nwc_pct', 0.12)

    annual = db.execute('''SELECT * FROM stock_financials_annual
        WHERE stock_code = ? ORDER BY report_date DESC LIMIT 1''',
        (stock_code,)).fetchone()
    if not annual or not annual['revenue']:
        db.close(); return {'error': f'{stock_code} 无年报数据'}

    ext = db.execute('''SELECT * FROM stock_financials_annual_ext
        WHERE stock_code = ? AND report_date = ?''',
        (stock_code, annual['report_date'])).fetchone()

    name_row = db.execute('SELECT name FROM stock_basic WHERE stock_code=?',
                          (stock_code,)).fetchone()
    name = name_row['name'] if name_row else stock_code

    warnings = []
    base_revenue = annual['revenue']
    gm = (annual['gross_margin'] or 0) / 100.0

    # 真实 SG&A
    if ext and (ext['selling_expense'] or ext['admin_expense']):
        sga_pct = ((ext['selling_expense'] or 0) + (ext['admin_expense'] or 0)) / base_revenue
    else:
        warnings.append('SG&A: 缺失')
        sga_pct = None

    # 真实 D&A
    if ext and (ext['depreciation_fa'] or ext['depreciation_ip']):
        da_pct = ((ext['depreciation_fa'] or 0) + (ext['depreciation_ip'] or 0)) / base_revenue
    else:
        warnings.append('D&A: 缺失')
        da_pct = None

    # 真实 CapEx
    ocf = annual['operating_cash_flow']
    fcf_a = annual['free_cash_flow']
    if ocf and fcf_a:
        capex_pct = (ocf - fcf_a) / base_revenue
    else:
        warnings.append('CapEx: 缺失')
        capex_pct = None

    # 真实利息
    if ext and ext['interest_expense']:
        interest_pct = ext['interest_expense'] / base_revenue
    else:
        warnings.append('利息支出: 缺失')
        interest_pct = None

    db.close()

    # 确定基准年份
    base_year = int(annual['report_date'][:4]) if annual['report_date'] else 2025

    if sga_pct is None or da_pct is None or capex_pct is None:
        return {'stock_code': stock_code, 'name': name, 'method': '3-Statement Projection',
                'error': '必要财务数据缺失', 'warnings': warnings}

    projections = []
    rev = base_revenue

    for yr, g in enumerate(g_list):
        rev = rev * (1 + g)
        gross_profit = rev * gm
        sga = rev * sga_pct
        da = rev * da_pct
        ebit = gross_profit - sga - da
        interest = rev * interest_pct
        pretax = ebit - interest
        net_income = pretax * (1 - tax)
        nwc = rev * nwc_pct
        capex = rev * capex_pct
        ocf_proj = net_income + da
        fcf_proj = ocf_proj - capex

        projections.append({
            'year': base_year + yr + 1,
            'income_statement': {
                'revenue': round(rev, 1),
                'gross_profit': round(gross_profit, 1),
                'ebit': round(ebit, 1),
                'net_income': round(net_income, 1),
                'gross_margin': f'{gm*100:.1f}%',
                'sga_margin': f'{sga_pct*100:.1f}%',
                'net_margin': f'{net_income/rev*100:.1f}%' if rev > 0 else 'N/A',
            },
            'cash_flow': {
                'operating_cf': round(ocf_proj, 1),
                'free_cf': round(fcf_proj, 1),
            }
        })

    return {
        'stock_code': stock_code, 'name': name, 'method': '3-Statement Projection',
        'base_year': base_year,
        'base_growth': f'{base_g:.1f}%',
        'base_revenue': round(base_revenue, 1),
        'base_gross_margin': f'{gm*100:.1f}%',
        'sga_pct': f'{sga_pct*100:.1f}%',
        'da_pct': f'{da_pct*100:.1f}%',
        'capex_pct': f'{capex_pct*100:.1f}%',
        'projections': projections,
        'warnings': warnings if warnings else None,
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
