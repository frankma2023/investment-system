"""
每日双强股批量形态扫描

1. 从 stock_rs_daily 查最新日期的双强股票（稳健龙头 / 加速爆发）
2. 排除ST + 市值<5000万
3. 逐只运行6引擎形态扫描
4. 输出 JSON + 静态HTML看板

用法：
    python scripts/daily_pattern_scan.py                    # 最新日期
    python scripts/daily_pattern_scan.py --date 2026-05-13  # 指定日期
    python scripts/daily_pattern_scan.py --top 50           # 只扫TOP50（快速测试）
"""

import sys, os, sqlite3, json, time, argparse
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))

DB_PATH = os.path.join(PROJECT_DIR, "data", "lixinger.db")
OUT_JSON = os.path.join(PROJECT_DIR, "web", "daily-pattern-scan", "data.json")
OUT_HTML = os.path.join(PROJECT_DIR, "web", "daily-pattern-scan", "index.html")

# RS 双强阈值（与 stock_rs.py 保持一致）
ROBUST_RPS_250 = 90
ROBUST_RPS_20 = 85
BURST_RPS_250 = 80
BURST_RPS_20 = 95
MIN_AMOUNT = 50_000_000  # 5000万


def get_candidates(date_str, top_n=None):
    """查询双强股票列表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT r.stock_code, b.name, r.close, r.rps_20, r.rps_60, r.rps_120, r.rps_250,
               rs_line, r.amount,
               CASE
                   WHEN r.rps_250>=? AND r.rps_20>=? AND r.rps_250>=? AND r.rps_20>=?
                       THEN '双强'
                   WHEN r.rps_250>=? AND r.rps_20>=? THEN '稳健龙头'
                   WHEN r.rps_250>=? AND r.rps_20>=? THEN '加速爆发'
               END as ds_type
        FROM stock_rs_daily r
        JOIN stock_basic b ON r.stock_code = b.stock_code
        WHERE r.date = ?
          AND ((r.rps_250 >= ? AND r.rps_20 >= ?) OR (r.rps_250 >= ? AND r.rps_20 >= ?))
          AND b.listing_status = 'normally_listed'
          AND b.name NOT LIKE '%ST%'
          AND b.name NOT LIKE '%*ST%'
          AND r.amount >= ?
        ORDER BY r.rps_250 DESC, r.rps_20 DESC
    """

    params = (
        ROBUST_RPS_250, ROBUST_RPS_20, BURST_RPS_250, BURST_RPS_20,
        ROBUST_RPS_250, ROBUST_RPS_20,
        BURST_RPS_250, BURST_RPS_20,
        date_str,
        ROBUST_RPS_250, ROBUST_RPS_20, BURST_RPS_250, BURST_RPS_20,
        MIN_AMOUNT
    )

    rows = conn.execute(query, params).fetchall()
    conn.close()

    # 计算当日涨幅
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    enriched = []
    for r in rows:
        code = r['stock_code']
        # 查前一日收盘价
        prev = conn.execute("""
            SELECT close FROM daily_kline
            WHERE stock_code=? AND date < ? ORDER BY date DESC LIMIT 1
        """, (code, date_str)).fetchone()
        prev_close = prev['close'] if prev and prev['close'] else r['close']
        change_pct = (r['close'] - prev_close) / prev_close * 100 if prev_close > 0 else 0

        enriched.append({
            'stock_code': code,
            'name': r['name'],
            'close': round(r['close'], 2),
            'change_pct': round(change_pct, 2),
            'rps_20': r['rps_20'],
            'rps_60': r['rps_60'],
            'rps_120': r['rps_120'],
            'rps_250': r['rps_250'],
            'rs_line': round(r['rs_line'], 2) if r['rs_line'] else None,
            'amount': r['amount'],
            'ds_type': r['ds_type'],
        })

    conn.close()

    if top_n:
        enriched = enriched[:top_n]

    return enriched


def scan_stock(code, date_str):
    """对单只股票运行6引擎扫描"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 取最近750天K线
    start_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=750)).strftime('%Y-%m-%d')
    rows = conn.execute("""
        SELECT date, open, high, low, close, volume
        FROM daily_kline
        WHERE stock_code=? AND date>=? AND date<=?
        ORDER BY date
    """, (code, start_date, date_str)).fetchall()
    conn.close()

    if len(rows) < 50:
        return []

    klines = [dict(r) for r in rows]

    try:
        from engine_registry import run_all_engines
        signals = run_all_engines(klines=klines, indicators=None)
    except Exception as e:
        print(f"  [{code}] engine error: {e}")
        return []

    # 只保留当天信号
    today_signals = [s for s in signals if s['date'] == date_str]
    return today_signals


def format_signal_summary(signals):
    """将信号列表压缩为一行文本"""
    if not signals:
        return '—'

    by_source = {}
    for s in signals:
        src = s['source']
        tp = s.get('type', 'bullish')
        if src not in by_source:
            by_source[src] = {'bullish': 0, 'bearish': 0}
        by_source[src][tp] += 1

    parts = []
    # 顺序：自研形态在前，指标/cdl在后
    order = ['pocket_pivot', 'double_bottom', 'breakout', 'flat_base', 'cdl', 'talib']
    labels = {
        'pocket_pivot': 'PP', 'double_bottom': 'DB', 'breakout': 'BK',
        'flat_base': 'FB', 'cdl': 'CDL', 'talib': 'TA'
    }
    for src in order:
        if src in by_source:
            counts = by_source[src]
            label = labels.get(src, src)
            if counts['bullish'] > 0 and counts['bearish'] > 0:
                parts.append('%s+%d-%d' % (label, counts['bullish'], counts['bearish']))
            elif counts['bullish'] > 0:
                parts.append('%s+%d' % (label, counts['bullish']))
            elif counts['bearish'] > 0:
                parts.append('%s-%d' % (label, counts['bearish']))

    return ' '.join(parts) if parts else '—'


def generate_html(candidates, date_str, elapsed):
    """生成静态HTML看板"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    rows_html = ''
    for i, c in enumerate(candidates):
        code = c['stock_code']
        name = c['name']
        ds = c['ds_type']
        ds_badge = ''
        if ds == '双强':
            ds_badge = '<span class="badge ds-double">双强</span>'
        elif ds == '稳健龙头':
            ds_badge = '<span class="badge ds-robust">稳健龙头</span>'
        elif ds == '加速爆发':
            ds_badge = '<span class="badge ds-burst">加速爆发</span>'

        # RS 值着色
        def rs_td(val):
            if val is None: return '<td>—</td>'
            if val >= 90: cls = 'rs-hot'
            elif val >= 80: cls = 'rs-warm'
            else: cls = ''
            return '<td class="%s">%d</td>' % (cls, val) if cls else '<td>%d</td>' % val

        change = c['change_pct']
        chg_cls = 'up' if change > 0 else 'down' if change < 0 else ''
        chg_html = '<span class="%s">%+.2f%%</span>' % (chg_cls, change)

        signal_txt = c.get('signal_summary', '—')

        # 信号摘要：如果有具体信号类型，高亮显示
        if signal_txt != '—' and '+' in signal_txt:
            signal_html = '<span class="sig-text">%s</span>' % signal_txt
        else:
            signal_html = '<span class="sig-none">%s</span>' % signal_txt

        rows_html += '''
            <tr>
                <td><a class="code-link" href="../pattern-scan/?code=%s" target="_blank">%s</a></td>
                <td>%s</td>
                <td class="num">%.2f</td>
                <td class="num">%s</td>
                %s%s%s%s
                <td>%s</td>
                <td>%s</td>
            </tr>''' % (
            code, code, name, c['close'], chg_html,
            rs_td(c['rps_250']), rs_td(c['rps_120']),
            rs_td(c['rps_60']), rs_td(c['rps_20']),
            ds_badge, signal_html
        )

    html = '''<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日双强股形态扫描 · 投资手账本</title>
<link rel="stylesheet" href="../shared/css/theme.css">
<link rel="stylesheet" href="../shared/css/base.css">
<link rel="stylesheet" href="../shared/css/xhs-cards.css">
<link rel="stylesheet" href="../shared/css/components.css">
<style>
body { font-family: var(--font-display); }
.app-container { max-width: 1400px; margin:0 auto; padding:12px 16px; }
.top-bar { display:flex; justify-content:space-between; align-items:center; padding:14px 20px; background:var(--card-bg); border-radius:18px; margin-bottom:12px; box-shadow:0 1px 6px rgba(0,0,0,0.04); }
.top-bar h1 { font-size:1.1rem; margin:0; }
.top-bar .meta { font-size:0.65rem; color:var(--text-tertiary); }
.table-wrap { background:var(--card-bg); border-radius:18px; padding:10px; box-shadow:0 1px 6px rgba(0,0,0,0.04); overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:0.7rem; }
th { padding:8px 6px; text-align:left; font-weight:700; color:var(--text-secondary); font-size:0.6rem; border-bottom:2px solid var(--divider); white-space:nowrap; position:sticky; top:0; background:var(--card-bg); cursor:pointer; }
th:hover { color:var(--color-accent); }
td { padding:6px; border-bottom:1px solid var(--divider); white-space:nowrap; }
tr:hover { background:var(--color-accent-subtle); }
.num { text-align:right; }
.code-link { color:var(--color-accent); font-weight:700; text-decoration:none; }
.code-link:hover { text-decoration:underline; }
.up { color:#E53935; font-weight:700; }
.down { color:#4CAF50; font-weight:700; }
.rs-hot { color:#E53935; font-weight:700; }
.rs-warm { color:#FF9800; font-weight:600; }
.badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:0.58rem; font-weight:700; }
.ds-double { background:#E8F5E9; color:#2E7D32; border:1px solid #4CAF50; }
.ds-robust { background:#E3F2FD; color:#1565C0; border:1px solid #2196F3; }
.ds-burst { background:#FFF3E0; color:#E65100; border:1px solid #FF9800; }
.sig-text { font-size:0.62rem; color:var(--text-secondary); }
.sig-none { font-size:0.62rem; color:var(--text-tertiary); }
.nav-dropdown { position:relative; display:inline-flex; }
.nav-dropdown-menu { display:none; position:absolute; top:100%; left:0; background:var(--card-bg); border:1px solid var(--divider); border-radius:14px; box-shadow:0 4px 20px rgba(0,0,0,0.08); min-width:150px; padding:6px 0; z-index:200; white-space:nowrap; }
.nav-dropdown:hover .nav-dropdown-menu { display:block; }
.nav-dropdown-menu a { display:block; padding:7px 16px; font-size:0.72rem; color:var(--text-secondary); text-decoration:none; }
.nav-dropdown-menu a:hover { background:var(--color-accent-subtle); color:var(--color-accent); }
.nav-dropdown-menu a.active { color:var(--color-accent); font-weight:700; }
.footer { text-align:center; padding:16px; font-size:0.6rem; color:var(--text-tertiary); }
</style>
</head>
<body>
<div class="app-container">
<nav class="top-nav">
  <div class="nav-brand"><span class="nav-fox">📋</span><span>每日双强形态扫描</span></div>
  <div class="nav-links">
    <a href="../" class="nav-item">🏠 看板</a>
    <div class="nav-dropdown"><a href="#" class="nav-item">回测 ▾</a><div class="nav-dropdown-menu">
      <a href="../distribution-day/">📉 抛盘日</a><a href="../follow-through-day/">📈 追盘日</a><a href="../accumulation-day/">📦 吸筹日</a>
      <a href="../index-rs-backtest/">🏆 指数RS强度</a><a href="../index-crowdedness/">📊 指数拥挤度</a><a href="../stock-rs-backtest/">💪 个股RS强度</a>
      <a href="../index-ad-backtest/">🔍 机构吸筹/出货</a><a href="../divergence-backtest/">⚠️ 指数背离</a>
      <a href="../strongest-index/">⭐ 最强指数</a><a href="../base-detection/">📐 标准突破</a><a href="../pocket-pivot/">🎯 口袋支点</a>
      <a href="../pattern-scan/">🔎 形态识别</a>
    </div></div>
    <a href="../index-scan/" class="nav-item">🔬 指数扫描</a><a href="../index-valuation/" class="nav-item">📈 指数估值</a>
    <a href="../stock-valuation/" class="nav-item">💎 个股扫描</a><a href="../market-scan/" class="nav-item">📊 大盘扫描</a>
    <a href="../pattern-scan/" class="nav-item">🔎 形态识别</a>
    <button class="theme-toggle">🌙</button>
  </div>
</nav>

<div class="top-bar">
  <div>
    <h1>📋 双强股形态扫描 <span style="font-size:0.65rem;font-weight:400;color:var(--text-tertiary)">—— 稳健龙头 + 加速爆发</span></h1>
  </div>
  <div class="meta">
    扫描日期: ''' + date_str + ''' | 股票数: ''' + str(len(candidates)) + ''' | 耗时: ''' + str(round(elapsed, 1)) + '''s | 生成: ''' + now + '''
  </div>
</div>

<div class="table-wrap">
<table id="stock-table">
<thead>
<tr>
  <th onclick="sortTable(0)">代码</th>
  <th onclick="sortTable(1)">名称</th>
  <th onclick="sortTable(2)">价格</th>
  <th onclick="sortTable(3)">涨幅</th>
  <th onclick="sortTable(4)">RS_250</th>
  <th onclick="sortTable(5)">RS_120</th>
  <th onclick="sortTable(6)">RS_60</th>
  <th onclick="sortTable(7)">RS_20</th>
  <th onclick="sortTable(8)">类型</th>
  <th>信号摘要</th>
</tr>
</thead>
<tbody>
''' + rows_html + '''
</tbody>
</table>
</div>

<div class="footer">
  每日自动扫描 · 数据来源 stock_rs_daily · 引擎: Pocket Pivot / Double Bottom / Breakout / Flat Base / TA-Lib CDL
</div>
</div>

<script>
// 简易表格排序
function sortTable(col) {
  const table = document.getElementById('stock-table');
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const isNum = [false, false, true, true, true, true, true, true, false, false][col];
  
  rows.sort((a, b) => {
    let va = a.cells[col].textContent.replace(/[%+\\-]/g,'').trim();
    let vb = b.cells[col].textContent.replace(/[%+\\-]/g,'').trim();
    if (isNum) { va = parseFloat(va)||0; vb = parseFloat(vb)||0; }
    return vb > va ? 1 : vb < va ? -1 : 0;
  });
  
  // 默认降序
  if (col >= 2 && col <= 7) rows.reverse();
  
  rows.forEach(r => tbody.appendChild(r));
}

// 主题切换
document.querySelector('.theme-toggle').addEventListener('click', () => {
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === 'light' ? 'dark' : 'light';
  document.querySelector('.theme-toggle').textContent = html.dataset.theme === 'light' ? '🌙' : '☀️';
});

// 默认按 RS_250 降序
sortTable(4);
</script>
</body>
</html>'''

    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--top', type=int, default=None, help='只扫描TOP N（测试用）')
    args = parser.parse_args()

    if args.date:
        date_str = args.date
    else:
        # 从 stock_rs_daily 取最新日期
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT MAX(date) FROM stock_rs_daily")
        date_str = cur.fetchone()[0]
        conn.close()

    if not date_str:
        print("No data in stock_rs_daily")
        return

    print(f"Scan date: {date_str}")
    t0 = time.time()

    # Step 1: 获取候选
    candidates = get_candidates(date_str, args.top)
    print(f"Candidates: {len(candidates)}")

    if not candidates:
        print("No candidates found")
        return

    # Step 2: 逐只扫描
    for i, c in enumerate(candidates):
        code = c['stock_code']
        try:
            signals = scan_stock(code, date_str)
            c['signals'] = signals
            c['signal_summary'] = format_signal_summary(signals)
        except Exception as e:
            print(f"  [{code}] scan error: {e}")
            c['signals'] = []
            c['signal_summary'] = 'ERR'

        if (i + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  Progress: {i+1}/{len(candidates)} ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"Scan complete: {len(candidates)} stocks in {elapsed:.1f}s")

    # Step 3: 保存 JSON
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date_str,
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'count': len(candidates),
            'elapsed': round(elapsed, 1),
            'candidates': candidates
        }, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {OUT_JSON}")

    # Step 4: 生成 HTML
    html = generate_html(candidates, date_str, elapsed)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"HTML saved: {OUT_HTML}")
    print("Done.")


if __name__ == '__main__':
    main()
