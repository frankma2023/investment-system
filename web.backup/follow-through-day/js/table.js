/**
 * table.js — Follow-Through Day Signal Table
 * 展示追盘日信号明细，支持排序
 */

function renderFTDTable(containerId, signals) {
  const wrapper = document.getElementById(containerId);
  if (!wrapper) return;

  const labels = {
    normal: '🔴 追盘日',
  };

  let html = `<table class="data-table">
    <thead><tr>
      <th>FTD日期</th><th>状态</th><th>反弹尝试日</th><th>D+天数</th>
      <th>涨幅</th><th>收盘价</th><th>成交量</th>
      <th>收盘位置</th><th>5日波动</th><th>10日波动</th><th>20日波动</th>
      <th>失败原因</th>
    </tr></thead><tbody>`;

  signals.forEach(s => {
    const cls = (s.gain_pct >= 0) ? 'text-up' : 'text-down';
    const failed = s.failed;
    const status = failed ? '❌ 已失效' : '✅ 有效';
    const rowStyle = failed ? ' style="opacity:0.6"' : '';

    html += `<tr${rowStyle}>
      <td>${s.date}</td>
      <td>${status}</td>
      <td>${s.rally_date || '—'}</td>
      <td>${s.days_from_d1 != null ? 'D+' + s.days_from_d1 : '—'}</td>
      <td class="${cls}">${fmtPct(s.gain_pct)}</td>
      <td>${fmtN(s.close)}</td>
      <td>${fmtVol(s.volume)}</td>
      <td>${s.close_position != null ? s.close_position + '%' : '—'}</td>
      <td>${fmtPct2(s.vol_5d)}</td><td>${fmtPct2(s.vol_10d)}</td><td>${fmtPct2(s.vol_20d)}</td>
      <td style="font-size:0.7rem;color:var(--text-tertiary)">${s.failure_reason || ''}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  wrapper.innerHTML = signals.length ? html : '<div style="padding:32px;text-align:center;color:#999">暂无追盘日信号</div>';
  initSortableTable(containerId);
}

function fmtN(v) { return (v != null) ? v.toFixed(2) : '—'; }
function fmtPct(v) { return (v != null) ? (v>=0?'+':'') + v.toFixed(2) + '%' : '—'; }
function fmtPct2(v) { return (v != null) ? (v*100).toFixed(2) + '%' : '—'; }
function fmtVol(v) {
  if (v == null) return '—';
  if (v >= 1e8) return (v/1e8).toFixed(2) + '亿';
  if (v >= 1e4) return (v/1e4).toFixed(0) + '万';
  return v.toString();
}

// Sortable table
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
  const isNum = col >= 3; // numeric columns (D+天数 and beyond)
  const dir = table.dataset.sortCol === String(col) && table.dataset.sortDir === 'asc' ? -1 : 1;
  table.dataset.sortCol = col;
  table.dataset.sortDir = dir === 1 ? 'asc' : 'desc';

  rows.sort((a, b) => {
    let va = a.cells[col].textContent.replace(/[^0-9.\-]/g,'');
    let vb = b.cells[col].textContent.replace(/[^0-9.\-]/g,'');
    if (isNum && va && vb) return (parseFloat(va) - parseFloat(vb)) * dir;
    return va.localeCompare(vb) * dir;
  });
  rows.forEach(r => tbody.appendChild(r));
}
