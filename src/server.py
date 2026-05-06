#!/usr/bin/env python3
"""
O'Neil 信号回测框架 — Flask API Server (Multi-signal)
端口: 8788
信号: distribution_day | (future: follow_through_day, accumulation, breakout, ...)
"""
import json, sqlite3, math, os, sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g

# Add parent to path for detector imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from detectors.distribution_day import detect as detect_distribution_days
from detectors.follow_through_day import detect as detect_follow_through_days

# ── Config ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)  # ~/investment-system/
CONFIG_DIR = os.path.join(PROJECT_DIR, 'config', 'market')
DB_PATH = os.path.join(PROJECT_DIR, 'data', 'lixinger.db')
DATA_DIR = os.path.join(PROJECT_DIR, 'data')

app = Flask(__name__)

# ═══════════════════════════════════════════════
# Database helpers
# ═══════════════════════════════════════════════

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db: db.close()

def init_schema():
    db = sqlite3.connect(DB_PATH)
    schema_path = os.path.join(PROJECT_DIR, 'data', 'schema.sql')
    with open(schema_path, encoding='utf-8') as f:
        db.executescript(f.read())
    db.commit()
    db.close()

# ═══════════════════════════════════════════════
# Technical indicators (computed on the fly)
# ═══════════════════════════════════════════════

def compute_ma(closes, window):
    if len(closes) < window: return None
    return sum(closes[-window:]) / window

def compute_volatility(changes, window):
    if len(changes) < window: return None
    recent = changes[-window:]
    mean = sum(recent) / len(recent)
    variance = sum((x - mean) ** 2 for x in recent) / len(recent)
    return math.sqrt(variance)

# ═══════════════════════════════════════════════
# K-line enrichment (shared by all signals)
# ═══════════════════════════════════════════════

def enrich_klines(rows):
    """Add change_pct, prev_close, K-line positions, MAs, volatility to raw DB rows."""
    klines = []
    prev_close = None
    changes_pct = []

    for r in rows:
        d = dict(r)
        if prev_close and prev_close != 0:
            d['change_pct'] = round((d['close'] - prev_close) / prev_close * 100, 4)
        else:
            d['change_pct'] = 0.0
        d['prev_close'] = prev_close or d['close']
        prev_close = d['close']
        changes_pct.append(d['change_pct'])

        hl_range = d['high'] - d['low']
        if hl_range > 0:
            d['close_position'] = round((d['close'] - d['low']) / hl_range * 100, 1)
            d['upper_shadow_pct'] = round((d['high'] - max(d['close'], d['open'])) / hl_range * 100, 1)
            d['lower_shadow_pct'] = round((min(d['close'], d['open']) - d['low']) / hl_range * 100, 1)
            d['body_pct'] = round(abs(d['close'] - d['open']) / hl_range * 100, 1)
        else:
            d['close_position'] = 50
            d['upper_shadow_pct'] = d['lower_shadow_pct'] = d['body_pct'] = 0

        klines.append(d)

    closes = [k['close'] for k in klines]
    volumes = [k['volume'] for k in klines]

    for i, k in enumerate(klines):
        if i > 0 and volumes[i-1] > 0:
            k['volume_ratio'] = round(volumes[i] / volumes[i-1], 4)
        else:
            k['volume_ratio'] = 1.0
        if i >= 4:
            ma5v = sum(volumes[i-4:i+1]) / 5
            k['volume_ratio_ma5'] = round(volumes[i] / ma5v, 4) if ma5v > 0 else 1.0
        else:
            k['volume_ratio_ma5'] = 1.0

        w = i + 1
        k['ma5']   = round(compute_ma(closes[:i+1], min(5, w)), 2) if w >= 5 else None
        k['ma10']  = round(compute_ma(closes[:i+1], min(10, w)), 2) if w >= 10 else None
        k['ma20']  = round(compute_ma(closes[:i+1], min(20, w)), 2) if w >= 20 else None
        k['ma50']  = round(compute_ma(closes[:i+1], min(50, w)), 2) if w >= 50 else None
        k['ma120'] = round(compute_ma(closes[:i+1], min(120, w)), 2) if w >= 120 else None
        k['ma250'] = round(compute_ma(closes[:i+1], min(250, w)), 2) if w >= 250 else None
        k['vol_5d']  = round(compute_volatility(changes_pct[:i+1], min(5, w)), 4) if w >= 5 else None
        k['vol_10d'] = round(compute_volatility(changes_pct[:i+1], min(10, w)), 4) if w >= 10 else None
        k['vol_20d'] = round(compute_volatility(changes_pct[:i+1], min(20, w)), 4) if w >= 20 else None

    return klines

# ═══════════════════════════════════════════════
# YAML config loader (simple, no PyYAML needed)
# ═══════════════════════════════════════════════

def load_config(signal_type):
    """Load YAML config file as a flat dict. Searches config/ and config/market/ first."""
    # Try config/market/ first (new convention), then config/ root (fallback)
    path = os.path.join(CONFIG_DIR, 'market', f'{signal_type}.yaml')
    if not os.path.exists(path):
        path = os.path.join(CONFIG_DIR, f'{signal_type}.yaml')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        content = f.read()
    # Parse simple YAML (no nested structures beyond 1 level)
    config = {}
    current_section = None
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if ':' in stripped and not stripped.startswith(' ') and not stripped.startswith('-'):
            # Top-level key
            key = stripped.split(':')[0].strip()
            val = stripped.split(':', 1)[1].strip()
            if val:
                config[key] = _parse_yaml_val(val)
            else:
                current_section = key
                config[key] = {}
        elif current_section and ':' in stripped:
            key = stripped.split(':')[0].strip()
            val = stripped.split(':', 1)[1].strip()
            if val:
                config[current_section][key] = _parse_yaml_val(val)
    return config

def _parse_yaml_val(s):
    s = s.strip().strip('"').strip("'")
    if s.lower() in ('true', 'yes'): return True
    if s.lower() in ('false', 'no'): return False
    try: return float(s) if '.' in s else int(s)
    except: return s

def save_config(signal_type, raw_yaml):
    """Save raw YAML string to config file (uses market/ subdirectory)."""
    path = os.path.join(CONFIG_DIR, 'market', f'{signal_type}.yaml')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(raw_yaml)

# ═══════════════════════════════════════════════
# API: GET /api/indices
# ═══════════════════════════════════════════════

INDEX_NAMES = {
    '000001': '上证综指', '000016': '上证50', '000300': '沪深300',
    '000688': '科创50', '000852': '中证1000', '000905': '中证500',
    '000985': '中证全指', '399001': '深证成指', '399006': '创业板指',
    '399673': '创业板50', '399986': '中证银行', '399995': '基建工程',
    '399998': '中证煤炭', '931008': '中证红利', 'H11057': '中证全债',
}

@app.route('/api/indices')
def api_indices():
    db = get_db()
    rows = db.execute("""SELECT DISTINCT stock_code FROM index_daily_kline WHERE kline_type='normal' ORDER BY stock_code""").fetchall()
    return jsonify([{'code': r['stock_code'], 'name': INDEX_NAMES.get(r['stock_code'], r['stock_code'])} for r in rows])

# ═══════════════════════════════════════════════
# API: GET /api/kline
# ═══════════════════════════════════════════════

@app.route('/api/kline')
def api_kline():
    stock_code = request.args.get('stock_code', '000985')
    start = request.args.get('start', '2020-01-01')
    end = request.args.get('end', '2024-12-31')

    db = get_db()
    rows = db.execute("""SELECT stock_code, date, open, high, low, close, volume, amount, change
        FROM index_daily_kline WHERE stock_code=? AND kline_type='normal'
        AND date >= date(?,'-300 days') AND date <= ? ORDER BY date""",
        (stock_code, start, end)).fetchall()

    klines = enrich_klines(rows)
    klines = [k for k in klines if k['date'] >= start]
    return jsonify(klines)

# ═══════════════════════════════════════════════
# API: POST /api/backtest (distribution_day)
# ═══════════════════════════════════════════════

@app.route('/api/backtest', methods=['POST', 'OPTIONS'])
def api_backtest():
    if request.method == 'OPTIONS': return '', 204

    data = request.get_json()
    stock_code = data.get('stock_code', '000985')
    start = data.get('start') or data.get('start_date', '2024-01-01')
    end = data.get('end') or data.get('end_date', '2024-12-31')
    signal_type = data.get('signal_type', 'distribution_day')
    params = data.get('params', {})

    db = get_db()
    rows = db.execute("""SELECT stock_code, date, open, high, low, close, volume, amount, change
        FROM index_daily_kline WHERE stock_code=? AND kline_type='normal'
        AND date >= date(?,'-365 days') AND date <= date(?,'+365 days') ORDER BY date""",
        (stock_code, start, end)).fetchall()

    klines = enrich_klines(rows)
    klines_for_chart = klines
    klines_in_range = [k for k in klines if k['date'] >= start and k['date'] <= end]

    # Route to detector
    if signal_type == 'follow_through_day':
        dist_signals = detect_distribution_days(klines_in_range, params) if params.get('use_distribution_signals', True) else []
        # FTD engine needs full klines for N-day new-low check; filter returned signals to range
        rally_attempts, signals, failed_ftds = detect_follow_through_days(klines, params, dist_signals)
        # Filter: only keep signals/rallies within the requested date range
        signals = [s for s in signals if start <= s.get('date','') <= end]
        failed_ftds = [s for s in failed_ftds if start <= s.get('date','') <= end]
        rally_attempts = [r for r in rally_attempts if start <= r.get('date','') <= end]
    else:
        # Default: distribution_day (also works for future signals)
        signals = detect_distribution_days(klines_in_range, params)
        rally_attempts = []
        failed_ftds = []

    # Stats
    total = len(klines_in_range)
    signal_count = len(signals)
    type_counts = {}
    for s in signals: type_counts[s.get('signal_type', s.get('ftd_type', 'standard'))] = type_counts.get(s.get('signal_type', s.get('ftd_type', 'standard')), 0) + 1
    weighted = sum(s.get('weight', 1) for s in signals)

    return jsonify({
        'stock_code': stock_code, 'start': start, 'end': end,
        'signal_type': signal_type, 'params': params,
        'klines': klines_for_chart, 'signals': signals,
        'rally_attempts': rally_attempts,
        'failed_ftds': failed_ftds,
        'stats': {
            'total_days': total, 'signal_count': signal_count,
            'standard_count': type_counts.get('standard', 0),
            'heavy_count': type_counts.get('heavy', 0),
            'special_count': type_counts.get('special', 0),
            'reversal_count': type_counts.get('reversal', 0),
            'ftd_normal': type_counts.get('normal', 0),
            'ftd_volume': type_counts.get('volume', 0),
            'ftd_mega': type_counts.get('mega', 0),
            'weighted_count': weighted,
            'rally_count': len(rally_attempts),
            'failed_ftd_count': len(failed_ftds),
        }
    })

# ═══════════════════════════════════════════════
# API: POST /api/config (GET/POST)
# ═══════════════════════════════════════════════

@app.route('/api/config', methods=['GET', 'POST', 'OPTIONS'])
def api_config():
    if request.method == 'OPTIONS': return '', 204

    signal_type = request.args.get('signal_type', 'distribution_day')

    if request.method == 'POST':
        raw = request.get_data(as_text=True)
        if raw:
            save_config(signal_type, raw)
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'empty body'}), 400

    # GET
    config = load_config(signal_type)
    return jsonify(config)

# ═══════════════════════════════════════════════
# API: POST /api/backtest/save
# ═══════════════════════════════════════════════

@app.route('/api/backtest/save', methods=['POST', 'OPTIONS'])
def api_backtest_save():
    if request.method == 'OPTIONS': return '', 204

    data = request.get_json()
    name = data.get('name', f"Backtest {datetime.now().strftime('%Y%m%d_%H%M')}")
    stock_code = data.get('stock_code')
    start = data.get('start')
    end = data.get('end')
    signal_type = data.get('signal_type', 'distribution_day')
    params = data.get('params', {})
    signals = data.get('signals', [])
    stats = data.get('stats', {})

    db = get_db()
    cur = db.cursor()
    cur.execute("""INSERT INTO backtest_runs (name, signal_type, stock_code, start_date, end_date, params)
        VALUES (?,?,?,?,?,?)""", (name, signal_type, stock_code, start, end, json.dumps(params)))
    run_id = cur.lastrowid

    for s in signals:
        cur.execute("""INSERT INTO backtest_signals (run_id,stock_code,date,signal_type,score,open,high,low,close,
            change_pct,volume,amount,vol_5d,vol_10d,vol_20d,ma5,ma10,ma20,ma50,ma120,ma250,
            volume_score,decline_score,position_score,gap_score,special_score,total_score,
            close_position,upper_shadow_pct,lower_shadow_pct,volume_ratio,volume_ratio_ma5)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, stock_code, s.get('date'), s.get('signal_type'), s.get('total_score', 0),
             s.get('open'), s.get('high'), s.get('low'), s.get('close'), s.get('change_pct'),
             s.get('volume'), s.get('amount', 0), s.get('vol_5d'), s.get('vol_10d'), s.get('vol_20d'),
             s.get('ma5'), s.get('ma10'), s.get('ma20'), s.get('ma50'), s.get('ma120'), s.get('ma250'),
             0,0,0,0,0,0, s.get('close_position'), s.get('upper_shadow_pct'), s.get('lower_shadow_pct'),
             s.get('volume_ratio'), s.get('volume_ratio_ma5')))

    cur.execute("""INSERT INTO backtest_stats (run_id,total_days,signal_count,standard_count,
        heavy_count,stealth_count,reversal_count,weighted_count,avg_vol_10d,avg_volume_ratio)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (run_id, stats.get('total_days', 0), stats.get('signal_count', 0),
         stats.get('standard_count', 0), stats.get('heavy_count', 0),
         stats.get('special_count', 0), stats.get('reversal_count', 0),
         stats.get('weighted_count', 0), stats.get('avg_vol_10d'), stats.get('avg_volume_ratio')))

    db.commit()
    return jsonify({'ok': True, 'run_id': run_id})

# ═══════════════════════════════════════════════
# API: GET /api/backtest/list
# ═══════════════════════════════════════════════

@app.route('/api/backtest/list')
def api_backtest_list():
    db = get_db()
    signal_type = request.args.get('signal_type', 'distribution_day')
    rows = db.execute("""SELECT r.*, s.signal_count, s.weighted_count
        FROM backtest_runs r LEFT JOIN backtest_stats s ON r.id=s.run_id
        WHERE r.signal_type=? ORDER BY r.created_at DESC""", (signal_type,)).fetchall()
    return jsonify([dict(r) for r in rows])

# ═══════════════════════════════════════════════
# API: GET /api/backtest/compare
# ═══════════════════════════════════════════════

@app.route('/api/backtest/compare')
def api_backtest_compare():
    id1, id2 = request.args.get('id1'), request.args.get('id2')
    db = get_db()

    def get_run(rid):
        run = db.execute("SELECT * FROM backtest_runs WHERE id=?", (rid,)).fetchone()
        stats = db.execute("SELECT * FROM backtest_stats WHERE run_id=?", (rid,)).fetchone()
        signals = db.execute("SELECT * FROM backtest_signals WHERE run_id=? ORDER BY date", (rid,)).fetchall()
        return {'run': dict(run) if run else None, 'stats': dict(stats) if stats else None,
                'signals': [dict(s) for s in signals]}

    return jsonify({'run1': get_run(id1), 'run2': get_run(id2)})

# ═══════════════════════════════════════════════
# API: GET /api/backtest/<id>/signals
# ═══════════════════════════════════════════════

@app.route('/api/backtest/<int:run_id>/signals')
def api_backtest_signals(run_id):
    db = get_db()
    rows = db.execute("SELECT * FROM backtest_signals WHERE run_id=? ORDER BY date", (run_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

# ═══════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    init_schema()
    print("🦊 O'Neil Backtest API Server starting on http://localhost:8788")
    print(f"   Config dir: {CONFIG_DIR}")
    print(f"   Detectors: distribution_day")
    app.run(host='0.0.0.0', port=8788, debug=False)
