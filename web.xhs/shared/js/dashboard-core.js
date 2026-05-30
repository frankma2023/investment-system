/* ═══════════════════════════════════════════════════════
   DASHBOARD-CORE.JS — 看板共享 JS 模块
   依赖：ECharts（通过 <script src> 引入）
   使用：引入后调用 Dashboard.init({...}) 即可
   ═══════════════════════════════════════════════════════ */
var Dashboard = window.Dashboard || {};

/* ── Theme Toggle ── */
Dashboard.themeKey = 'dashboard-theme';

Dashboard.toggleTheme = function() {
  var html = document.documentElement;
  var next = html.dataset.theme === 'dark' ? 'light' : 'dark';
  html.dataset.theme = next;
  var btn = document.querySelector('.theme-btn');
  if (btn) btn.textContent = next === 'dark' ? '☀' : '☾';
  localStorage.setItem(Dashboard.themeKey, next);
  if (Dashboard._onThemeChange) Dashboard._onThemeChange();
};

Dashboard.initTheme = function(defaultTheme, onThemeChange) {
  defaultTheme = defaultTheme || 'dark';
  Dashboard.themeKey = (defaultTheme === 'dark' ? 'bbg' : 'neo') + '-theme';
  Dashboard._onThemeChange = onThemeChange;
  var saved = localStorage.getItem(Dashboard.themeKey) || defaultTheme;
  document.documentElement.dataset.theme = saved;
  var btn = document.querySelector('.theme-btn');
  if (btn) btn.textContent = saved === 'dark' ? '☀' : '☾';
};

Dashboard.isDark = function() {
  return document.documentElement.dataset.theme === 'dark';
};

/* ── Mock K-line Data (200 trading days) ── */
Dashboard.generateKline = function(basePrice) {
  basePrice = basePrice || 3800;
  var data = [], o = basePrice, h, l, c, vol;
  var start = new Date(2025, 6, 1);
  for (var i = 0; i < 200; i++) {
    var d = new Date(start); d.setDate(d.getDate() + i);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    var chg = (Math.random() - 0.48) * 2.5;
    var hlR = o * (0.005 + Math.random() * 0.025);
    h = o + hlR * (0.3 + Math.random() * 0.7);
    l = o - hlR * (0.3 + Math.random() * 0.7);
    c = o * (1 + chg / 100); c = Math.max(l, Math.min(h, c));
    vol = (0.6 + Math.random() * 2.5) * 1e8;
    if (i > 160 && i < 170 && Math.random() < 0.3) { c = o * 0.985; h = o * 1.005; l = c * 0.99; vol *= 1.6; }
    if (i > 180 && i < 190) { c = o * (1.01 + Math.random() * 0.03); vol *= 1.5; }
    data.push({
      date: d.toISOString().split('T')[0],
      open: +o.toFixed(2), close: +c.toFixed(2),
      high: +h.toFixed(2), low: +l.toFixed(2),
      volume: Math.round(vol),
      turnover: (vol * 0.008).toFixed(0),
      turnoverRate: (0.3 + Math.random() * 1.2).toFixed(2)
    });
    o = c;
  }
  return data;
};

Dashboard.calcMA = function(data, field, period) {
  return data.map(function(_, i) {
    if (i < period - 1) return null;
    var sum = 0;
    for (var j = i - period + 1; j <= i; j++) sum += data[j][field];
    return +(sum / period).toFixed(2);
  });
};

/* ── ECharts Color Helper ── */
Dashboard.chartColors = function(themeObj) {
  var dark = Dashboard.isDark();
  return {
    up: themeObj.up && themeObj.up[0] ? themeObj.up[0] : (dark ? '#ff4466' : '#d43050'),
    dn: themeObj.dn && themeObj.dn[0] ? themeObj.dn[0] : (dark ? '#00e676' : '#1a8a40'),
    upBorder: themeObj.up && themeObj.up[1] ? themeObj.up[1] : (dark ? '#e03050' : '#b82840'),
    dnBorder: themeObj.dn && themeObj.dn[1] ? themeObj.dn[1] : (dark ? '#00c860' : '#148030'),
    axis: themeObj.axis || (dark ? '#306090' : '#80a0b8'),
    split: themeObj.split || (dark ? 'rgba(0,200,255,0.06)' : 'rgba(0,140,200,0.08)'),
    text: themeObj.text || (dark ? '#6898c0' : '#3a5a7a'),
    ma: themeObj.ma || ['#ffab00','#00e5ff','#b388ff','#ff6e40','#40c4ff','#8d6e63'],
    tooltipBg: dark ? 'rgba(5,8,15,0.75)' : 'rgba(238,242,248,0.78)',
    tooltipBorder: dark ? 'rgba(0,200,255,0.15)' : 'rgba(0,140,200,0.15)',
    tooltipText: dark ? '#e0f0ff' : '#0a1620'
  };
};

/* ── Build K-line Chart ── */
Dashboard.buildKline = function(domId, kdata, themeObj, tooltipFn) {
  var dom = document.getElementById(domId);
  if (!dom) return null;
  if (dom._echart) dom._echart.dispose();
  var ch = echarts.init(dom, null, { devicePixelRatio: 2 });
  var tc = Dashboard.chartColors(themeObj);
  var raw = kdata;
  var dates = raw.map(function(d) { return d.date; });
  var ohlc = raw.map(function(d) { return [d.open, d.close, d.low, d.high]; });
  var vols = raw.map(function(d) { return d.volume; });
  var mas = {};
  [5,10,20,50,120,250].forEach(function(p) { mas[p] = Dashboard.calcMA(raw, 'close', p); });

  var defaultTooltip = function(ps) {
    var d = raw[ps[0].dataIndex];
    var chg = (d.close - d.open).toFixed(2);
    var cp = ((d.close - d.open) / d.open * 100).toFixed(2);
    var cl = d.close >= d.open ? tc.up : tc.dn;
    return '<div style="font-size:12px;font-weight:700;color:'+tc.ma[1]+';margin-bottom:6px;">◆ '+d.date+'</div>'
      +'<div>开盘 <b>'+d.open+'</b> &nbsp; 最高 <b style="color:'+tc.up+'">'+d.high+'</b> &nbsp; 最低 <b style="color:'+tc.dn+'">'+d.low+'</b></div>'
      +'<div>收盘 <b>'+d.close+'</b> &nbsp; 涨跌 <b style="color:'+cl+'">'+chg+' ('+cp+'%)</b></div>'
      +'<div style="margin-top:4px;">成交量 <b>'+((d.volume/1e8).toFixed(2))+'亿</b> &nbsp; 成交额 <b>'+((d.turnover/1e8).toFixed(2))+'亿</b></div>'
      +'<div>换手率 <b>'+d.turnoverRate+'%</b></div>';
  };

  ch.setOption({
    backgroundColor: 'transparent', animation: true,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: tc.axis }, label: { backgroundColor: tc.tooltipBg, color: tc.tooltipText } },
      backgroundColor: tc.tooltipBg, borderColor: tc.tooltipBorder,
      textStyle: { color: tc.tooltipText, fontSize: 11, fontFamily: 'Share Tech Mono, monospace' },
      formatter: tooltipFn || defaultTooltip
    },
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    grid: [
      { left: '8%', right: '8%', top: 50, height: '60%' },
      { left: '8%', right: '8%', top: '76%', height: '14%' }
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: tc.axis } }, axisTick: { show: false }, axisLabel: { color: tc.text, fontSize: 9 }, splitLine: { show: false }, boundaryGap: true, axisPointer: { label: { show: false } } },
      { type: 'category', data: dates, gridIndex: 1, axisLine: { lineStyle: { color: tc.axis } }, axisTick: { show: false }, axisLabel: { show: false }, splitLine: { show: false }, boundaryGap: true }
    ],
    yAxis: [
      { scale: true, gridIndex: 0, axisLine: { lineStyle: { color: tc.axis } }, axisTick: { show: false }, splitLine: { lineStyle: { color: tc.split, type: 'dashed' } }, axisLabel: { color: tc.text, fontSize: 9, formatter: function(v) { return v.toFixed(0); } } },
      { scale: true, gridIndex: 1, axisLine: { lineStyle: { color: tc.axis } }, axisTick: { show: false }, splitLine: { lineStyle: { color: tc.split, type: 'dashed' } }, axisLabel: { color: tc.text, fontSize: 8, formatter: function(v) { return (v/1e8).toFixed(1)+'亿'; } } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0,1], start: 50, end: 100 },
      { type: 'slider', xAxisIndex: [0,1], start: 50, end: 100, height: 20, bottom: 8, borderColor: tc.split, backgroundColor: 'rgba(0,0,0,0.2)', fillerColor: 'rgba(0,200,255,0.06)', handleStyle: { color: tc.ma[1] }, textStyle: { color: tc.text, fontSize: 9 } }
    ],
    series: [
      { name: 'K', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: { color: tc.up, color0: tc.dn, borderColor: tc.upBorder, borderColor0: tc.dnBorder }
      },
      { name: '成交量', type: 'bar', data: vols, xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: { color: function(p) { return raw[p.dataIndex].close >= raw[p.dataIndex].open ? tc.up : tc.dn; } }
      }
    ].concat([5,10,20,50,120,250].map(function(p, i) {
      return { name: 'MA'+p, type: 'line', data: mas[p], xAxisIndex: 0, yAxisIndex: 0, smooth: true, symbol: 'none', lineStyle: { width: 1, color: tc.ma[i] } };
    }))
  });
  dom._echart = ch;
  return ch;
};

/* ── Render Stats Strip ── */
Dashboard.renderStats = function(containerId, items) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = items.map(function(x) {
    return '<div class="stat-cell"><div class="stat-label">'+x.label+'</div><div class="stat-value '+ (x.cls||'') +'">'+x.value+'</div></div>';
  }).join('');
};

/* ── Sortable Table ── */
Dashboard.tableSort = { key: null, dir: 'asc' };

Dashboard.renderTable = function(containerId, columns, keys, data, sortKey, sortDir) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var d = [].concat(data);
  if (sortKey) {
    d.sort(function(a, b) {
      var va = isNaN(a[sortKey]) ? a[sortKey] : +a[sortKey];
      var vb = isNaN(b[sortKey]) ? b[sortKey] : +b[sortKey];
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
  }
  var h = '<table class="data-table"><thead><tr>';
  columns.forEach(function(col, i) {
    var cls = sortKey === keys[i] ? (sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc') : '';
    h += '<th class="'+cls+'" onclick="Dashboard.sortTable(\''+containerId+'\',\''+keys[i]+'\')">'+col+'</th>';
  });
  h += '</tr></thead><tbody>';
  d.forEach(function(r) {
    h += '<tr>';
    keys.forEach(function(k, i) {
      var val = r[k];
      var cls = '';
      if (k === 'chg' || k === 'ma50' || k === 'ma200') cls = +val >= 0 ? 'td-up' : 'td-down';
      if (k === 'chg' || k === 'ma50' || k === 'ma200') {
        if (k === 'chg') val = (+val>=0?'+':'') + val + '%';
        else val = (+val>=0?'+':'') + val + '%';
      }
      if (k === 'turnover') val = val + '%';
      if (k === 'mcap') val = val;
      var style = '';
      if (i === 1) style = 'font-weight:600';
      if (k === 'rating') style = 'font-weight:700;color:var(--color-accent)';
      if (i === 0) h += '<td style="'+style+'">'+val+'</td>';
      else h += '<td class="'+cls+'" style="'+style+'">'+val+'</td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table>';
  el.innerHTML = h;
};

Dashboard.sortTable = function(containerId, key) {
  if (Dashboard.tableSort.key === key) {
    Dashboard.tableSort.dir = Dashboard.tableSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    Dashboard.tableSort.key = key; Dashboard.tableSort.dir = 'asc';
  }
  // Callback to page-level render
  if (Dashboard._onTableSort) Dashboard._onTableSort(key, Dashboard.tableSort.dir);
};

/* ── Config Panel ── */
Dashboard.renderConfig = function(containerId, params) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = params.map(function(p) {
    var dv = Number.isInteger(p.val) ? p.val : p.val.toFixed(2);
    return '<div class="config-item"><div class="config-label"><span class="config-name" title="'+p.name+'">'+p.name+'</span><span class="config-val">'+dv+p.unit+'</span></div><input type="range" class="config-slider" min="'+p.min+'" max="'+p.max+'" step="'+p.step+'" value="'+p.val+'" data-unit="'+p.unit+'" oninput="Dashboard.updateConfig(this)"></div>';
  }).join('');
};

Dashboard.updateConfig = function(slider) {
  var v = +slider.value, u = slider.dataset.unit;
  var dv = Number.isInteger(v) ? v : v.toFixed(2);
  slider.closest('.config-item').querySelector('.config-val').textContent = dv + u;
};

/* ── Redraw ── */
Dashboard.redrawCharts = function(ids) {
  ids.forEach(function(id) {
    var d = document.getElementById(id);
    if (d && d._echart) d._echart.dispose();
  });
  if (Dashboard._onRedraw) Dashboard._onRedraw();
};

/* ── Resize Handler ── */
Dashboard.initResize = function() {
  window.addEventListener('resize', function() {
    document.querySelectorAll('.chart-container').forEach(function(d) {
      if (d._echart) d._echart.resize();
    });
  });
};
