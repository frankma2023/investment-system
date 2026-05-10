/**
 * main.js — Accumulation Day Backtest Controller
 * 吸筹日是追盘日的增强变体，使用更严苛的条件过滤
 */
const ACC_SIGNAL_CONFIG = {
  name: '吸筹日',
  colors: { normal: '#F57C00' },
  labels: { normal: '📦 吸筹日' },
  symbol: 'pin',
  sizeBoost: { default: 22 },
  getTooltipExtra: (kline, signal) => {
    if (!signal) return null;
    const extras = [];
    if (signal.rally_date) { extras.push(['Day1', signal.rally_date]); extras.push(['天数', 'D+' + signal.days_from_d1]); }
    extras.push(['涨幅', (signal.gain_pct >= 0 ? '+' : '') + signal.gain_pct.toFixed(2) + '%']);
    extras.push(['量比(前日)', signal.vol_ratio_prev.toFixed(2)]);
    extras.push(['量比(MA20)', signal.vol_ratio_ma20.toFixed(2)]);
    extras.push(['收盘分位', signal.close_position + '%']);
    const checks = [];
    if (signal.met_price) checks.push('价格✓');
    if (signal.met_volume) checks.push('量能✓'); else checks.push('量能✗');
    if (signal.met_close_pos) checks.push('收盘✓'); else checks.push('收盘✗');
    if (signal.met_no_dist) checks.push('无抛盘✓'); else checks.push('有抛盘✗');
    extras.push(['条件', checks.join(' ')]);
    return extras;
  },
};

let currentKlines = [];
let currentSignals = [];
let currentRallyAttempts = [];
let chartInstance = null;
const SIGNAL_TYPE = 'accumulation_day';

document.addEventListener('DOMContentLoaded', async () => {
  await loadIndices();
  setDefaultDates();
  bindEvents();
  initChart();
  await loadConfig();
  setTimeout(runBacktest, 600);
});

async function loadIndices() {
  try {
    const data = await API.indices();
    const sel = document.getElementById('index-select');
    const priority = ['000985', '000300', '000905'];
    const ordered = [...data.filter(d => priority.includes(d.code)), ...data.filter(d => !priority.includes(d.code))];
    sel.innerHTML = ordered.map(d => `<option value="${d.code}">${d.name} (${d.code})</option>`).join('');
    sel.value = '000985';
  } catch (e) { console.error('Failed to load indices:', e); }
}

function setDefaultDates() {
  const now = new Date();
  const ago = new Date(now);
  ago.setFullYear(ago.getFullYear() - 2);
  document.getElementById('date-end').value = now.toISOString().split('T')[0];
  document.getElementById('date-start').value = ago.toISOString().split('T')[0];
}

function bindEvents() {
  document.getElementById('btn-run').addEventListener('click', runBacktest);
  document.getElementById('btn-save').addEventListener('click', saveConfig);
  document.getElementById('index-select').addEventListener('change', runBacktest);
  document.getElementById('date-start').addEventListener('change', runBacktest);
  document.getElementById('date-end').addEventListener('change', runBacktest);
}

function initChart() { chartInstance = initKlineChart('chart-kline'); }

function getParams() {
  return {
    rally: {
      new_low_days: parseInt(document.getElementById('c1-new-low').value),
      close_strength: document.getElementById('c1-close-strength').value,
      protection_days: parseInt(document.getElementById('c1-protection').value),
    },
    accumulation: {
      window_start: parseInt(document.getElementById('c3-win-start').value),
      window_end: parseInt(document.getElementById('c3-win-end').value),
      min_gain_pct: parseFloat(document.getElementById('c3-min-gain').value),
      vol_ratio_prev: parseFloat(document.getElementById('c3-vol-prev').value),
      vol_ratio_ma20: parseFloat(document.getElementById('c3-vol-ma20').value),
      close_position_min: parseInt(document.getElementById('c3-close-pos').value) / 100,
      narrow_range_pct: parseFloat(document.getElementById('c3-narrow').value) / 100,
      require_no_dist: document.getElementById('c3-no-dist-toggle').classList.contains('on'),
    },
    rally_failure: {
      reset_window_start: parseInt(document.getElementById('c2-reset-start').value),
      reset_window_end: parseInt(document.getElementById('c2-reset-end').value),
      no_signal_days: parseInt(document.getElementById('c2-no-signal').value),
    },
  };
}

async function runBacktest() {
  const btn = document.getElementById('btn-run');
  btn.disabled = true; btn.textContent = '⏳ 计算中...';

  const stockCode = document.getElementById('index-select').value;
  const start = document.getElementById('date-start').value;
  const end = document.getElementById('date-end').value;
  const params = getParams();

  // 诊断：显示实际发送的参数
  console.log('🔍 回测参数:', JSON.stringify(params, null, 2));
  const diagEl = document.getElementById('stat-acc');
  if (diagEl) diagEl.title = 'prot=' + params.rally.protection_days + ' dist=' + params.accumulation.require_no_dist;

  try {
    const data = await API.backtest({
      stock_code: stockCode, start, end,
      signal_type: SIGNAL_TYPE, params,
    });

    currentKlines = data.klines || [];
    currentRallyAttempts = data.rally_attempts || [];
    currentSignals = data.signals || [];
    console.log('🔍 API返回:', 'klines='+currentKlines.length, 'signals='+currentSignals.length, 'rallies='+currentRallyAttempts.length);
    if(currentSignals.length) console.log('  信号:', currentSignals.map(function(s){return s.date}).join(','));

    renderKlineChart(chartInstance, currentKlines, currentSignals, {
      signalConfig: ACC_SIGNAL_CONFIG,
      rallyAttempts: currentRallyAttempts,
    });

    updateStats(data.stats);
    renderTable(currentSignals, currentKlines);
    btn.textContent = '🔄 重新回测';
  } catch (e) {
    console.error('Backtest failed:', e);
    btn.textContent = '❌ 失败，重试';
  }
  btn.disabled = false;
}

function updateStats(stats) {
  if (!stats) return;
  document.getElementById('stat-total').textContent = stats.total_days || 0;
  document.getElementById('stat-rally').textContent = stats.rally_attempts_count || stats.signal_count || 0;
  document.getElementById('stat-acc').textContent = stats.accumulation_count || 0;
}

function renderTable(signals, klines) {
  const wrapper = document.getElementById('table-signals');
  if (!signals.length) {
    wrapper.innerHTML = '<div style="padding:32px;text-align:center;color:var(--text-tertiary)">暂无吸筹日信号</div>';
    return;
  }
  const klineMap = {}; klines.forEach(k => { klineMap[k.date] = k; });
  const sorted = [...signals].sort((a, b) => a.date.localeCompare(b.date));

  let html = `<table class="data-table"><thead><tr>
    <th>反弹尝试日</th><th>吸筹日</th><th>D+N</th><th>涨幅</th>
    <th>成交量</th><th>量比(前日)</th><th>量比(MA20)</th><th>收盘分位</th>
    <th>无抛盘</th>
  </tr></thead><tbody>`;

  sorted.forEach(s => {
    const k = klineMap[s.date] || {};
    const vol = k.volume != null ? (k.volume >= 1e8 ? (k.volume / 1e8).toFixed(2) + '亿' : (k.volume / 1e4).toFixed(0) + '万') : '—';
    html += `<tr>
      <td>${s.rally_date || '—'}</td>
      <td>${s.date}</td><td>D+${s.days_from_d1}</td>
      <td class="text-up">${s.gain_pct >= 0 ? '+' : ''}${s.gain_pct.toFixed(2)}%</td>
      <td>${vol}</td>
      <td>${s.vol_ratio_prev.toFixed(2)}</td>
      <td>${s.vol_ratio_ma20.toFixed(2)}</td>
      <td>${s.close_position}%</td>
      <td>${s.met_no_dist ? '✅' : '⚠️'}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  wrapper.innerHTML = html;
  initSortable('table-signals');
}

function initSortable(id) {
  const wrapper = document.getElementById(id), table = wrapper.querySelector('table');
  if (!table) return;
  table.querySelectorAll('th').forEach((th, col) => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const isNum = col >= 2 && col <= 7;
      const dir = table.dataset.sortCol === String(col) && table.dataset.sortDir === 'asc' ? -1 : 1;
      table.dataset.sortCol = col; table.dataset.sortDir = dir === 1 ? 'asc' : 'desc';
      rows.sort((a, b) => {
        let va = a.cells[col].textContent.replace(/[^0-9.\-]/g, ''), vb = b.cells[col].textContent.replace(/[^0-9.\-]/g, '');
        if (isNum) { const na = parseFloat(va), nb = parseFloat(vb); if (isNaN(na) && isNaN(nb)) return 0; if (isNaN(na)) return 1; if (isNaN(nb)) return -1; return (na - nb) * dir; }
        return va.localeCompare(vb) * dir;
      });
      rows.forEach(r => tbody.appendChild(r));
    });
  });
}

async function loadConfig() {
  try {
    const resp = await fetch(`${API_BASE}/api/config?signal_type=accumulation_day`, { cache: 'no-store' });
    const data = await resp.json();
    // API 直接返回解析后的配置 dict
    if (data && (data.rally || data.accumulation)) {
      console.log('配置已加载:', data);
      applyConfigDict(data);
      return;
    }
  } catch (e) { console.log('配置加载失败:', e); }
}

function applyConfigDict(cfg) {
  // rally
  if (cfg.rally) {
    const rm = { new_low_days: 'c1-new-low', close_strength: 'c1-close-strength', protection_days: 'c1-protection' };
    for (const [k, id] of Object.entries(rm)) {
      if (cfg.rally[k] !== undefined) setFieldVal(id, cfg.rally[k]);
    }
  }
  // accumulation
  if (cfg.accumulation) {
    const am = { window_start: 'c3-win-start', window_end: 'c3-win-end', min_gain_pct: 'c3-min-gain', vol_ratio_prev: 'c3-vol-prev', vol_ratio_ma20: 'c3-vol-ma20' };
    for (const [k, id] of Object.entries(am)) {
      if (cfg.accumulation[k] !== undefined) setFieldVal(id, cfg.accumulation[k]);
    }
    if (cfg.accumulation.close_position_min !== undefined)
      setFieldVal('c3-close-pos', Math.round(cfg.accumulation.close_position_min * 100));
    if (cfg.accumulation.narrow_range_pct !== undefined)
      setFieldVal('c3-narrow', Math.round(cfg.accumulation.narrow_range_pct * 100));
    if (cfg.accumulation.require_no_dist !== undefined) {
      const el = document.getElementById('c3-no-dist-toggle');
      if (el) el.className = 'toggle-switch ' + (cfg.accumulation.require_no_dist ? 'on' : 'off');
    }
  }
  // rally_failure
  if (cfg.rally_failure) {
    const fm = { reset_window_start: 'c2-reset-start', reset_window_end: 'c2-reset-end', no_signal_days: 'c2-no-signal' };
    for (const [k, id] of Object.entries(fm)) {
      if (cfg.rally_failure[k] !== undefined) setFieldVal(id, cfg.rally_failure[k]);
    }
  }
}

function setFieldVal(id, val) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.tagName === 'SELECT') { el.value = String(val); return; }
  el.value = val;
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

function runDiagnostic() {
  const date = document.getElementById('diag-date').value;
  const div = document.getElementById('diag-result');
  if (!date || !currentKlines.length) { div.style.display='none'; return; }

  const params = getParams();
  const ac = params.accumulation;
  const klineMap = {}; currentKlines.forEach(function(k){ klineMap[k.date] = k; });
  const k = klineMap[date];
  if (!k) { div.innerHTML='<div style="font-size:0.7rem;color:#FF6B6B">该日期不在回测范围内</div>'; div.style.display='block'; return; }

  // 找该日期在klines中的索引
  var idx = currentKlines.findIndex(function(r){ return r.date === date; });
  var prev = idx > 0 ? currentKlines[idx-1] : null;
  var prev20 = currentKlines.slice(Math.max(0, idx-20), idx);

  // ① 涨幅
  var chg = k.change_pct || 0;
  var c1 = chg >= ac.min_gain_pct;

  // ② 成交量
  var vrPrev = prev && prev.volume > 0 ? k.volume / prev.volume : 0;
  var ma20v = prev20.length ? prev20.reduce(function(s,r){return s+r.volume}, 0) / prev20.length : 0;
  var vrMA20 = ma20v > 0 ? k.volume / ma20v : 0;
  var c2a = vrPrev >= ac.vol_ratio_prev;
  var c2b = vrMA20 >= ac.vol_ratio_ma20;

  // ③ 收盘强度
  var amp = k.close > 0 ? (k.high - k.low) / k.close : 0;
  var pos = k.high !== k.low ? (k.close - k.low) / (k.high - k.low) : 1;
  var c3, c3detail;
  if (k.high === k.low) { c3 = true; c3detail = 'high=low，直接通过'; }
  else if (amp < ac.narrow_range_pct) { c3 = k.close >= k.open; c3detail = '窄幅日('+(amp*100).toFixed(2)+'%<'+ (ac.narrow_range_pct*100).toFixed(2)+'%)→需close>=open'; }
  else { c3 = pos >= ac.close_position_min; c3detail = '正常日→分位>='+ac.close_position_min; }

  // ④ 反弹窗口
  var rallyInfo = '';
  for (var i=0; i<currentRallyAttempts.length; i++) {
    var ra = currentRallyAttempts[i];
    var raIdx = currentKlines.findIndex(function(r){ return r.date === ra.date; });
    if (raIdx < 0) continue;
    var dist = idx - raIdx;
    if (dist >= ac.window_start && dist <= ac.window_end) {
      rallyInfo = '<span style="color:#4CAF50">✅ D+'+dist+' (窗口D+'+ac.window_start+'~'+ac.window_end+')，反弹日='+ra.date+'</span>';
      break;
    } else if (dist > 0 && dist < ac.window_start) {
      rallyInfo = '<span style="color:#FF9800">⚠ D+'+dist+'，窗口未到 (需D+'+ac.window_start+'~'+ac.window_end+')，反弹日='+ra.date+'</span>';
      break;
    } else if (dist > ac.window_end && dist <= 10) {
      rallyInfo = '<span style="color:#FF6B6B">❌ D+'+dist+'，窗口已过 (D+'+ac.window_start+'~'+ac.window_end+')，反弹日='+ra.date+'</span>';
      break;
    }
  }
  if (!rallyInfo) {
    // check if the date itself is a rally day
    var isRally = false;
    for (var ir=0; ir<currentRallyAttempts.length; ir++) {
      if (currentRallyAttempts[ir].date === date) { isRally = true; break; }
    }
    rallyInfo = isRally ? '<span style="color:#FF6B6B">❌ 该日是反弹尝试日(D+0)，不在吸筹窗口内</span>' : '<span style="color:#FF6B6B">❌ 不在任何反弹尝试窗口内</span>';
  }

  // 构建结果表格
  function cell(v){ return '<td style="font-weight:700">'+v+'</td>'; }
  function pass(b, detail){ return b ? '<td style="color:#4CAF50">✅ 通过 · '+detail+'</td>' : '<td style="color:#FF6B6B">❌ 不达标 · '+detail+'</td>'; }

  var tbl = '<table class="data-table" style="margin:0"><thead><tr><th style="width:20%">条件</th><th>实际值</th><th>阈值</th><th style="width:30%">判定</th></tr></thead><tbody>';
  tbl += '<tr>'+cell('① 涨幅')+'<td>'+(chg>=0?'+':'')+chg.toFixed(2)+'%</td><td>≥'+ac.min_gain_pct.toFixed(2)+'%</td>'+pass(c1, '')+'</tr>';
  tbl += '<tr>'+cell('② 量比(前日)')+'<td>'+vrPrev.toFixed(2)+'</td><td>≥'+ac.vol_ratio_prev.toFixed(2)+'</td>'+pass(c2a, k.volume+'/'+prev.volume)+'</tr>';
  tbl += '<tr>'+cell('② 量比(MA20)')+'<td>'+vrMA20.toFixed(2)+'</td><td>≥'+ac.vol_ratio_ma20.toFixed(2)+'</td>'+pass(c2b, 'MA20='+ma20v.toFixed(0))+'</tr>';
  tbl += '<tr>'+cell('③ 收盘强度')+'<td>分位'+pos.toFixed(2)+'</td><td>≥'+ac.close_position_min.toFixed(2)+'</td>'+pass(c3, c3detail)+'</tr>';
  tbl += '<tr>'+cell('④ 反弹窗口')+'<td colspan="2">—</td><td>'+rallyInfo+'</td></tr>';
  var allPass = c1 && c2a && c2b && c3 && rallyInfo.indexOf('✅')>=0;
  tbl += '<tr style="border-top:2px solid var(--divider)"><td style="font-weight:900">综合</td><td colspan="2"></td><td style="font-weight:900;font-size:0.85rem;color:'+(allPass?'#4CAF50':'#FF6B6B')+'">'+(allPass?'🎉 应为吸筹日':'❌ 不满足')+'</td></tr>';
  tbl += '</tbody></table>';

  div.innerHTML = '<div style="font-size:0.65rem;color:var(--text-tertiary);margin-bottom:6px">'+date+' OHLC: '+k.open.toFixed(0)+' / '+k.high.toFixed(0)+' / '+k.low.toFixed(0)+' / '+k.close.toFixed(0)+'</div>'+tbl;
  div.style.display = 'block';
}

async function saveConfig() {
  const btn = document.getElementById('btn-save');
  btn.textContent = '⏳ 保存中...'; btn.disabled = true;
  const p = getParams();
  const noDist = p.accumulation.require_no_dist;
  const yaml = [
    '# 吸筹日 Accumulation Day 参数配置',
    '# 追盘日的增强变体：更严苛的成交量+收盘强度+抛盘日过滤',
    '', 'rally:',
    `  new_low_days: ${p.rally.new_low_days}`,
    `  close_strength: ${p.rally.close_strength}`,
    `  protection_days: ${p.rally.protection_days}`,
    '', 'accumulation:',
    `  window_start: ${p.accumulation.window_start}`,
    `  window_end: ${p.accumulation.window_end}`,
    `  min_gain_pct: ${p.accumulation.min_gain_pct}`,
    `  vol_ratio_prev: ${p.accumulation.vol_ratio_prev}`,
    `  vol_ratio_ma20: ${p.accumulation.vol_ratio_ma20}`,
    `  close_position_min: ${p.accumulation.close_position_min}`,
    `  narrow_range_pct: ${p.accumulation.narrow_range_pct}`,
    `  require_no_dist: ${noDist ? 'true' : 'false'}`,
    '', 'rally_failure:',
    `  reset_window_start: ${p.rally_failure.reset_window_start}`,
    `  reset_window_end: ${p.rally_failure.reset_window_end}`,
    `  no_signal_days: ${p.rally_failure.no_signal_days}`,
    '',
  ].join('\n');
  try {
    const resp = await fetch(`${API_BASE}/api/config?signal_type=${SIGNAL_TYPE}`, {
      method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: yaml,
    });
    const data = await resp.json();
    if (data.ok) {
      btn.textContent = '✅ 已保存'; btn.classList.add('saved');
      setTimeout(() => { btn.textContent = '💾 保存配置'; btn.classList.remove('saved'); btn.disabled = false; }, 2000);
    } else { throw new Error(data.error); }
  } catch (e) {
    console.error('Save failed:', e); btn.textContent = '❌ 保存失败'; btn.disabled = false;
    setTimeout(() => { btn.textContent = '💾 保存配置'; }, 2000);
  }
}
