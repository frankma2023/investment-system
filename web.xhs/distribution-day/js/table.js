/**
 * backtest-table.js — Distribution Day Signal Table
 * 展示抛盘日信号明细，支持排序
 */

function renderSignalTable(containerId, signals) {
  const wrapper = document.getElementById(containerId);
  if (!wrapper) return;

  const labels = {
    heavy: '⚡重抛盘日', standard: '🔴标准抛盘',
    special: '🟡假阳线', reversal: '🟠反转'
  };

  let html = `<table class="data-table">
    <thead><tr>
      <th>日期</th><th>类型</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th>
      <th>涨跌幅</th><th>成交量</th><th>5日波动</th><th>10日波动</th><th>20日波动</th>
      <th>MA20</th><th>MA50</th>
    </tr></thead><tbody>`;

  signals.forEach(s => {
    const cls = s.change_pct >= 0 ? 'text-up' : 'text-down';
    html += `<tr>
      <td>${s.date}</td>
      <td>${labels[s.signal_type] || s.signal_type}</td>
      <td>${fmtN(s.open)}</td><td>${fmtN(s.high)}</td><td>${fmtN(s.low)}</td><td>${fmtN(s.close)}</td>
      <td class="${cls}">${fmtPct(s.change_pct)}</td>
      <td>${fmtVol(s.volume)}</td>
      <td>${fmtPct2(s.vol_5d)}</td><td>${fmtPct2(s.vol_10d)}</td><td>${fmtPct2(s.vol_20d)}</td>
      <td>${fmtN(s.ma20)}</td><td>${fmtN(s.ma50)}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  wrapper.innerHTML = signals.length ? html : '<div style="padding:32px;text-align:center;color:#999">暂无信号</div>';
  initSortableTable(containerId);
}

function fmtN(v) { return (v != null) ? v.toFixed(2) : '—'; }
function fmtPct(v) { return (v != null) ? (v>=0?'+':'') + v.toFixed(2) + '%' : '—'; }
function fmtPct2(v) { return (v != null) ? (v*100).toFixed(2) + '%' : '—'; }

// Simple sortable table
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
  const isNum = col >= 2; // numeric columns
  const dir = table.dataset.sortCol === String(col) && table.dataset.sortDir === 'asc' ? -1 : 1;
  table.dataset.sortCol = col;
  table.dataset.sortDir = dir === 1 ? 'asc' : 'desc';

  rows.sort((a, b) => {
    let va = a.cells[col].textContent.replace(/[^0-9.\-]/g,'');
    let vb = b.cells[col].textContent.replace(/[^0-9.\-]/g,'');
    if (isNum) return (parseFloat(va) - parseFloat(vb)) * dir;
    return va.localeCompare(vb) * dir;
  });
  rows.forEach(r => tbody.appendChild(r));
}
