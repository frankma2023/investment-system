"""
基本面恶化卖出检测引擎 v1.0

检测公司基本面是否出现恶化信号：
  - 5 项计分：EPS增速/营收增速/净利率/毛利率/ROE
  - 1 项展示：年度EPS
  - 相邻两季同比增速严格递减即触发红灯
  - 3~5 红灯=卖出，2=观察，0~1=OK

数据源: stock_financials_quarterly / stock_financials_annual
"""

import os, sqlite3
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_quarterly(code: str, limit: int = 40) -> List[Dict]:
    """拉取季度财报数据，按 report_date 升序"""
    db = _get_db()
    rows = db.execute("""
        SELECT stock_code, report_date, revenue_yoy, net_profit_adj_yoy,
               net_profit_margin, gross_margin_single, roe_single,
               net_profit_single, net_profit_adj_single
        FROM stock_financials_quarterly
        WHERE stock_code = ?
        ORDER BY report_date ASC
    """, (code,)).fetchall()
    db.close()
    if len(rows) > limit:
        rows = rows[-limit:]
    return [dict(r) for r in rows]


def _fetch_annual(code: str, limit: int = 10) -> List[Dict]:
    """拉取年度财报数据"""
    db = _get_db()
    rows = db.execute("""
        SELECT stock_code, report_date, net_profit_yoy, roe
        FROM stock_financials_annual
        WHERE stock_code = ?
        ORDER BY report_date ASC
    """, (code,)).fetchall()
    db.close()
    if len(rows) > limit:
        rows = rows[-limit:]
    return [dict(r) for r in rows]


def _get_stock_name(code: str) -> str:
    db = _get_db()
    row = db.execute("SELECT name FROM stock_basic WHERE stock_code = ?", (code,)).fetchone()
    db.close()
    return row['name'] if row else code


def _yoy_diff(later: Optional[float], earlier: Optional[float]) -> Optional[float]:
    """计算同比变化差值（百分点）"""
    if later is None or earlier is None:
        return None
    return round(later - earlier, 2)


def _is_consecutive_decline(values: List[Optional[float]]) -> bool:
    """
    检查是否存在连续两个季度的同比增速递减。
    需要至少三个有效值: A > B > C（两个相邻递减对）。
    """
    valid = [v for v in values if v is not None]
    if len(valid) < 3:
        return False
    # 取最近三个有效值，检查是否连续递减
    return valid[-3] > valid[-2] and valid[-2] > valid[-1]


def _analysis_text_eps(current: float, previous: float, quarters: List[Dict]) -> str:
    """生成 EPS 分析文字"""
    direction = "递减" if previous > current else "递增"
    diff = abs(previous - current)
    # 检查是否有异常波动
    vals = [q.get('net_profit_adj_yoy') for q in quarters if q.get('net_profit_adj_yoy') is not None]
    has_anomaly = False
    if len(vals) >= 3:
        avg = sum(abs(v) for v in vals[-4:]) / min(4, len(vals[-4:]))
        if abs(current - previous) > avg * 1.5:
            has_anomaly = True
    text = f"最近两个发布季 EPS 同比增速{direction}：{previous:+.1f}% → {current:+.1f}%（变动 {diff:.1f} 个百分点）。"
    if has_anomaly:
        last_4 = vals[-4:] if len(vals) >= 4 else vals
        text += f" 近期波动较大（近{len(last_4)}季振幅异常），需关注下季是否企稳。"
    else:
        text += f" 连续增速{direction}表明盈利动能{'减弱' if direction == '递减' else '增强'}。"
    return text


def _analysis_text_simple(label: str, current: float, previous: float, unit: str = "%") -> str:
    direction = "下滑" if previous > current else "上升"
    diff = abs(previous - current)
    return f"最近两个发布季{label}连续{direction}：{previous:.1f}{unit} → {current:.1f}{unit}（变动 {diff:.1f} 个百分点）。"


def _analysis_text_roe(current: float, prev_year: float) -> str:
    if current >= 17:
        if prev_year is not None and prev_year > current:
            diff = prev_year - current
            return f"ROE={current:.1f}%，高于 17% 安全线。同比去年 {prev_year:.1f}% 下滑 {diff:.1f} 个百分点，但绝对值仍属健康。"
        return f"ROE={current:.1f}%，高于 17% 安全线，同比稳定。盈利能力良好。"
    else:
        return f"ROE={current:.1f}%，低于 17% 安全线。资本回报率不足，需关注公司盈利能力是否持续下降。"


def _analysis_text_annual_eps(current: float) -> str:
    if current < 0:
        return f"最近年度 EPS 同比 {current:+.1f}%，出现负增长。年度盈利出现拐点，需警惕长期趋势逆转。"
    elif current < 10:
        return f"最近年度 EPS 同比 {current:+.1f}%，增速处于低位。增长动能偏弱，关注下一年度能否回升。"
    else:
        return f"最近年度 EPS 同比 {current:+.1f}%，保持正增长。年度盈利趋势健康。"


def check_fundamental_deterioration(code: str) -> Dict:
    """
    检测基本面恶化信号。

    Returns:
        Dict: 包含 verdict, red_flags, checks 等字段
    """
    # 1. 拉取数据
    quarterly = _fetch_quarterly(code, limit=40)
    annual = _fetch_annual(code, limit=10)
    name = _get_stock_name(code)

    # 2. 数据充足性检查
    if len(quarterly) < 5:
        return {
            "code": code, "name": name,
            "verdict": "insufficient_data",
            "red_flags": 0, "total_checks": 5,
            "data_quarters": len(quarterly),
            "latest_report_date": quarterly[-1]['report_date'] if quarterly else None,
            "checks": {},
            "reason": f"季度数据仅 {len(quarterly)} 条，需至少 5 条才可研判"
        }

    # 3. 提取各检查项的数据序列
    eps_yoy = [q.get('net_profit_adj_yoy') for q in quarterly]
    rev_yoy = [q.get('revenue_yoy') for q in quarterly]
    nm_single = [q.get('net_profit_margin') for q in quarterly]
    gm_single = [q.get('gross_margin_single') for q in quarterly]

    # 计算净利率和毛利率的同比增速（同季差值，百分点）
    nm_yoy = []
    gm_yoy = []
    for i, q in enumerate(quarterly):
        if i >= 4:
            nm_yoy.append(_yoy_diff(nm_single[i], nm_single[i - 4]))
            gm_yoy.append(_yoy_diff(gm_single[i], gm_single[i - 4]))
        else:
            nm_yoy.append(None)
            gm_yoy.append(None)

    # 4. EPS 增速检查
    eps_valid = [v for v in eps_yoy if v is not None]
    eps_latest = eps_valid[-1] if eps_valid else None
    eps_prev = eps_valid[-2] if len(eps_valid) >= 2 else None
    eps_red = _is_consecutive_decline(eps_yoy)

    # 5. 营收增速检查
    rev_valid = [v for v in rev_yoy if v is not None]
    rev_latest = rev_valid[-1] if rev_valid else None
    rev_prev = rev_valid[-2] if len(rev_valid) >= 2 else None
    rev_red = _is_consecutive_decline(rev_yoy)

    # 6. 净利率检查
    nm_valid = [v for v in nm_yoy if v is not None]
    nm_latest = nm_valid[-1] if nm_valid else None
    nm_prev = nm_valid[-2] if len(nm_valid) >= 2 else None
    nm_red = _is_consecutive_decline(nm_yoy)

    # 7. 毛利率检查
    gm_valid = [v for v in gm_yoy if v is not None]
    gm_latest = gm_valid[-1] if gm_valid else None
    gm_prev = gm_valid[-2] if len(gm_valid) >= 2 else None
    gm_red = _is_consecutive_decline(gm_yoy)

    # 8. ROE 检查（使用年度数据，避免季节性Q1陷阱）
    roe_annual = [a.get('roe') for a in annual if a.get('roe') is not None]
    roe_latest = roe_annual[-1] if roe_annual else None
    roe_prev_year = roe_annual[-2] if len(roe_annual) >= 2 else None

    roe_red = False
    if roe_latest is not None:
        if roe_latest < 17:
            roe_red = True
        elif roe_prev_year is not None and roe_prev_year - roe_latest > 0.5:
            roe_red = True

    # 9. 年度 EPS（仅展示）
    ann_eps_valid = [a.get('net_profit_yoy') for a in annual if a.get('net_profit_yoy') is not None]
    ann_eps_latest = ann_eps_valid[-1] if ann_eps_valid else None

    # 10. 计分
    red_flags = sum([eps_red, rev_red, nm_red, gm_red, roe_red])
    if red_flags >= 3:
        verdict = "sell"
    elif red_flags == 2:
        verdict = "watch"
    else:
        verdict = "ok"

    # 构建净利率和毛利率的 quarters 数据（在 make_check 之前准备好）
    def _build_nm_gm_quarters(field):
        qs = []
        yoy_seq = nm_yoy if field == 'nm_yoy' else gm_yoy
        for i, q in enumerate(quarterly):
            if i >= 4 and yoy_seq[i] is not None:
                qs.append({"date": q['report_date'], "value": round(yoy_seq[i], 2)})
        return qs

    nm_quarters_data = _build_nm_gm_quarters('nm_yoy')
    gm_quarters_data = _build_nm_gm_quarters('gm_yoy')

    # 预构建各检查项的 quarters 数据
    eps_quarters = [{"date": q['report_date'], "value": round(q['net_profit_adj_yoy'], 2)}
                    for q in quarterly if q.get('net_profit_adj_yoy') is not None]
    rev_quarters = [{"date": q['report_date'], "value": round(q['revenue_yoy'], 2)}
                    for q in quarterly if q.get('revenue_yoy') is not None]
    nm_quarters_data = _build_nm_gm_quarters('nm_yoy')
    gm_quarters_data = _build_nm_gm_quarters('gm_yoy')

    # 11. 构建 checks
    def make_check(status, label, current_v, previous_v, trend, analysis, qs_data):
        return {
            "status": status, "label": label,
            "current": round(current_v, 2) if current_v is not None else None,
            "previous": round(previous_v, 2) if previous_v is not None else None,
            "trend": trend,
            "quarters": qs_data,
            "analysis": analysis
        }

    def make_roe_check(status, label, current_v, prev_v, trend, analysis, annual_data):
        ys = [{"year": a['report_date'][:4], "value": round(a['roe'], 2)}
              for a in annual_data if a.get('roe') is not None]
        return {
            "status": status, "label": label,
            "current": round(current_v, 2) if current_v is not None else None,
            "previous_year": round(prev_v, 2) if prev_v is not None else None,
            "trend": trend,
            "years": ys,
            "analysis": analysis
        }

    def make_annual_check(status, label, current_v, analysis, years_data):
        return {
            "status": status, "label": label,
            "display_only": True,
            "current": round(current_v, 2) if current_v is not None else None,
            "years": [{"year": a['report_date'][:4], "value": round(a['net_profit_yoy'], 2)}
                      for a in annual if a.get('net_profit_yoy') is not None],
            "analysis": analysis
        }

    eps_trend = "down" if (eps_prev is not None and eps_latest is not None and eps_prev > eps_latest) else "up"
    rev_trend = "down" if (rev_prev is not None and rev_latest is not None and rev_prev > rev_latest) else "up"
    nm_trend = "down" if (nm_prev is not None and nm_latest is not None and nm_prev > nm_latest) else "up"
    gm_trend = "down" if (gm_prev is not None and gm_latest is not None and gm_prev > gm_latest) else "up"

    eps_analysis = _analysis_text_eps(eps_latest or 0, eps_prev or 0, quarterly) if eps_latest is not None else "EPS 数据不足"
    rev_analysis = _analysis_text_simple("营收同比增速", rev_latest or 0, rev_prev or 0) if rev_latest is not None else "营收数据不足"
    nm_analysis = _analysis_text_simple("净利率同比变化", nm_latest or 0, nm_prev or 0, "ppt") if nm_latest is not None else "净利率数据不足"
    gm_analysis = _analysis_text_simple("毛利率同比变化", gm_latest or 0, gm_prev or 0, "ppt") if gm_latest is not None else "毛利率数据不足"
    roe_analysis = _analysis_text_roe(roe_latest or 0, roe_prev_year or 0) if roe_latest is not None else "ROE 数据不足"
    ann_analysis = _analysis_text_annual_eps(ann_eps_latest or 0) if ann_eps_latest is not None else "年度数据不足"

    latest_report = quarterly[-1]['report_date'] if quarterly else None

    eps_na = eps_latest is None
    rev_na = rev_latest is None
    nm_na = nm_latest is None
    gm_na = gm_latest is None
    roe_na = roe_latest is None

    checks = {
        "eps_growth": make_check("red" if eps_red else ("green" if not eps_na else "na"), "EPS 增速", eps_latest, eps_prev, eps_trend, eps_analysis, eps_quarters),
        "revenue_growth": make_check("red" if rev_red else ("green" if not rev_na else "na"), "营收增速", rev_latest, rev_prev, rev_trend, rev_analysis, rev_quarters),
        "net_margin": make_check("red" if nm_red else ("green" if not nm_na else "na"), "净利率", nm_latest, nm_prev, nm_trend, nm_analysis, nm_quarters_data),
        "gross_margin": make_check("red" if gm_red else ("green" if not gm_na else "na"), "毛利率", gm_latest, gm_prev, gm_trend, gm_analysis, gm_quarters_data),
        "roe": make_roe_check("red" if roe_red else ("green" if not roe_na else "na"), "ROE", roe_latest, roe_prev_year, "down" if roe_red else "stable", roe_analysis, annual),
        "annual_eps": make_annual_check("red" if (ann_eps_latest is not None and ann_eps_latest < 0) else "green", "年度 EPS", ann_eps_latest, ann_analysis, annual),
    }

    return {
        "code": code,
        "name": name,
        "verdict": verdict,
        "red_flags": red_flags,
        "total_checks": 5,
        "data_quarters": len(quarterly),
        "latest_report_date": latest_report,
        "checks": checks,
    }


if __name__ == '__main__':
    import sys, json
    code = sys.argv[1] if len(sys.argv) > 1 else '600519'
    result = check_fundamental_deterioration(code)
    print(json.dumps(result, ensure_ascii=False, indent=2))
