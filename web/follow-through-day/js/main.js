/**
 * main.js — Follow-Through Day Backtest Controller
 * Uses shared/api-client.js and shared/kline-chart.js
 */

/* ── FTD signal config for kline-chart ── */
const FTD_SIGNAL_CONFIG = {
  name: '追盘日',
  colors: { normal: '#FF6B6B', volume: '#FF7043', mega: '#E53935' },
  labels: { normal: '🔥 追盘日', volume: '📊 放量追盘日', mega: '💥 巨量追盘日' },
  symbol: 'pin',
  sizeBoost: { default: 20 },
  getTooltipExtra: (kline, signal) => {
    if (!signal) return null;
    const extras = [];
    if (signal.rally_date) {
      extras.push(['Day1', signal.rally_date]);
      extras.push(['天数', 'D+' + signal.days_from_d1]);
    }
    if (signal.failed) {
      extras.push(['状态', '❌ 已失效']);
      if (signal.failure_reason) extras.push(['原因', signal.failure_reason]);
    } else {
      extras.push(['状态', '✅ 有效']);
    }
    return extras;
  },
};

let currentKlines = [];
let currentSignals = [];           // combined active + failed FTDs (from API)
let currentRallyAttempts = [];     // all rally attempts
let currentFailedRally = [];       // failed rally attempts (from API)
let currentFailedFTDs = [];        // failed FTDs only
let chartInstance = null;

document.addEventListener('DOMContentLoaded', async () => {
  await loadIndices();
  setDefaultDates();
  bindEvents();
  initChart();
  setTimeout(runBacktest, 600);
});

async function loadIndices() {
  try {
    const data = await API.indices();
    const sel = document.getElementById('index-select');
    const priority = ['000985', '000300', '000905'];
    const priorityData = data.filter(d => priority.includes(d.code));
    const otherData = data.filter(d => !priority.includes(d.code));
    const sorted = [...priorityData, ...otherData];
    sel.innerHTML = sorted.map(d =>
      `<option value="${d.code}">${d.name} (${d.code})</option>`
    ).join('');
    sel.value = '000985';
  } catch (e) {
    console.error('Failed to load indices:', e);
  }
}

function setDefaultDates() {
  const now = new Date();
  const threeMonthsAgo = new Date(now);
  threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
  document.getElementById('date-end').value = now.toISOString().split('T')[0];
  document.getElementById('date-start').value = threeMonthsAgo.toISOString().split('T')[0];
}

function bindEvents() {
  document.getElementById('btn-run').addEventListener('click', runBacktest);
  document.getElementById('btn-save').addEventListener('click', saveConfig);
  document.getElementById('index-select').addEventListener('change', runBacktest);
  document.getElementById('date-start').addEventListener('change', runBacktest);
  document.getElementById('date-end').addEventListener('change', runBacktest);
}

function initChart() {
  chartInstance = initKlineChart('chart-kline');
}

/* ── Parameter Reader ── */
function getParams() {
  const ma10Enabled = document.getElementById('c3-vol-ma10-toggle').classList.contains('on');
  return {
    rally: {
      new_low_days: parseInt(document.getElementById('c1-new-low').value),
      close_strength: document.getElementById('c1-close-strength').value,
      protection_days: parseInt(document.getElementById('c1-protection').value),
    },
    ftd: {
      window_start: parseInt(document.getElementById('c3-win-start').value),
      window_end: parseInt(document.getElementById('c3-win-end').value),
      min_gain_pct: parseFloat(document.getElementById('c3-min-gain').value),
      min_vol_ratio_prev: parseFloat(document.getElementById('c3-vol-prev').value),
      vol_ratio_ma10_enabled: ma10Enabled,
      vol_ratio_ma10: parseFloat(document.getElementById('c3-vol-ma10').value),
      close_position_min: parseInt(document.getElementById('c3-close-pos').value),
    },
    rally_failure: {
      reset_window_start: parseInt(document.getElementById('c2-reset-start').value),
      reset_window_end: parseInt(document.getElementById('c2-reset-end').value),
      no_ftd_days: parseInt(document.getElementById('c2-no-ftd').value),
    },
    failure: {
      weak_continuation_days: parseInt(document.getElementById('c4-weak-days').value),
      weak_continuation_min_gain: parseFloat(document.getElementById('c4-weak-gain').value),
      distribution_cover_days: parseInt(document.getElementById('c4-dist-days').value),
      distribution_cover_count: parseInt(document.getElementById('c4-dist-count').value),
      retracement_enabled: document.getElementById('c4-retracement-toggle').classList.contains('on'),
    },
  };
}

/* ── Run Backtest ── */
async function runBacktest() {
  const btn = document.getElementById('btn-run');
  btn.disabled = true;
  btn.textContent = '⏳ 计算中...';

  const stockCode = document.getElementById('index-select').value;
  const start = document.getElementById('date-start').value;
  const end = document.getElementById('date-end').value;
  const params = getParams();

  try {
    const data = await API.backtest({
      stock_code: stockCode,
      start: start,
      end: end,
      signal_type: 'follow_through_day',
      params: params,
    });

    currentKlines = data.klines || [];
    currentRallyAttempts = data.rally_attempts || [];
    currentFailedRally = data.failed_rally_attempts || [];
    currentFailedFTDs = data.failed_ftds || [];

    // signals = combined active + failed FTDs (server merges them)
    const allSignals = data.signals || [];
    // Split into active/failed for chart rendering
    const activeFTDs = allSignals.filter(s => !s.failed);
    currentSignals = allSignals;

    // Compute failed rally attempts if not provided by server
    let failedRally = currentFailedRally;
    if (!failedRally.length && currentRallyAttempts.length) {
      const allFtdRallyDates = new Set(allSignals.map(s => s.rally_date).filter(Boolean));
      failedRally = currentRallyAttempts.filter(r => !allFtdRallyDates.has(r.date));
    }

    // Render chart
    renderKlineChart(chartInstance, currentKlines, activeFTDs, {
      signalConfig: FTD_SIGNAL_CONFIG,
      rallyAttempts: currentRallyAttempts,
      failedSignals: currentFailedFTDs,
      failedRallyAttempts: failedRally,
    });

    // Update stats (field names match running server)
    updateStats(data.stats, failedRally.length);

    // Render table
    renderFTDTable('table-signals', allSignals, currentKlines);

    btn.textContent = '🔄 重新回测';
  } catch (e) {
    console.error('Backtest failed:', e);
    btn.textContent = '❌ 失败，重试';
  }
  btn.disabled = false;
}

/* ── Update Stats Cards ── */
function updateStats(stats, failedRallyCount) {
  if (!stats) return;
  document.getElementById('stat-total').textContent = stats.total_days || 0;
  // signal_count in stats = rally_attempts count (running server convention)
  document.getElementById('stat-rally').textContent = stats.rally_attempts_count || stats.signal_count || 0;
  document.getElementById('stat-rally-fail').textContent = stats.failed_rally_count || failedRallyCount || 0;
  document.getElementById('stat-ftd').textContent = ((stats.ftd_count || 0) + (stats.failed_ftd_count || 0)) || 0;
  document.getElementById('stat-ftd-fail').textContent = stats.failed_ftd_count || 0;
}

/* ── Render FTD Signal Table ── */
function renderFTDTable(containerId, signals, klines) {
  const wrapper = document.getElementById(containerId);
  if (!wrapper) return;

  const klineMap = {};
  klines.forEach(k => { klineMap[k.date] = k; });

  const sorted = [...signals].sort((a, b) => a.date.localeCompare(b.date));

  if (!sorted.length) {
    wrapper.innerHTML = '<div style="padding:32px;text-align:center;color:var(--text-tertiary)">暂无追盘日信号</div>';
    return;
  }

  let html = `<table class="data-table">
    <thead><tr>
      <th>反弹尝试日</th>
      <th>追盘日</th>
      <th>D+N</th>
      <th>涨幅</th>
      <th>成交量</th>
      <th>5日波动率</th>
      <th>10日波动率</th>
      <th>20日波动率</th>
      <th>收盘位置</th>
      <th>状态</th>
      <th>失效原因</th>
    </tr></thead><tbody>`;

  sorted.forEach(s => {
    const k = klineMap[s.date] || {};
    const isFailed = s.failed;
    const cls = isFailed ? 'text-down' : 'text-up';
    const statusLabel = isFailed ? '⚫ 已失效' : '✅ 有效';
    const vol = k.volume != null ? fmtVol(k.volume) : '—';
    const vol5d = k.vol_5d != null ? (k.vol_5d).toFixed(2) + '%' : '—';
    const vol10d = k.vol_10d != null ? (k.vol_10d).toFixed(2) + '%' : '—';
    const vol20d = k.vol_20d != null ? (k.vol_20d).toFixed(2) + '%' : '—';
    const reason = (s.failure_reason || '').replace(/"/g, '&quot;');

    html += `<tr>
      <td>${s.rally_date || '—'}</td>
      <td>${s.date}</td>
      <td>D+${s.days_from_d1}</td>
      <td class="${cls}">${fmtPct(s.gain_pct)}</td>
      <td>${vol}</td>
      <td>${vol5d}</td>
      <td>${vol10d}</td>
      <td>${vol20d}</td>
      <td>${s.close_position != null ? s.close_position + '%' : '—'}</td>
      <td class="${cls}">${statusLabel}</td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${reason}">${s.failure_reason || '—'}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  wrapper.innerHTML = html;
  initSortableTable(containerId);
}

/* ── Sortable Table ── */
function initSortableTable(containerId) {
  const wrapper = document.getElementById(containerId);
  if (!wrapper) return;
  const table = wrapper.querySelector('table');
  if (!table) return;
  const headers = table.querySelectorAll('th');
  headers.forEach((th, col) => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => sortTable(table, col));
  });
}

function sortTable(table, col) {
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const isNum = col >= 2 && col <= 8;
  const dir = table.dataset.sortCol === String(col) && table.dataset.sortDir === 'asc' ? -1 : 1;
  table.dataset.sortCol = col;
  table.dataset.sortDir = dir === 1 ? 'asc' : 'desc';

  rows.sort((a, b) => {
    let va = a.cells[col].textContent.replace(/[^0-9.\-]/g, '');
    let vb = b.cells[col].textContent.replace(/[^0-9.\-]/g, '');
    if (isNum) {
      const na = parseFloat(va), nb = parseFloat(vb);
      if (isNaN(na) && isNaN(nb)) return 0;
      if (isNaN(na)) return 1;
      if (isNaN(nb)) return -1;
      return (na - nb) * dir;
    }
    return va.localeCompare(vb) * dir;
  });
  rows.forEach(r => tbody.appendChild(r));
}

function fmtVol(v) {
  if (v == null) return '—';
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
  return v.toString();
}
function fmtPct(v) {
  if (v == null) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
}

/* ── Save Config ── */
async function saveConfig() {
  const btn = document.getElementById('btn-save');
  btn.textContent = '⏳ 保存中...';
  btn.disabled = true;

  const params = getParams();
  const ma10Enabled = params.ftd.vol_ratio_ma10_enabled;

  // Build YAML string matching config file structure
  const yaml = [
    '# 追盘日 Follow-Through Day 参数配置',
    '# 所有阈值可调，通过回测看板实时生效',
    '',
    'rally:',
    `  new_low_days: ${params.rally.new_low_days}`,
    `  close_strength: ${params.rally.close_strength}`,
    `  protection_days: ${params.rally.protection_days}`,
    '',
    'ftd:',
    `  window_start: ${params.ftd.window_start}`,
    `  window_end: ${params.ftd.window_end}`,
    `  min_gain_pct: ${params.ftd.min_gain_pct}`,
    `  min_vol_ratio_prev: ${params.ftd.min_vol_ratio_prev}`,
    `  vol_ratio_ma10_enabled: ${ma10Enabled}`,
    `  vol_ratio_ma10: ${ma10Enabled ? params.ftd.vol_ratio_ma10 : 0.0}`,
    `  close_position_min: ${params.ftd.close_position_min}`,
    '',
    'rally_failure:',
    `  reset_window_start: ${params.rally_failure.reset_window_start}`,
    `  reset_window_end: ${params.rally_failure.reset_window_end}`,
    `  no_ftd_days: ${params.rally_failure.no_ftd_days}`,
    '',
    'failure:',
    `  breakdown_days: 5`,
    `  weak_continuation_days: ${params.failure.weak_continuation_days}`,
    `  weak_continuation_min_gain: ${params.failure.weak_continuation_min_gain}`,
    `  retracement_enabled: ${params.failure.retracement_enabled}`,
    `  min_retracement_pct: 2.0`,
    `  retracement_days: 15`,
    `  retracement_ratio: 0.618`,
    `  distribution_cover_days: ${params.failure.distribution_cover_days}`,
    `  distribution_cover_count: ${params.failure.distribution_cover_count}`,
    '',
    'manual_annotations:',
    '  - rally_date: "2024-09-18"',
    '    ftd_date: "2024-09-24"',
    '',
  ].join('\n');

  try {
    const resp = await fetch(`${API_BASE}/api/config?signal_type=follow_through_day`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: yaml,
    });
    const data = await resp.json();
    if (data.ok) {
      btn.textContent = '✅ 已保存';
      btn.classList.add('saved');
      setTimeout(() => { btn.textContent = '💾 保存配置'; btn.classList.remove('saved'); btn.disabled = false; }, 2000);
    } else {
      throw new Error(data.error || 'unknown');
    }
  } catch (e) {
    console.error('Save config failed:', e);
    btn.textContent = '❌ 保存失败';
    btn.disabled = false;
    setTimeout(() => { btn.textContent = '💾 保存配置'; }, 2000);
  }
}
