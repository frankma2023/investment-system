/**
 * main.js — Distribution Day Backtest Controller (4-card params)
 * Uses shared/api-client.js and shared/kline-chart.js
 */

// Signal-specific config for kline-chart.js
const DD_SIGNAL_CONFIG = {
  name: '抛盘日',
  colors: { heavy: '#4A148C', standard: '#7B1FA2', special: '#FFB347', reversal: '#FF7043' },
  labels: { heavy: '⚡重抛盘日(×2)', standard: '🔴标准抛盘日', special: '🟡假阳线', reversal: '🟣盘中反转' },
  sizeBoost: { heavy: 24, default: 18 },
};

let currentKlines = [];
let currentSignals = [];
let chartInstance = null;
let savedRunIds = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadIndices();
  setDefaultDates();
  bindEvents();
  initChart();
});

async function loadIndices() {
  try {
    const data = await API.indices();
    const sel = document.getElementById('index-select');
    sel.innerHTML = data.map(d =>
      `<option value="${d.code}">${d.name} (${d.code})</option>`
    ).join('');
    sel.value = '000985';
  } catch (e) {
    console.error('Failed to load indices:', e);
  }
}

function setDefaultDates() {
  document.getElementById('date-start').value = '2024-01-01';
  document.getElementById('date-end').value = '2024-12-31';
}

function bindEvents() {
  document.getElementById('btn-run').addEventListener('click', runBacktest);
  document.getElementById('btn-save').addEventListener('click', saveBacktest);
  document.getElementById('btn-compare').addEventListener('click', toggleCompare);
  document.getElementById('index-select').addEventListener('change', runBacktest);
  document.getElementById('date-start').addEventListener('change', runBacktest);
  document.getElementById('date-end').addEventListener('change', runBacktest);
}

function initChart() {
  chartInstance = initKlineChart('chart-kline');
}

/* ── 4-Card Parameter Reader ── */
function getCardEnabled(id) {
  const btn = document.getElementById(id + '-toggle');
  return btn ? btn.classList.contains('on') : true;
}

function getParams() {
  return {
    cards: {
      card1: {
        enabled: getCardEnabled('card1'),
        decline: parseFloat(document.getElementById('c1-decline')?.value) || -0.10,
        vol: parseFloat(document.getElementById('c1-vol')?.value) || 1.00,
      },
      card2: {
        enabled: getCardEnabled('card2'),
        chg_min: parseFloat(document.getElementById('c2-chg-min')?.value) || -0.30,
        chg_max: parseFloat(document.getElementById('c2-chg-max')?.value) || 0.20,
        surge: parseFloat(document.getElementById('c2-surge')?.value) || 0.50,
        vol: parseFloat(document.getElementById('c2-vol')?.value) || 1.10,
        shadow: parseFloat(document.getElementById('c2-shadow')?.value) || 1.5,
      },
      card3: {
        enabled: getCardEnabled('card3'),
        surge: parseFloat(document.getElementById('c3-surge')?.value) || 0.50,
        vol: parseFloat(document.getElementById('c3-vol')?.value) || 1.10,
        shadow: parseFloat(document.getElementById('c3-shadow')?.value) || 1.5,
        midpt: parseInt(document.getElementById('c3-midpt')?.value) || 50,
      },
      card4: {
        enabled: getCardEnabled('card4'),
        decline: parseFloat(document.getElementById('c4-decline')?.value) || -1.50,
        vol: parseFloat(document.getElementById('c4-vol')?.value) || 0.98,
      }
    }
  };
}

async function runBacktest() {
  const btn = document.getElementById('btn-run');
  btn.disabled = true;
  btn.textContent = '⏳ 计算中...';

  const stockCode = document.getElementById('index-select').value;
  const start = document.getElementById('date-start').value;
  const end = document.getElementById('date-end').value;
  const params = getParams();

  try {
    const data = await API.backtest({ stock_code: stockCode, start, end, params });

    currentKlines = data.klines;
    currentSignals = data.signals;

    renderKlineChart(chartInstance, currentKlines, currentSignals, { signalConfig: DD_SIGNAL_CONFIG });
    updateStats(data.stats);
    renderSignalTable('table-signals', currentSignals);

    btn.textContent = '🔄 重新回测';
  } catch (e) {
    console.error('Backtest failed:', e);
    btn.textContent = '❌ 失败，重试';
  }
  btn.disabled = false;
}

function updateStats(stats) {
  document.getElementById('stat-total').textContent = stats.total_days;
  document.getElementById('stat-signals').textContent = stats.signal_count;
  document.getElementById('stat-standard').textContent = stats.standard_count;
  document.getElementById('stat-special').textContent = stats.special_count;
  document.getElementById('stat-reverse').textContent = stats.reversal_count || 0;
  document.getElementById('stat-heavy').textContent = stats.heavy_count;
}

async function saveBacktest() {
  if (!currentSignals.length) return alert('请先运行回测');

  const name = prompt('回测名称:', `抛盘日回测 ${new Date().toLocaleDateString()}`);
  if (!name) return;

  const stockCode = document.getElementById('index-select').value;
  const start = document.getElementById('date-start').value;
  const end = document.getElementById('date-end').value;
  const params = getParams();
  const stats = {
    total_days: currentKlines.length,
    signal_count: currentSignals.length,
    standard_count: currentSignals.filter(s => s.signal_type === 'standard').length,
    heavy_count: currentSignals.filter(s => s.signal_type === 'heavy').length,
    special_count: currentSignals.filter(s => s.signal_type === 'special').length,
    reversal_count: currentSignals.filter(s => s.signal_type === 'reversal').length,
    weighted_count: currentSignals.reduce((sum, s) => sum + (s.weight||1), 0),
  };

  try {
    const data = await API.save({ name, stock_code: stockCode, start, end, params, signals: currentSignals, stats });
    alert(`✅ 已保存 (ID: ${data.run_id})`);
    loadSavedList();
  } catch (e) {
    console.error('Save failed:', e);
    alert('❌ 保存失败');
  }
}

async function loadSavedList() {
  try {
    const data = await API.list();
    savedRunIds = data;
    const sel1 = document.getElementById('compare-select-1');
    const sel2 = document.getElementById('compare-select-2');
    const opts = data.map(r =>
      `<option value="${r.id}">#${r.id} ${r.name} (${r.signal_count}信号)</option>`
    ).join('');
    sel1.innerHTML = '<option value="">— 选择—</option>' + opts;
    sel2.innerHTML = '<option value="">— 选择—</option>' + opts;
  } catch (e) {
    console.error('Load list failed:', e);
  }
}

function toggleCompare() {
  const panel = document.getElementById('compare-panel');
  const isOpen = panel.style.display === 'block';
  panel.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) loadSavedList();
  document.getElementById('btn-compare').textContent = isOpen ? '📊 对比' : '✖ 关闭对比';
}

/* ── Slider sync: called from HTML oninput ── */
window.syncSlider = function(id) {
  const el = document.getElementById(id);
  const v = document.getElementById(id + '-v');
  if (!el || !v) return;
  const val = parseFloat(el.value);
  if (id.includes('decline') || id.includes('chg-min') || id.includes('chg-max')) {
    v.textContent = (val >= 0 ? '+' : '') + val.toFixed(2) + '%';
  } else if (id.includes('shadow')) {
    v.textContent = val.toFixed(1) + '×';
  } else if (id.includes('vol')) {
    v.textContent = val.toFixed(2);
  } else if (id.includes('surge')) {
    v.textContent = val.toFixed(2) + '%';
  }
};

// Integer slider variant (no decimals)
window.syncSliderInt = function(id) {
  const el = document.getElementById(id);
  const v = document.getElementById(id + '-v');
  if (!el || !v) return;
  v.textContent = el.value + '%';
};

// Auto-run on page load
setTimeout(runBacktest, 500);
