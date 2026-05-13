#!/usr/bin/env python3
"""
O'Neil 信号回测框架 — Flask API Server (Multi-signal)
端口: 8788
信号: distribution_day | (future: follow_through_day, accumulation, breakout, ...)
"""
import json, sqlite3, math, os, sys, re
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g

# Add parent to path for detector imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from detectors.distribution_day import detect as detect_distribution_days
from detectors.follow_through_day import detect as detect_follow_through_days
from detectors.accumulation_day import detect as detect_accumulation_days
from detectors.index_ad import detect as detect_index_ad
from detectors.divergence import (
    compute_rsi, compute_macd,
    detect_volume_price_divergence, detect_rsi_divergence,
    detect_macd_divergence, detect_breadth_divergence,
    confirm_divergence, compute_resonance
)
from engine_registry import discover_engines, get_engine_list, run_all_engines
from scanners.recommend import generate as generate_recommendation
import numpy as np
import talib

# ── Config ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)  # ~/investment-system/
CONFIG_DIR = os.path.join(PROJECT_DIR, 'config', 'market')
INDEX_RS_CONFIG = os.path.join(PROJECT_DIR, 'config', 'index_style.yaml')
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
    """Load YAML config file as a flat dict.
    Search order: config/market/ → config/ → return empty
    """
    # Paths to try, in order
    candidates = [
        os.path.join(CONFIG_DIR, f'{signal_type}.yaml'),           # config/market/
        os.path.join(PROJECT_DIR, 'config', f'{signal_type}.yaml'), # config/
    ]
    path = None
    for p in candidates:
        if os.path.exists(p):
            path = p
            break
    if not path:
        return {}
    # Try PyYAML first (handles nested structures), fall back to simple parser
    if HAS_YAML:
        with open(path, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    # Simple YAML parser fallback
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
    """Save raw YAML string to config file.
    Preserves existing location: config/market/ → config/ → default config/market/
    """
    candidates = [
        os.path.join(CONFIG_DIR, f'{signal_type}.yaml'),           # config/market/
        os.path.join(PROJECT_DIR, 'config', f'{signal_type}.yaml'), # config/
    ]
    path = None
    for p in candidates:
        if os.path.exists(p):
            path = p
            break
    if not path:
        path = candidates[0]  # default: config/market/
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
        rally_attempts, signals, failed_ftds = detect_follow_through_days(klines, params, dist_signals)
        signals = [s for s in signals if start <= s.get('date','') <= end]
        failed_ftds = [s for s in failed_ftds if start <= s.get('date','') <= end]
        rally_attempts = [r for r in rally_attempts if start <= r.get('date','') <= end]
    elif signal_type == 'accumulation_day':
        dist_signals = detect_distribution_days(klines_in_range, params) if params.get('use_distribution_signals', True) else []
        rally_attempts, acc_signals = detect_accumulation_days(klines, params, dist_signals)
        signals = [s for s in acc_signals if start <= s.get('date','') <= end]
        rally_attempts = [r for r in rally_attempts if start <= r.get('date','') <= end]
        failed_ftds = []
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
            'rally_attempts_count': len(rally_attempts),
            'accumulation_count': len(signals) if signal_type == 'accumulation' else 0,
            'ftd_count': len(signals) if signal_type == 'follow_through_day' else 0,
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
# API: GET /api/market-health
# ═══════════════════════════════════════════════

@app.route('/api/market-health')
def api_market_health():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()

    row = db.execute(
        "SELECT * FROM market_health_daily WHERE date <= ? ORDER BY date DESC LIMIT 1",
        (target_date,)
    ).fetchone()

    if not row:
        return jsonify({'status': 'no_data', 'date': target_date, 'total_score': 0, 'indicators': [], 'rotations': []})

    indicators = [
        {'key': 'ma50_above',   'value': row['ma50_above_value'],   'score': row['ma50_above_score'],   'detail': ''},
        {'key': 'hl_ratio',     'value': row['hl_ratio_value'],     'score': row['hl_ratio_score'],     'detail': ''},
        {'key': 'ad_ratio',     'value': row['ad_ratio_value'],     'score': row['ad_ratio_score'],     'detail': ''},
        {'key': 'vol_breakout', 'value': row['vol_breakout_value'], 'score': row['vol_breakout_score'],  'detail': ''},
        {'key': 'margin_5d',    'value': row['margin_5d_value'],    'score': row['margin_5d_score'],     'detail': ''},
        {'key': 'sector_rot',   'value': row['sector_rot_score'],   'score': row['sector_rot_score'],   'detail': ''},
        {'key': 'fear_greed',   'value': row['fear_greed_value'],   'score': row['fear_greed_score'],   'detail': ''},
    ]

    rot_rows = db.execute(
        "SELECT * FROM market_rotation_daily WHERE date = ?", (row['date'],)
    ).fetchall()

    rotations = []
    pool_icons = {"一级行业": "🏭", "二级行业": "🔧", "主题指数": "🎯", "策略指数": "🧩"}
    for r in rot_rows:
        rot = {
            'name': r['pool'],
            'icon': pool_icons.get(r['pool'], '📦'),
            'method': r['method'],
            'value': r['value'],
            'participates': r['method'] == 'overlap',
            'count': '',
        }
        if r['top5_current']:
            try:
                rot['top5_current'] = json.loads(r['top5_current'])
                rot['top5_last'] = json.loads(r.get('top5_last') or '[]')
                if r['method'] == 'overlap':
                    curr_set = set(rot['top5_current'])
                    last_set = set(rot['top5_last'])
                    rot['top5_overlap'] = list(curr_set & last_set)
            except Exception:
                pass
        rotations.append(rot)

    return jsonify({
        'date': row['date'],
        'total_score': row['total_score'],
        'rating': row['rating'],
        'indicators': indicators,
        'rotations': rotations,
    })

# ═══════════════════════════════════════════════
# API: GET /api/market-health/breakouts
# ═══════════════════════════════════════════════

@app.route('/api/market-health/breakouts')
def api_market_breakouts():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()
    rows = db.execute("""
        SELECT mb.*, sb.name
        FROM market_breakout_daily mb
        LEFT JOIN stock_basic sb ON mb.stock_code = sb.stock_code
        WHERE mb.date = (SELECT MAX(date) FROM market_breakout_daily WHERE date <= ?)
        ORDER BY mb.volume DESC
    """, (target_date,)).fetchall()
    stocks = [{
        'stock_code': r['stock_code'],
        'name': r['name'] or '',
        'close': r['close'],
        'change_pct': r['change_pct'],
        'volume': r['volume'],
        'amount': r['amount'],
    } for r in rows]
    return jsonify({'date': rows[0]['date'] if rows else target_date, 'count': len(stocks), 'stocks': stocks})

# ═══════════════════════════════════════════════
# API: GET /api/strongest-index
# ═══════════════════════════════════════════════

@app.route('/api/strongest-index')
def api_strongest_index():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    params_str = request.args.get('params', '{}')
    try: params = json.loads(params_str)
    except: params = {}

    db = get_db()
    pools_cfg = load_index_pools()
    conditions = params.get('conditions', {})
    auto_relax = params.get('auto_relax', True)
    relax_step = params.get('relax_step', 5)
    pool_top_n = {'market': 3, 'sector_l1': 5, 'sector_l2': 10, 'thematic': 50, 'strategy': 20}
    pool_labels = {'market': '市场指数', 'sector_l1': '一级行业', 'sector_l2': '二级行业', 'thematic': '主题指数', 'strategy': '策略指数'}

    def check(r, rs20_thr):
        if conditions.get('rs_250',{}).get('enabled',True) and (r['rs_20']or 0) >= 0 and (r['rs_250']or 0) < conditions['rs_250'].get('threshold',80): return False
        if conditions.get('rs_60',{}).get('enabled',True) and (r['rs_60']or 0) < conditions['rs_60'].get('threshold',85): return False
        if conditions.get('rs_20',{}).get('enabled',True) and (r['rs_20']or 0) < rs20_thr: return False
        if conditions.get('ma_align',{}).get('enabled',True) and not ((r['ma50']or 0) > (r['ma150']or 0) > (r['ma200']or 0)): return False
        if conditions.get('ad_slope',{}).get('enabled',True) and (r['ad_slope_20d']or 0) <= 0: return False
        return True

    result_pools = {}
    for pn, codes in pools_cfg.items():
        if pn not in pool_top_n: continue
        tn = pool_top_n[pn]
        ph = ','.join(['?' for _ in codes])
        # 先取最新有数据的日期
        latest = db.execute("SELECT MAX(date) as d FROM index_rs_daily WHERE date <= ?", (target_date,)).fetchone()
        if not latest or not latest['d']: continue
        ldate = latest['d']
        rows = db.execute(f"SELECT * FROM index_rs_daily WHERE date = ? AND stock_code IN ({ph})", [ldate] + codes).fetchall()

        rs20_thr = conditions.get('rs_20',{}).get('threshold', 90)
        flt = [r for r in rows if check(r, rs20_thr)]
        relaxed = False
        if auto_relax and len(flt) < tn:
            r2 = rs20_thr - relax_step
            if r2 >= 60:
                flt = [r for r in rows if check(r, r2)]
                rs20_thr = r2; relaxed = True
        flt.sort(key=lambda x: (x['rs_20']or 0, x['rs_60']or 0, x['rs_250']or 0), reverse=True)
        flt = flt[:tn]
        result_pools[pn] = {'top_n': tn, 'total': len(rows), 'relaxed': relaxed, 'applied_rs20': int(rs20_thr),
            'indices': [{'code': r['stock_code'], 'name': '', 'rs_20': r['rs_20'], 'rs_60': r['rs_60'],
            'rs_250': r['rs_250'], 'ma50': r['ma50'], 'ma150': r['ma150'], 'ma200': r['ma200'],
            'ad_slope': round(r['ad_slope_20d']or 0,1)} for r in flt]}

    idx_names = load_index_names()
    for pd in result_pools.values():
        for s in pd['indices']: s['name'] = idx_names.get(s['code'], s['code'])

    # ── 全量指数数据（供复核表格） ──
    # ── 全量指数数据（供复核表格） ──
    all_rows = db.execute(f"""
        SELECT * FROM index_rs_daily
        WHERE date = (SELECT MAX(date) FROM index_rs_daily WHERE date <= ?)
        ORDER BY rs_20 DESC
    """, (target_date,)).fetchall()

    # code→pool_type 映射
    code_pool = {}
    for pn, codes in pools_cfg.items():
        for c in codes: code_pool[c] = pool_labels.get(pn, pn)

    all_indices = []
    for r in all_rows:
        all_indices.append({
            'code': r['stock_code'], 'name': idx_names.get(r['stock_code'], r['stock_code']),
            'pool': code_pool.get(r['stock_code'], ''),
            'rs_20': r['rs_20'], 'rs_60': r['rs_60'], 'rs_250': r['rs_250'],
            'ret_20': round(r['ret_20'] or 0, 2), 'ret_60': round(r['ret_60'] or 0, 2),
            'ma50': round(r['ma50'] or 0, 0), 'ma150': round(r['ma150'] or 0, 0), 'ma200': round(r['ma200'] or 0, 0),
            'ad_slope': round(r['ad_slope_20d'] or 0, 1),
        })

    return jsonify({'date': target_date, 'pools': result_pools, 'all_indices': all_indices})

# ═══════════════════════════════════════════════
# API: GET /api/stock-name
# ═══════════════════════════════════════════════

@app.route('/api/stock-name')
def api_stock_name():
    code = request.args.get('code', '')
    mode = request.args.get('mode', '')  # 'stock'|'index'|''=auto
    if not code: return jsonify({})
    db = get_db()
    if mode != 'index':
        r = db.execute("SELECT name FROM stock_basic WHERE stock_code=?", (code,)).fetchone()
        if r: return jsonify({'code': code, 'name': r['name']})
    # fallback: index names from index_style.yaml
    idx_names = load_index_names()
    nm = idx_names.get(code, '')
    return jsonify({'code': code, 'name': nm})

# ═══════════════════════════════════════════════
# API: POST /api/pocket-pivot
# ═══════════════════════════════════════════════

@app.route('/api/pocket-pivot', methods=['POST', 'OPTIONS'])
def api_pocket_pivot():
    if request.method == 'OPTIONS': return '', 204
    data = request.get_json()
    stock_code = data.get('stock_code', '600519')
    start = data.get('start', '2023-01-01')
    end = data.get('end', datetime.now().strftime('%Y-%m-%d'))
    params = data.get('params', {})
    mode = data.get('mode', 'stock')
    period = data.get('period', 'day')  # day/week/month

    db = get_db()
    table = 'index_daily_kline' if mode == 'index' else 'daily_kline'
    kf = "AND kline_type='normal'" if mode == 'index' else ''
    # 月线需要更长历史
    extra = '-600 days' if period == 'month' else '-300 days'
    rows = db.execute(f"""SELECT date, open, high, low, close, volume, amount FROM {table}
        WHERE stock_code=? {kf} AND date>=date(?,?) AND date<=? ORDER BY date""",
        (stock_code, start, extra, end)).fetchall()
    if not rows: return jsonify({'klines':[],'signals':[]})

    klines_full = [dict(r) for r in rows]

    # ── 日→周/月聚合 ──
    if period != 'day':
        klines_full = _aggregate_klines(klines_full, period)

    merged = {}
    cfg_path = os.path.join(PROJECT_DIR, 'config', 'market', 'pocket_pivot.yaml')
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        merged.update(cfg.get('pocket_pivot', {}))
    merged.update(params.get('pocket_pivot', params))

    from scanners.pocket_pivot import detect, get_rs
    rs_info = get_rs(db, stock_code, end, mode)
    signals = detect(klines_full, merged, rs_info)
    # 为每个信号日补上当日真实的 RS 值
    for s in signals:
        sd_rs = get_rs(db, stock_code, s['date'], mode)
        if sd_rs:
            s['rs_20'] = sd_rs['rs_20']
            s['rs_250'] = sd_rs['rs_250']
    klines_out = [k for k in klines_full if start <= k['date'] <= end]
    signals_out = [s for s in signals if start <= s['date'] <= end]
    return jsonify({'klines': klines_out, 'signals': signals_out})


def _aggregate_klines(klines, period):
    """日K线聚合为周K或月K"""
    if not klines: return []
    result = []
    group_key = None; current = None
    for k in klines:
        d = k['date']
        if period == 'week':
            from datetime import datetime
            dt = datetime.strptime(d, '%Y-%m-%d')
            iso = dt.isocalendar()
            gk = f"{iso[0]}-W{iso[1]:02d}"
        else:
            gk = d[:7]
        if gk != group_key:
            if current: result.append(current)
            current = {'date': d, 'open': k['open'], 'high': k['high'], 'low': k['low'], 'close': k['close'], 'volume': k['volume'] or 0, 'amount': k.get('amount') or 0}
            group_key = gk
        else:
            current['high'] = max(current['high'], k['high'])
            current['low'] = min(current['low'], k['low'])
            current['close'] = k['close']
            current['volume'] = (current['volume'] or 0) + (k['volume'] or 0)
            current['amount'] = (current['amount'] or 0) + (k.get('amount') or 0)
    if current: result.append(current)
    return result


@app.route('/api/flat-base', methods=['POST', 'OPTIONS'])
def api_flat_base():
    if request.method == 'OPTIONS': return '', 204
    data = request.get_json()
    stock_code = data.get('stock_code', '600519')
    start = data.get('start', '2023-01-01')
    end = data.get('end', datetime.now().strftime('%Y-%m-%d'))
    period = data.get('period', 'day')
    params = data.get('params', {})
    db = get_db()
    extra = '-900 days' if period == 'month' else '-400 days'
    rows = db.execute(f"""SELECT date, open, high, low, close, volume, amount FROM daily_kline
        WHERE stock_code=? AND date>=date(?,?) AND date<=? ORDER BY date""",
        (stock_code, start, extra, end)).fetchall()
    if not rows: return jsonify({'klines':[],'signals':[]})
    klines_full = [dict(r) for r in rows]
    if period != 'day': klines_full = _aggregate_klines(klines_full, period)
    from scanners.flat_base import detect, load_params
    merged = load_params()
    cfg_path = os.path.join(PROJECT_DIR, 'config', 'market', 'flat_base.yaml')
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        merged.update(cfg.get('flat_base', {}))
    merged.update(params.get('flat_base', params))
    signals = detect(klines_full, merged)
    klines_out = [k for k in klines_full if start <= k['date'] <= end]
    signals_out = [s for s in signals if start <= s['date'] <= end]
    return jsonify({'klines': klines_out, 'signals': signals_out})


@app.route('/api/double-bottom', methods=['POST', 'OPTIONS'])
def api_double_bottom():
    if request.method == 'OPTIONS': return '', 204
    data = request.get_json()
    stock_code = data.get('stock_code', '600519')
    start = data.get('start', '2023-01-01')
    end = data.get('end', datetime.now().strftime('%Y-%m-%d'))
    period = data.get('period', 'day')
    mode = data.get('mode', 'stock')
    params = data.get('params', {})
    db = get_db()
    table = 'index_daily_kline' if mode == 'index' else 'daily_kline'
    kf = "AND kline_type='normal'" if mode == 'index' else ''
    extra = '-600 days' if period == 'month' else '-400 days'
    rows = db.execute(f"""SELECT date, open, high, low, close, volume, amount FROM {table}
        WHERE stock_code=? {kf} AND date>=date(?,?) AND date<=? ORDER BY date""",
        (stock_code, start, extra, end)).fetchall()
    if not rows: return jsonify({'klines':[],'signals':[]})
    klines_full = [dict(r) for r in rows]
    if period != 'day': klines_full = _aggregate_klines(klines_full, period)
    from scanners.double_bottom import detect, load_params
    merged = load_params()
    cfg_path = os.path.join(PROJECT_DIR, 'config', 'market', 'double_bottom.yaml')
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        merged.update(cfg.get('double_bottom', {}))
    merged.update(params.get('double_bottom', params))
    signals = detect(klines_full, merged)
    klines_out = [k for k in klines_full if start <= k['date'] <= end]
    signals_out = [s for s in signals if start <= s['date'] <= end]
    return jsonify({'klines': klines_out, 'signals': signals_out})


@app.route('/api/pocket-pivot-rs')
def api_pocket_pivot_rs():
    code = request.args.get('code', '')
    date = request.args.get('date', '')
    mode = request.args.get('mode', 'stock')
    if not code or not date: return jsonify({})
    db = get_db()
    from scanners.pocket_pivot import get_rs
    rs = get_rs(db, code, date, mode)
    return jsonify(rs or {'rs_20': None, 'rs_250': None})

# ═══════════════════════════════════════════════
# API: POST /api/breakout
# ═══════════════════════════════════════════════

@app.route('/api/breakout', methods=['POST', 'OPTIONS'])
def api_breakout():
    if request.method == 'OPTIONS': return '', 204
    data = request.get_json()
    stock_code = data.get('stock_code', '600519')
    start = data.get('start', '2023-01-01')
    end = data.get('end', datetime.now().strftime('%Y-%m-%d'))
    mode = data.get('mode', 'stock')
    params = data.get('params', {})

    db = get_db()
    table = 'index_daily_kline' if mode == 'index' else 'daily_kline'
    kf = "AND kline_type='normal'" if mode == 'index' else ''

    rows = db.execute(f"SELECT date, open, high, low, close, volume FROM {table} WHERE stock_code=? {kf} AND date>=date(?,'-200 days') AND date<=? ORDER BY date", (stock_code, start, end)).fetchall()
    if not rows: return jsonify({'klines': [], 'signals': []})

    klines_full = [dict(r) for r in rows]

    merged = {}
    cfg_path = os.path.join(PROJECT_DIR, 'config', 'market', 'breakout.yaml')
    if os.path.exists(cfg_path):
        import yaml
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        merged.update(cfg.get('breakout', {}))
    merged.update(params.get('breakout', params))

    from scanners.breakout_scanner import detect
    signals = detect(klines_full, merged)
    klines_out = [k for k in klines_full if start <= k['date'] <= end]
    signals_out = [s for s in signals if start <= s['date'] <= end]
    return jsonify({'klines': klines_out, 'signals': signals_out})

# ═══════════════════════════════════════════════
# API: GET /api/market-panorama
# ═══════════════════════════════════════════════

@app.route('/api/market-panorama')
def api_market_panorama():
    """大盘扫描看板全景数据，从 market_snapshot_daily 读取"""
    db = get_db()

    snap = db.execute("SELECT * FROM market_snapshot_daily WHERE double_strong IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
    if not snap:
        return jsonify({'status': 'no_data', 'date': datetime.now().strftime('%Y-%m-%d')})

    # 抛盘日
    dc = snap['dist_30d_count'] or 0
    dd = snap['dist_30d_dates'] or ''
    if dc >= 5:
        dist = {'level': 'danger', 'label': f'{dc}个', 'desc': snap['dist_detail'] or f'近30天{dc}个抛盘日({dd})'}
    elif dc >= 3:
        dist = {'level': 'warning', 'label': f'{dc}个', 'desc': snap['dist_detail'] or f'近30天{dc}个抛盘日({dd})'}
    elif dc >= 1:
        dist = {'level': 'ok', 'label': f'{dc}个', 'desc': snap['dist_detail'] or f'近30天{dc}个抛盘日({dd})'}
    else:
        dist = {'level': 'ok', 'label': '0', 'desc': snap['dist_detail'] or '近30天无抛盘日'}
    dist['dates'] = dd

    core = {
        'distribution': dist,
        'ftd': {'level': 'ok' if (snap['ftd_30d_count'] or 0) > 0 else 'warning',
                'label': str(snap['ftd_30d_count'] or 0), 'count': snap['ftd_30d_count'] or 0,
                'dates': snap['ftd_30d_dates'] or '', 'desc': snap['ftd_detail'] or ''},
        'accumulation': {'level': 'ok' if (snap['acc_30d_count'] or 0) > 0 else 'warning',
                        'label': str(snap['acc_30d_count'] or 0), 'count': snap['acc_30d_count'] or 0,
                        'dates': snap['acc_30d_dates'] or '', 'desc': snap['acc_detail'] or ''},
    }

    ch = snap['crowd_high_count'] or 0
    ct = snap['crowd_total'] or 0
    crowd = {
        'high_count': ch, 'total': ct,
        'desc': f'拥挤度≥70的指数{ch}个/{ct}个。' + (
            '多个指数过热，追高风险加大。' if ch>=3 else '指数拥挤度正常。' if ch<=1 else '个别指数偏热，注意区分趋势与泡沫。'
        ),
    }

    stocks = {
        'double_strong': snap['double_strong'] or 0,
        'steady_leader': snap['steady_leader'] or 0,
        'burst': snap['burst'] or 0,
    }

    return jsonify({'date': snap['date'], 'core': core, 'crowding': crowd, 'stocks': stocks,
                    'ad': {'positive': snap['ad_positive_count'] or 0, 'total': snap['ad_total'] or 0,
                           'desc': snap['ad_detail'] or ''},
                    'divergence': {'count': snap['diverge_count'] or 0, 'desc': snap['diverge_detail'] or ''}})

# ═══════════════════════════════════════════════
    klines_out = [k for k in klines_full if start <= k['date'] <= end]
    signals_out = [s for s in signals if start <= s['date'] <= end]
    return jsonify({'klines': klines_out, 'signals': signals_out})


@app.route('/api/market-panorama/compute', methods=['POST'])
def api_market_panorama_compute():
    """手动触发快照计算"""
    import subprocess
    target = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        r = subprocess.run(
            ['python', 'scripts/compute_market_snapshot.py', '--date', target],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=120
        )
        return jsonify({'ok': r.returncode == 0, 'output': r.stdout[-500:] if r.stdout else r.stderr[-200:]})
    except Exception as e:
        return jsonify({'ok': False, 'output': str(e)})

def _save_ad_snapshot(db, result, as_of_date):
    """从AD计算结果中提取摘要，存入 market_snapshot_daily"""
    try:
        positive = 0; total = 0
        for pname, pdata in result.get('pools', {}).items():
            for item in pdata.get('rankings', []):
                r = item.get('rating', '')
                if r:
                    total += 1
                    if r[0] in ('A', 'B'):
                        positive += 1
        if total == 0: return
        pct = round(positive / total * 100)
        desc = f'{positive}/{total}个指数AD评级为正(A/B)，' + (
            '机构资金积极流入，市场支撑强。' if pct >= 60 else
            '机构资金中性偏多，可适度参与。' if pct >= 30 else
            '机构资金偏向流出，谨慎操作。')
        db.execute("""
            INSERT INTO market_snapshot_daily (date, ad_positive_count, ad_total, ad_detail)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET ad_positive_count=excluded.ad_positive_count,
            ad_total=excluded.ad_total, ad_detail=excluded.ad_detail
        """, (as_of_date, positive, total, desc))
        db.commit()
    except Exception as e:
        print(f"[AD snapshot] save error: {e}")


def _save_divergence_snapshot(db, results, as_of_date):
    """从背离计算结果中提取摘要，存入 market_snapshot_daily"""
    try:
        count = sum(1 for r in results if r.get('resonance'))
        if count == 0:
            desc = '当前无指数出现背离共振，市场趋势一致性强。'
        elif count <= 2:
            desc = f'{count}个指数出现背离共振，关注趋势转折可能。'
        else:
            desc = f'{count}个指数出现背离共振，多项指标预警，建议降低仓位。'
        db.execute("""
            INSERT INTO market_snapshot_daily (date, diverge_count, diverge_detail)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET diverge_count=excluded.diverge_count,
            diverge_detail=excluded.diverge_detail
        """, (as_of_date, count, desc))
        db.commit()
    except Exception as e:
        print(f"[Divergence snapshot] save error: {e}")


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
# API: 指数拥挤度回测
# ═══════════════════════════════════════════════

@app.route('/api/crowding/config', methods=['GET', 'POST', 'OPTIONS'])
def api_crowding_config():
    if request.method == 'OPTIONS': return '', 204

    config_path = os.path.join(PROJECT_DIR, 'config', 'index_crowding.yaml')

    if request.method == 'POST':
        raw = request.get_data(as_text=True)
        if raw:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(raw)
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'empty body'}), 400

    # GET
    if os.path.exists(config_path):
        with open(config_path, encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/yaml; charset=utf-8'}
    return jsonify({'weights': {}, 'levels': {}})


@app.route('/api/crowding/backtest', methods=['POST', 'OPTIONS'])
def api_crowding_backtest():
    if request.method == 'OPTIONS': return '', 204

    data = request.get_json() or {}
    weights = data.get('weights', {})
    levels_raw = data.get('levels', {})
    index_codes = data.get('index_codes', [])
    start_date = data.get('start_date', '2025-01-01')
    end_date = data.get('end_date', '2026-05-05')

    # 取前100个指数
    if not index_codes:
        index_codes = DEFAULT_INDEX_CODES[:100] if 'DEFAULT_INDEX_CODES' in dir() else []
    else:
        index_codes = index_codes[:100]

    # 构建权重和等级
    w = {
        'turnover_ratio': weights.get('turnover_ratio', 0.25),
        'turnover_rate': weights.get('turnover_rate', 0.10),
        'margin_balance': weights.get('margin_balance', 0.15),
        'margin_buy': weights.get('margin_buy', 0.10),
        'pe_pct': weights.get('pe_pct', 0.15),
        'pb_pct': weights.get('pb_pct', 0.05),
        'dyr_pct': weights.get('dyr_pct', 0.05),
        'fund_holding': weights.get('fund_holding', 0.15),
    }
    levels = [
        (0, levels_raw.get('low_max', 30), '低拥挤'),
        (levels_raw.get('low_max', 30), levels_raw.get('normal_max', 60), '正常'),
        (levels_raw.get('normal_max', 60), levels_raw.get('elevated_max', 80), '偏高'),
        (levels_raw.get('elevated_max', 80), 101, '高拥挤'),
    ]

    from scanners.index_crowding import compute_for_api
    results = compute_for_api(index_codes, start_date, end_date, w, levels)

    return jsonify({
        'results': results,
        'params': {'weights': w, 'levels': levels_raw},
        'count': len(results),
    })


@app.route('/api/crowding/indices', methods=['GET'])
def api_crowding_indices():
    """返回指数池列表"""
    yaml_path = os.path.join(PROJECT_DIR, 'config', 'index_style.yaml')
    if not os.path.exists(yaml_path):
        return jsonify([])
    try:
        import yaml
        with open(yaml_path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        indices = []
        for cat_name, idx_list in data.get('categories', {}).items():
            for item in idx_list:
                indices.append({
                    'code': item['code'],
                    'name': item['name'],
                    'category': cat_name
                })
        return jsonify(indices)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crowding/latest', methods=['GET'])
def api_crowding_latest():
    """返回所有指数最新拥挤度数据（从 index_crowding_daily 表直接取）"""
    db = get_db()
    date = request.args.get('date', None)
    try:
        if not date:
            date = db.execute("SELECT MAX(date) FROM index_crowding_daily").fetchone()[0]
        # 找到不晚于请求日期且记录最多的快照
        snap = db.execute("""SELECT date, COUNT(*) as cnt FROM index_crowding_daily
            WHERE date <= ? GROUP BY date ORDER BY cnt DESC LIMIT 1""", (date,)).fetchone()
        if not snap or not snap['date']:
            return jsonify({'results': [], 'date': date, 'count': 0})
        date = snap['date']
        rows = db.execute('''
            SELECT stock_code, composite_score, crowd_level,
                   heat_score, flow_score, valuation_score,
                   pe_pct, turnover_ratio_pct
            FROM index_crowding_daily
            WHERE date = ?
            ORDER BY composite_score DESC
        ''', (date,)).fetchall()
        results = [{
            'stock_code': r['stock_code'],
            'composite_score': r['composite_score'],
            'crowd_level': r['crowd_level'],
            'heat_score': r['heat_score'],
            'flow_score': r['flow_score'],
            'valuation_score': r['valuation_score'],
            'pe_pct': r['pe_pct'],
            'turnover_ratio_pct': r['turnover_ratio_pct'],
        } for r in rows]
        return jsonify({'results': results, 'date': date, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════
# API: 个股RS强度
# ═══════════════════════════════════════════════

# ── 个股RS计算缓存 ──
_rs_cache = {}  # {date: polars DataFrame}

@app.route('/api/stock-rs', methods=['GET'])
def api_stock_rs():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 200))
    try:
        from scanners.stock_rs import compute
        import polars as pl
        # 缓存：同一天不重复计算
        if date not in _rs_cache:
            _rs_cache.clear()  # 只保留最新一天
            _rs_cache[date] = compute(target_date=date, start_date=None)
        df = _rs_cache[date]
        latest_date = df["date"].max()
        # 过滤到最新日期，并把 null rps 和有效 rps 分开——防止排序参数导致 null 排前面
        latest = df.filter(pl.col("date") == latest_date)
        valid_rps = latest.filter(pl.col("rps_250").is_not_null()).sort("rps_250", descending=True)
        total_valid = len(valid_rps)
        total_pages = (total_valid + page_size - 1) // page_size if page_size > 0 else 1
        start = (page - 1) * page_size
        page_data = valid_rps.slice(start, page_size)

        results = []
        for row in page_data.iter_rows(named=True):
            results.append({
                'stock_code': row['stock_code'],
                'name': row.get('name', ''),
                'close': row['adj_close'],
                'rps_250': row['rps_250'],
                'rps_120': row['rps_120'],
                'rps_60': row['rps_60'],
                'rps_20': row['rps_20'],
                'double_strong': row['double_strong'],
                'rs_line': round(row['rs_line_norm'], 2) if row['rs_line_norm'] is not None else None,
            })

        stats = {
            'total': len(latest),
            'valid_rps250': total_valid,
            'double_strong_count': latest.filter(pl.col("double_strong").is_not_null()).shape[0],
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        }

        return jsonify({'date': str(latest_date), 'results': results, 'stats': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stock-rs/double-strong', methods=['GET'])
def api_stock_rs_double_strong():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        from scanners.stock_rs import compute, get_double_strong
        import polars as pl
        if date not in _rs_cache:
            _rs_cache.clear()
            _rs_cache[date] = compute(target_date=date, start_date=None)
        df = _rs_cache[date]
        ds = get_double_strong(df)
        latest_date = df["date"].max()
        ds = ds.filter(pl.col("date") == latest_date).filter(pl.col("rps_250").is_not_null()).sort("rps_250", descending=True)

        results = []
        for row in ds.iter_rows(named=True):
            results.append({
                'stock_code': row['stock_code'],
                'name': row.get('name', ''),
                'close': row['adj_close'],
                'rps_250': row['rps_250'],
                'rps_20': row['rps_20'],
                'pattern': row['double_strong'],
            })

        return jsonify({'date': str(latest_date), 'results': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stock-rs/rs-line', methods=['GET'])
def api_stock_rs_line():
    """单只股票RS线历史序列"""
    code = request.args.get('code', '600519')
    start = request.args.get('start', '2024-01-01')
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    try:
        from scanners.stock_rs import compute
        import polars as pl
        cache_key = end + '_' + (start or 'full')
        if cache_key not in _rs_cache:
            if len(_rs_cache) > 2:
                _rs_cache.clear()
            _rs_cache[cache_key] = compute(target_date=end, start_date=start)
        df = _rs_cache[cache_key]
        stock = df.filter((pl.col("stock_code")==code) & (pl.col("date")>=start) & (pl.col("date")<=end)).sort("date")
        if stock.shape[0] == 0:
            return jsonify({'error': f'{code} 无数据'}), 404
        return jsonify({
            'code': code,
            'dates': stock["date"].to_list(),
            'rs_line': [round(x, 2) if x else None for x in stock["rs_line_norm"].to_list()],
            'close': stock["adj_close"].to_list(),
            'rps_250': stock["rps_250"].to_list(),
            'rps_20': stock["rps_20"].to_list(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════
# API: GET /api/valuation — 指数估值分位数据
# ═══════════════════════════════════════════════

@app.route('/api/valuation')
def api_valuation():
    code = request.args.get('code', '000300')
    start = request.args.get('start', '2016-01-01')
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()
    rows = db.execute('''
        SELECT date, pe_ttm, pe_ttm_pct, pb, pb_pct, dyr, dyr_pct
        FROM index_fundamental_daily
        WHERE stock_code = ? AND date >= ? AND date <= ?
        ORDER BY date
    ''', (code, start, end)).fetchall()
    return jsonify({
        'code': code,
        'dates': [r['date'] for r in rows],
        'pe': [r['pe_ttm'] for r in rows],
        'pe_pct': [r['pe_ttm_pct'] for r in rows],
        'pb': [r['pb'] for r in rows],
        'pb_pct': [r['pb_pct'] for r in rows],
        'dyr': [r['dyr'] for r in rows],
        'dyr_pct': [r['dyr_pct'] for r in rows],
    })


@app.route('/api/valuation/fs')
def api_valuation_fs():
    """指数财务数据（年报）"""
    code = request.args.get('code', '000300')
    try:
        import sys, os
        sys.path.insert(0, os.path.join(PROJECT_DIR, 'scripts'))
        from common import api_post
        metrics = [
            'y.m.npatoshopc_ps.t', 'y.m.roe.t',
            'y.ps.oi.t', 'y.ps.op.t', 'y.ps.op_s_r.t',
            'y.ps.np.t', 'y.ps.np_s_r.t',
            'y.ps.da_om.t', 'y.ps.tas.t',
        ]
        raw = api_post('/index/fs/hybrid', {
            'stockCodes': [code], 'metricsList': metrics,
            'startDate': '2016-01-01',
            'endDate': datetime.now().strftime('%Y-%m-%d'),
        })
        raw_sorted = sorted(raw, key=lambda x: x.get('date', ''))
        result = {'code': code, 'dates': [],
            'eps': [], 'roe': [], 'revenue': [], 'op_profit': [],
            'op_margin': [], 'net_profit': [], 'net_margin': [],
            'dividend': [], 'tax': [], 'peg': []}
        for item in raw_sorted:
            dt = item.get('date', '')[:10]
            result['dates'].append(dt[:4] if len(dt)>4 else dt)
            y = item.get('y', {})
            ps = y.get('ps', {})
            m = y.get('m', {})
            def get_nested(d, path):
                for k in path:
                    if not isinstance(d, dict): return d
                    d = d.get(k, {})
                return d if not isinstance(d, dict) else None
            result['eps'].append(get_nested(m, ['npatoshopc_ps','t']))
            result['roe'].append(get_nested(m, ['roe','t']))
            result['revenue'].append(get_nested(ps, ['oi','t']))
            result['op_profit'].append(get_nested(ps, ['op','t']))
            result['op_margin'].append(get_nested(ps, ['op_s_r','t']))
            result['net_profit'].append(get_nested(ps, ['np','t']))
            result['net_margin'].append(get_nested(ps, ['np_s_r','t']))
            result['dividend'].append(get_nested(ps, ['da_om','t']))
            result['tax'].append(get_nested(ps, ['tas','t']))
            result['peg'].append(None)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════
# API: 个股全维度看板
# ═══════════════════════════════════════════════

@app.route('/api/stock-valuation')
def api_stock_valuation():
    """个股估值指标历史：PE/PB/PS/股息率/市值"""
    code = request.args.get('code', '600519')
    start = request.args.get('start', '2016-01-01')
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()
    metrics = ['pe_ttm','pb','ps_ttm','dyr','mc']
    result = {'code': code, 'dates': [], 'pe': [], 'pb': [], 'ps': [], 'dyr': [], 'mc': []}
    rows = db.execute('''
        SELECT date, metric_code, value FROM fundamental_indicator
        WHERE stock_code=? AND date>=? AND date<=?
        AND metric_code IN (?,?,?,?,?)
        ORDER BY date, metric_code
    ''', (code, start, end, *metrics)).fetchall()
    # 按日期聚合
    by_date = {}
    for r in rows:
        d = r['date']
        if d not in by_date: by_date[d] = {}
        by_date[d][r['metric_code']] = r['value']
    for d in sorted(by_date.keys()):
        v = by_date[d]
        result['dates'].append(d)
        result['pe'].append(v.get('pe_ttm'))
        result['pb'].append(v.get('pb'))
        result['ps'].append(v.get('ps_ttm'))
        result['dyr'].append(v.get('dyr'))
        result['mc'].append(v.get('mc'))
    # 股票名称
    name_row = db.execute('SELECT name FROM stock_basic WHERE stock_code=?', (code,)).fetchone()
    result['name'] = name_row['name'] if name_row else code

    # ── 计算十年分位 ──
    def calc_pct(arr, ascending=True):
        """计算每个值在历史中的百分位(0~1)"""
        valid = [(i, v) for i, v in enumerate(arr) if v is not None]
        if len(valid) < 2: return [None]*len(arr)
        sorted_vals = sorted(valid, key=lambda x: x[1], reverse=not ascending)
        n = len(sorted_vals)
        pcts = [None]*len(arr)
        for rank, (idx, _) in enumerate(sorted_vals):
            pcts[idx] = round(rank/(n-1), 4)
        return pcts

    result['pe_pct'] = calc_pct(result['pe'], ascending=True)    # PE越低越便宜
    result['pb_pct'] = calc_pct(result['pb'], ascending=True)
    result['ps_pct'] = calc_pct(result['ps'], ascending=True)
    result['dyr_pct'] = calc_pct(result['dyr'], ascending=False)  # 股息率越高越好

    return jsonify(result)


@app.route('/api/stock-financials')
def api_stock_financials():
    """个股年度财务数据：ROE/毛利率/净利率/EPS/营收增速/净利增速/FCF/资产负债率等"""
    code = request.args.get('code', '600519')
    db = get_db()
    rows = db.execute('''
        SELECT report_date, revenue, revenue_yoy, net_profit, net_profit_yoy,
               gross_margin, roe,
               free_cash_flow, asset_liability_ratio, interest_bearing_debt_ratio,
               current_ratio, quick_ratio, receivables_turnover, inventory_turnover
        FROM stock_financials_annual
        WHERE stock_code=? AND report_date >= '2016-12-31'
        ORDER BY report_date
    ''', (code,)).fetchall()
    result = {'code': code, 'dates': [], 'revenue': [], 'revenue_yoy': [],
              'net_profit': [], 'net_profit_yoy': [], 'gross_margin': [],
              'roe': [], 'eps': [], 'fcf': [], 'debt_ratio': [],
              'interest_debt_ratio': [], 'current_ratio': [], 'quick_ratio': [],
              'receivables_turnover': [], 'inventory_turnover': []}
    for r in rows:
        result['dates'].append(r['report_date'][:4])
        result['revenue'].append(r['revenue'])
        result['revenue_yoy'].append(r['revenue_yoy'])
        result['net_profit'].append(r['net_profit'])
        result['net_profit_yoy'].append(r['net_profit_yoy'])
        result['gross_margin'].append(r['gross_margin'])
        result['roe'].append(r['roe'])
        # EPS = 净利润 / 总股本
        cap_row = db.execute('''SELECT capitalization FROM stock_equity_change
            WHERE stock_code=? AND date <= ? ORDER BY date DESC LIMIT 1''',
            (code, r['report_date'])).fetchone()
        cap = cap_row['capitalization'] if cap_row and cap_row['capitalization'] else None
        eps = (r['net_profit'] / cap) if (r['net_profit'] and cap) else None
        result['eps'].append(eps)
        result['fcf'].append(r['free_cash_flow'])
        result['debt_ratio'].append(r['asset_liability_ratio'])
        result['interest_debt_ratio'].append(r['interest_bearing_debt_ratio'])
        result['current_ratio'].append(r['current_ratio'])
        result['quick_ratio'].append(r['quick_ratio'])
        result['receivables_turnover'].append(r['receivables_turnover'])
        result['inventory_turnover'].append(r['inventory_turnover'])
        # 年度PE = 市值 / 净利润 = (股本 × 年末收盘价) / 净利润
        year_end_price = None
        if cap and r['net_profit']:
            yr = r['report_date'][:4]
            k_row = db.execute('''SELECT close FROM daily_kline
                WHERE stock_code=? AND date >= ? AND date <= ?
                ORDER BY date DESC LIMIT 1''',
                (code, yr+'-12-01', yr+'-12-31')).fetchone()
            if k_row:
                year_end_price = k_row['close']
        annual_pe = (cap * year_end_price / r['net_profit']) if (cap and year_end_price and r['net_profit']) else None
        result.setdefault('annual_pe', []).append(annual_pe)
    return jsonify(result)


# ═══════════════════════════════════════════════
# API: GET /api/index-rs
# ═══════════════════════════════════════════════

def load_index_pools():
    """从 config/index_style.yaml 加载指数分类池定义"""
    if not os.path.exists(INDEX_RS_CONFIG):
        return {}
    if HAS_YAML:
        with open(INDEX_RS_CONFIG, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        categories = data.get('categories', {})
        pools = {}
        for cat_name, indices in categories.items():
            pools[cat_name] = [item['code'] for item in indices]
        return pools
    else:
        # 回退到简易解析
        return _parse_index_yaml_simple()


def _parse_index_yaml_simple():
    """简易YAML解析（无PyYAML时回退）"""
    pools = {}
    current_cat = None
    with open(INDEX_RS_CONFIG, encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if ':' in stripped and not stripped.startswith('-') and 'code:' not in stripped.lower():
                cat_name = stripped.split(':')[0].strip().split('#')[0].strip()
                if cat_name in ('categories', 'meta'):
                    continue
                pools[cat_name] = []
                current_cat = cat_name
            elif current_cat and '- {code:' in stripped:
                m = re.search(r"code:\s*['\"]?([^'\",}]+)", stripped)
                if m:
                    pools[current_cat].append(m.group(1).strip())
    return pools


INDEX_NAMES_MAP = {}

def load_index_names():
    """从 config/index_style.yaml 加载指数代码→名称映射"""
    global INDEX_NAMES_MAP
    if INDEX_NAMES_MAP:
        return INDEX_NAMES_MAP
    if not os.path.exists(INDEX_RS_CONFIG):
        return {}
    if HAS_YAML:
        with open(INDEX_RS_CONFIG, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        for cat_name, indices in data.get('categories', {}).items():
            for item in indices:
                INDEX_NAMES_MAP[item['code']] = item['name']
    else:
        with open(INDEX_RS_CONFIG, encoding='utf-8') as f:
            for line in f:
                m_code = re.search(r"code:\s*['\"]?([^'\",}]+)", line)
                m_name = re.search(r"name:\s*['\"]?([^'\",}]+)", line)
                if m_code and m_name:
                    INDEX_NAMES_MAP[m_code.group(1).strip()] = m_name.group(1).strip()
    return INDEX_NAMES_MAP


@app.route('/api/index-rs')
def api_index_rs():
    """指数RS强度 — 从 index_rs_daily 读取预计算结果"""
    as_of_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    pool_name = request.args.get('pool', None)

    db = get_db()
    all_pools = load_index_pools()
    if not all_pools:
        return jsonify({'error': 'index_style.yaml not found'}), 500

    if pool_name and pool_name in all_pools:
        pools = {pool_name: all_pools[pool_name]}
    else:
        pools = all_pools

    index_names = load_index_names()
    tier_config = load_config('index_rs') or {}
    tier_params = tier_config.get('tiers', {})

    result = {'pools': {}}

    for pname, codes in pools.items():
        ph = ','.join(['?' for _ in codes])
        rows = db.execute(f"""
            SELECT * FROM index_rs_daily WHERE date <= ? AND stock_code IN ({ph})
            AND date = (SELECT MAX(date) FROM index_rs_daily WHERE date <= ?)
        """, [as_of_date] + codes + [as_of_date]).fetchall()

        rankings = []
        for r in rows:
            rankings.append({
                'code': r['stock_code'], 'name': index_names.get(r['stock_code'], r['stock_code']),
                'close': r['close'], 'change_pct': round(r['ret_20'] or 0, 2),
                'RET_20': r['ret_20'], 'RET_60': r['ret_60'], 'RET_120': r['ret_120'], 'RET_250': r['ret_250'],
                'RS_20': r['rs_20'], 'RS_60': r['rs_60'], 'RS_120': r['rs_120'], 'RS_250': r['rs_250'],
            })

        # L1/L2/L3 筛选
        l1, l2, l3 = [], [], []
        l1_cfg = tier_params.get('L1', {}) if tier_params else {}
        l2_cfg = tier_params.get('L2', {}) if tier_params else {}
        l3_cfg = tier_params.get('L3', {}) if tier_params else {}

        for item in rankings:
            if l1_cfg:
                if (item['RS_120'] or 0) >= l1_cfg.get('rs_120', 90) and \
                   (item['RS_250'] or 0) >= l1_cfg.get('rs_250', 85) and \
                   (item['RS_60'] or 0) >= l1_cfg.get('rs_60', 80):
                    l1.append(item)
            if l2_cfg:
                if (item['RS_20'] or 0) >= l2_cfg.get('rs_20', 90):
                    l2.append(item)
            if l3_cfg:
                if (item['RS_60'] or 0) >= l3_cfg.get('rs_60', 70):
                    l3.append(item)

        rankings.sort(key=lambda x: x['RS_120'] or 0, reverse=True)
        top10 = rankings[:10]

        result['pools'][pname] = {
            'rankings': rankings,
            'tiers': {'L1': l1, 'L2': l2, 'L3': l3},
            'top10': top10,
        }

    return jsonify(result)

# ═══════════════════════════════════════════════
# API: GET /api/index-constituents
# ═══════════════════════════════════════════════

@app.route('/api/index-constituents')
def api_index_constituents():
    index_code = request.args.get('index_code', '')
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    if not index_code:
        return jsonify({'error': 'index_code required'}), 400

    db = get_db()

    # 找到指定日期之前最近一个月份快照
    snap = db.execute("""SELECT date FROM index_constituents
        WHERE index_code=? AND date <= ?
        ORDER BY date DESC LIMIT 1""", (index_code, date)).fetchone()

    if not snap:
        return jsonify({'constituents': [], 'snapshot_date': None, 'count': 0})

    snap_date = snap['date']

    # 拉取成分股及权重（权重表仅有前10大，其余显示为—）
    rows = db.execute("""SELECT ic.stock_code, sb.name,
        (SELECT icw.weighting FROM index_constituent_weightings icw
         WHERE icw.index_code = ic.index_code AND icw.stock_code = ic.stock_code
         ORDER BY icw.date DESC LIMIT 1) as weighting
        FROM index_constituents ic
        LEFT JOIN stock_basic sb ON ic.stock_code = sb.stock_code
        WHERE ic.index_code = ? AND ic.date = ?
        ORDER BY weighting DESC NULLS LAST""",
        (index_code, snap_date)).fetchall()

    constituents = [dict(r) for r in rows]

    return jsonify({
        'index_code': index_code,
        'snapshot_date': snap_date,
        'count': len(constituents),
        'constituents': constituents,
    })

# ═══════════════════════════════════════════════
# API: GET /api/index-ad
# ═══════════════════════════════════════════════

@app.route('/api/index-ad')
def api_index_ad():
    as_of_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    pool_name = request.args.get('pool', None)
    window_days = int(request.args.get('window', 65))
    method = request.args.get('method', 'raw')  # raw | zscore

    db = get_db()

    # zscore需要250天历史基线，增加查询窗口
    if method == 'zscore':
        lookback = 500  # 250天基线 + 65天窗口 ≈ 315个交易日 ≈ 500个日历日
    else:
        lookback = window_days * 2 + 30

    # 加载指数分类池
    all_pools = load_index_pools()
    if not all_pools:
        return jsonify({'error': 'index_style.yaml not found or empty'}), 500

    if pool_name and pool_name in all_pools:
        pools = {pool_name: all_pools[pool_name]}
    else:
        pools = all_pools

    # 加载指数名称
    index_names = load_index_names()

    # 收集所有需要的指数代码
    all_codes = set()
    for codes in pools.values():
        all_codes.update(codes)
    code_list = list(all_codes)
    if not code_list:
        return jsonify({'error': 'no indices in pool'}), 400

    # 批量查询K线
    placeholders = ','.join(['?' for _ in code_list])
    rows = db.execute(f"""SELECT k.stock_code, k.date, k.open, k.high, k.low, k.close, k.volume, k.amount, k.change,
        COALESCE(f.to_r, CASE WHEN f.mc > 0 THEN k.amount / f.mc ELSE 0 END) as to_r
        FROM index_daily_kline k
        LEFT JOIN index_fundamental_daily f ON k.stock_code = f.stock_code AND k.date = f.date
        WHERE k.kline_type='normal'
        AND k.stock_code IN ({placeholders})
        AND k.date >= date(?, '-{lookback} days')
        ORDER BY k.stock_code, k.date""",
        code_list + [as_of_date]).fetchall()

    # 按指数代码分组
    pool_klines = {}
    for r in rows:
        code = r['stock_code']
        if code not in pool_klines:
            pool_klines[code] = []
        pool_klines[code].append({
            'date': r['date'],
            'open': r['open'],
            'high': r['high'],
            'low': r['low'],
            'close': r['close'],
            'to_r': r['to_r'],
            'change': r['change'],
        })

    # 调用引擎
    result = detect_index_ad(pool_klines, pools, as_of_date, window_days, method)

    # 补充指数名称和评级含义
    for pname, pdata in result['pools'].items():
        for item in pdata.get('rankings', []):
            item['name'] = index_names.get(item['code'], item['code'])
            if item.get('rating'):
                from detectors.index_ad import RATING_MEANINGS
                item['meaning'] = RATING_MEANINGS.get(item['rating'], '')

    # ── 保存摘要到 market_snapshot_daily ──
    _save_ad_snapshot(db, result, as_of_date)

    return jsonify(result)

# ═══════════════════════════════════════════════
# API: GET /api/stock-analysis
# ═══════════════════════════════════════════════

@app.route('/api/stock-analysis')
def api_stock_analysis():
    stock_code = request.args.get('code', '')
    if not stock_code:
        return jsonify({'error': 'code required'}), 400
    try:
        from analysis.financial import dcf_valuation, comps_analysis, earnings_analysis, three_statement_projection
        def safe(fn, *args):
            try: return fn(*args)
            except Exception as e: return {'error': str(e)}
        dcf = safe(dcf_valuation, stock_code, {'exit_multiple': 8})
        comps = safe(comps_analysis, stock_code)
        earnings = safe(earnings_analysis, stock_code)
        model = safe(three_statement_projection, stock_code)
        return jsonify({'dcf': dcf, 'comps': comps, 'earnings': earnings, 'model': model})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ═══════════════════════════════════════════════
# API: GET /api/index-divergence
# ═══════════════════════════════════════════════

@app.route('/api/index-divergence')
def api_index_divergence():
    as_of_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    pool_name = request.args.get('pool', 'market')
    sensitivity = request.args.get('sensitivity', 'long')

    db = get_db()

    all_pools = load_index_pools()
    if pool_name not in all_pools:
        return jsonify({'error': 'invalid pool'}), 400
    pool_codes = all_pools[pool_name]
    index_names = load_index_names()

    # 如带 _t 参数则跳过缓存，强制重算
    force_refresh = bool(request.args.get('_t', ''))

    # 先查缓存（跳过强制刷新时）
    cached = []
    placeholders = ','.join(['?' for _ in pool_codes])
    if not force_refresh:
        cached = db.execute(f'''SELECT * FROM index_divergence_daily
            WHERE stock_code IN ({placeholders}) AND date = ?''',
            pool_codes + [as_of_date]).fetchall()

    cached_map = {r['stock_code']: r for r in cached}
    all_codes = set(pool_codes)
    missing = all_codes - set(cached_map.keys())

    # 如果全部缓存命中，直接返回
    if not missing:
        results = []
        for r in cached:
            results.append(build_div_result(r, index_names))
        return jsonify({'as_of_date': as_of_date, 'pool': pool_name, 'cached': True, 'indices': results})

    # 批量查询K线
    lookback = 500
    code_list = list(missing)
    ph = ','.join(['?' for _ in code_list])
    rows = db.execute(f'''SELECT stock_code, date, open, high, low, close, volume, amount, change
        FROM index_daily_kline WHERE kline_type='normal'
        AND stock_code IN ({ph})
        AND date >= date(?, '-{lookback} days')
        ORDER BY stock_code, date''',
        code_list + [as_of_date]).fetchall()

    pool_klines = {}
    for r in rows:
        code = r['stock_code']
        if code not in pool_klines:
            pool_klines[code] = []
        pool_klines[code].append(dict(r))

    # 加载配置
    cfg = load_config('divergence')
    vp_cfg = cfg.get('volume_price', {}) if cfg else {}
    rsi_cfg = cfg.get('rsi', {}) if cfg else {}
    macd_cfg = cfg.get('macd', {}) if cfg else {}
    breadth_cfg = cfg.get('breadth', {}) if cfg else {}
    confirm_window = cfg.get('confirm_window', 20) if cfg else 20

    if sensitivity == 'short':
        rsi_cfg = {**rsi_cfg, 'period': 7, 'lookback': 10}
        macd_cfg = {**macd_cfg, 'lookback': 10}
        confirm_window = 10

    # ── 成分股上涨比例预计算 ──
    # 仅对 market/sector_l1/sector_l2 计算（86个指数），其余跳过
    advance_ratios_map = {}
    if pool_name in ('market', 'sector_l1', 'sector_l2'):
        advance_ratios_map = compute_advance_ratios(db, pool_codes, as_of_date)

    results = []
    for code in sorted(missing):
        klines = pool_klines.get(code, [])
        if not klines: continue

        as_of_idx = None
        for i, k in enumerate(klines):
            if k['date'] == as_of_date: as_of_idx = i; break
        if as_of_idx is None:
            for i in range(len(klines)-1, -1, -1):
                if klines[i]['date'] <= as_of_date: as_of_idx = i; break
        if as_of_idx is None: continue

        actual_date = klines[as_of_idx]['date']
        close_val = klines[as_of_idx]['close']

        div_vp = detect_volume_price_divergence(klines, vp_cfg, as_of_idx)
        div_rsi = detect_rsi_divergence(klines, rsi_cfg, as_of_idx)
        div_macd = detect_macd_divergence(klines, macd_cfg, as_of_idx)

        # 成分股背离（仅对有预计算数据的指数）
        div_breadth = None
        if code in advance_ratios_map and advance_ratios_map[code]:
            ar_dict = advance_ratios_map[code]  # {date: ratio}
            div_breadth = detect_breadth_divergence(klines, ar_dict, as_of_idx, breadth_cfg)

        div_vp = confirm_divergence(klines, as_of_idx, div_vp, confirm_window)
        div_rsi = confirm_divergence(klines, as_of_idx, div_rsi, confirm_window)
        div_macd = confirm_divergence(klines, as_of_idx, div_macd, confirm_window)
        div_breadth = confirm_divergence(klines, as_of_idx, div_breadth, min(confirm_window, 10))

        divergences = {'vp': div_vp, 'rsi': div_rsi, 'macd': div_macd, 'breadth': div_breadth}
        resonance_level, alert_text = compute_resonance(divergences, None, None, None)

        db.execute('''INSERT OR REPLACE INTO index_divergence_daily
            (stock_code, date, div_vp_type, div_vp_level, div_vp_strength,
             div_rsi_type, div_rsi_level, div_macd_type, div_macd_level,
             div_breadth_type, div_breadth_level,
             resonance_level, alert_text, close, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime("now","localtime"))''',
            (code, actual_date,
             div_vp['type'] if div_vp else None, div_vp['level'] if div_vp else None, div_vp.get('strength') if div_vp else None,
             div_rsi['type'] if div_rsi else None, div_rsi['level'] if div_rsi else None,
             div_macd['type'] if div_macd else None, div_macd['level'] if div_macd else None,
             div_breadth['type'] if div_breadth else None, div_breadth['level'] if div_breadth else None,
             resonance_level, alert_text, close_val))

        results.append({
            'code': code, 'name': index_names.get(code, code), 'close': close_val,
            'div_vp': {'type': div_vp['type'], 'level': div_vp['level'], 'strength': div_vp.get('strength')} if div_vp else None,
            'div_rsi': {'type': div_rsi['type'], 'level': div_rsi['level']} if div_rsi else None,
            'div_macd': {'type': div_macd['type'], 'level': div_macd['level']} if div_macd else None,
            'div_breadth': {'type': div_breadth['type'], 'level': div_breadth['level']} if div_breadth else None,
            'resonance_level': resonance_level, 'alert_text': alert_text,
        })

    db.commit()

    # 合并缓存结果
    for r in cached:
        if r['stock_code'] not in missing:
            results.append(build_div_result(r, index_names))

    results.sort(key=lambda x: x['code'])
    # ── 保存摘要到 market_snapshot_daily ──
    _save_divergence_snapshot(db, results, as_of_date)

    return jsonify({'as_of_date': as_of_date, 'pool': pool_name, 'indices': results})
    return {
        'code': r['stock_code'], 'name': index_names.get(r['stock_code'], r['stock_code']),
        'close': r['close'],
        'div_vp': {'type': r['div_vp_type'], 'level': r['div_vp_level'], 'strength': r['div_vp_strength']} if r['div_vp_type'] else None,
        'div_rsi': {'type': r['div_rsi_type'], 'level': r['div_rsi_level']} if r['div_rsi_type'] else None,
        'div_macd': {'type': r['div_macd_type'], 'level': r['div_macd_level']} if r['div_macd_type'] else None,
        'div_breadth': {'type': r['div_breadth_type'], 'level': r['div_breadth_level']} if r['div_breadth_type'] else None,
        'resonance_level': r['resonance_level'], 'alert_text': r['alert_text'],
        'rs_rating': r['rs_rating'], 'ad_rating': r['ad_rating'], 'crowd_level': r['crowd_level'],
    }


def compute_advance_ratios(db, index_codes, as_of_date):
    """
    预计算每个指数的每日成分股上涨比例。
    返回 {code: [ratio, ...]} 与 index_daily_kline 等长。
    """
    advance_map = {}

    # 1. 找到最近一次成分股快照
    placeholders = ','.join(['?' for _ in index_codes])
    snapshots = db.execute(f'''SELECT index_code, MAX(date) as snap_date
        FROM index_constituents WHERE index_code IN ({placeholders})
        AND date <= ? GROUP BY index_code''',
        index_codes + [as_of_date]).fetchall()

    snap_map = {r['index_code']: r['snap_date'] for r in snapshots}

    # 2. 对每个指数，取成分股列表 → 查询近65天的日涨跌
    lookback_date = (datetime.strptime(as_of_date, '%Y-%m-%d') - timedelta(days=100)).strftime('%Y-%m-%d')

    for code in index_codes:
        snap_date = snap_map.get(code)
        if not snap_date:
            advance_map[code] = None
            continue

        # 取成分股列表
        constituents = db.execute('''SELECT stock_code FROM index_constituents
            WHERE index_code = ? AND date = ?''', (code, snap_date)).fetchall()
        if not constituents:
            advance_map[code] = None
            continue

        c_codes = [r['stock_code'] for r in constituents]
        c_ph = ','.join(['?' for _ in c_codes])

        # 查询这些成分股的日涨跌
        rows = db.execute(f'''SELECT date, AVG(CASE WHEN change_pct > 0 THEN 1.0 ELSE 0.0 END) as up_ratio
            FROM daily_kline WHERE stock_code IN ({c_ph})
            AND date >= ? AND date <= ?
            GROUP BY date ORDER BY date''',
            c_codes + [lookback_date, as_of_date]).fetchall()

        if not rows:
            advance_map[code] = None
            continue

        # 构建与index_daily_kline对齐的日期列表
        idx_dates = db.execute('''SELECT date FROM index_daily_kline
            WHERE stock_code = ? AND kline_type="normal"
            AND date >= ? AND date <= ? ORDER BY date''',
            (code, lookback_date, as_of_date)).fetchall()

        date_to_ratio = {r['date']: r['up_ratio'] for r in rows}
        advance_map[code] = date_to_ratio  # {date: ratio}

    return advance_map

# ═══════════════════════════════════════════════
# 统一形态扫描 API — /api/pattern-scan
# ═══════════════════════════════════════════════

@app.route('/api/pattern-scan', methods=['GET', 'OPTIONS'])
def api_pattern_scan():
    if request.method == 'OPTIONS':
        return '', 204

    # ── 参数解析 ──
    code = request.args.get('code', '600519')
    start = request.args.get('start', None)
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    period = request.args.get('period', 'daily')
    mode = request.args.get('mode', '')  # 'stock' | 'index' | ''=auto

    db = get_db()

    # ── 确定是股票还是指数 ──
    if mode == 'index':
        is_index = True
    elif mode == 'stock':
        is_index = False
    else:
        is_index = bool(re.match(r'^(sh|sz|cs|cy|)\d{6}$', code) and (
            code.startswith('sh') or code.startswith('sz') or
            code.startswith('cs') or code.startswith('cy')
        ))
    table = 'index_daily_kline' if is_index else 'daily_kline'
    kf = "AND kline_type='normal'" if is_index else ''

    # 获取足够的历史K线（至少2年）
    if start:
        rows = db.execute(f"""SELECT date, open, high, low, close, volume
            FROM {table} WHERE stock_code=? {kf}
            AND date>=date(?, '-750 days') AND date<=?
            ORDER BY date""", (code, start, end)).fetchall()
    else:
        rows = db.execute(f"""SELECT date, open, high, low, close, volume
            FROM {table} WHERE stock_code=? {kf}
            AND date<=?
            ORDER BY date""", (code, end)).fetchall()

    if not rows:
        return jsonify({'code': code, 'error': 'no_data'})

    klines_full = [dict(r) for r in rows]

    # 获取股票名称
    name = code
    if not is_index:
        name_row = db.execute("SELECT name FROM stock_basic WHERE stock_code=?", (code,)).fetchone()
        if name_row:
            name = name_row['name']
    if name == code:
        idx_names = load_index_names()
        nm = idx_names.get(code, '')
        if nm:
            name = nm

    # ── 日→周/月聚合（如需要） ──
    if period == 'monthly':
        klines_full = _aggregate_klines(klines_full, 'month')
    elif period == 'weekly':
        klines_full = _aggregate_klines(klines_full, 'week')

    # ── 计算 TA-Lib 指标（供前端和引擎使用） ──
    indicators = _compute_indicators(klines_full)

    # ── 运行全部引擎 ──
    signals = run_all_engines(klines=klines_full, indicators=indicators)

    # ── 过滤到请求的日期范围 ──
    if start:
        klines_out = [k for k in klines_full if k['date'] >= start]
        signals_out = [s for s in signals if s['date'] >= start]
    else:
        klines_out = klines_full
        signals_out = signals

    # ── 信号统计 ──
    by_source = {}
    bullish = 0
    bearish = 0
    for s in signals_out:
        # 归一化：补齐缺失字段
        if 'type' not in s:
            s['type'] = 'bullish'  # 自研形态引擎默认买入信号
        if 'confidence' not in s:
            s['confidence'] = 'medium'
        if 'pivot' not in s:
            s['pivot'] = None
        if 'details' not in s:
            s['details'] = {}

        src = s['source']
        if src not in by_source:
            by_source[src] = 0
        by_source[src] += 1
        if s['type'] == 'bullish':
            bullish += 1
        else:
            bearish += 1

    # ── 引擎列表 ──
    engine_list = get_engine_list()

    return jsonify({
        'code': code,
        'name': name,
        'period': period,
        'date_range': {
            'start': klines_out[0]['date'] if klines_out else start,
            'end': klines_out[-1]['date'] if klines_out else end,
        },
        'klines': klines_out,
        'indicators': _sanitize_indicators(indicators, len(klines_out)),
        'engines': engine_list,
        'signals': signals_out,
        'signal_stats': {
            'by_source': by_source,
            'total': len(signals_out),
            'bullish': bullish,
            'bearish': bearish,
        },
        'recommendation': generate_recommendation(
            signals_out, indicators, klines_out, name
        ),
    })


def _compute_indicators(klines):
    """计算 TA-Lib 技术指标，返回 dict of lists"""
    n = len(klines)
    if n < 5:
        return {}

    close = np.array([k.get('close') or np.nan for k in klines], dtype=np.float64)
    high = np.array([k.get('high') or np.nan for k in klines], dtype=np.float64)
    low = np.array([k.get('low') or np.nan for k in klines], dtype=np.float64)
    open_ = np.array([k.get('open') or np.nan for k in klines], dtype=np.float64)
    vol = np.array([k.get('volume') or 0 for k in klines], dtype=np.float64)

    result = {}

    # SMA
    for p in [5, 10, 20, 50, 120, 250]:
        sma = talib.SMA(close, p)
        result[f'sma{p}'] = [float(x) if not np.isnan(x) else None for x in sma]

    # BBANDS
    bb_u, bb_m, bb_l = talib.BBANDS(close, 20, 2, 2, 0)
    result['bb_upper'] = [float(x) if not np.isnan(x) else None for x in bb_u]
    result['bb_middle'] = [float(x) if not np.isnan(x) else None for x in bb_m]
    result['bb_lower'] = [float(x) if not np.isnan(x) else None for x in bb_l]

    # ATR
    atr = talib.ATR(high, low, close, 14)
    result['atr14'] = [float(x) if not np.isnan(x) else None for x in atr]

    # RSI
    rsi = talib.RSI(close, 14)
    result['rsi14'] = [float(x) if not np.isnan(x) else None for x in rsi]

    # MACD
    macd, macd_sig, macd_hist = talib.MACD(close, 12, 26, 9)
    result['macd'] = [float(x) if not np.isnan(x) else None for x in macd]
    result['macd_signal'] = [float(x) if not np.isnan(x) else None for x in macd_sig]
    result['macd_hist'] = [float(x) if not np.isnan(x) else None for x in macd_hist]

    # VOL_MA50
    vol_ma = talib.SMA(vol, 50)
    result['vol_ma50'] = [float(x) if not np.isnan(x) else None for x in vol_ma]

    return result


def _sanitize_indicators(indicators, target_len):
    """确保 indicators 长度和 klines_out 对齐。
    klines_out 是 klines_full 按 start 日期过滤后的尾部，
    因此 indicators 也取尾部 target_len 个元素。"""
    result = {}
    for key, arr in indicators.items():
        arr = list(arr)
        if len(arr) < target_len:
            arr = [None] * (target_len - len(arr)) + arr
        else:
            arr = arr[-target_len:]  # 取尾部，与 klines_out 对齐
        result[key] = arr
    return result

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
    print(f"   Detectors: distribution_day, follow_through_day, accumulation, index_rs")
    app.run(host='0.0.0.0', port=8788, debug=False)
