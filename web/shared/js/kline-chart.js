/**
 * kline-chart.js — Generic ECharts K-line with Signal Markers
 * 小红书 v1 风格 · 可配置信号标记 · DataZoom 缩放 · 深色/浅色自适应
 *
 * Usage:
 *   const chart = initKlineChart('chart-container');
 *   renderKlineChart(chart, klines, signals, { signalConfig });
 *
 * signalConfig = {
 *   name: '抛盘日',
 *   colors: { heavy: '#4A148C', standard: '#7B1FA2', special: '#FFB347', reversal: '#FF7043', ... },
 *   labels: { heavy: '⚡重抛盘日(×2)', standard: '🔴标准抛盘日', ... },
 *   sizeBoost: { heavy: 24, default: 18 },
 *   getTooltipExtra: (kline, signal) => null,  // optional extra tooltip rows
 * }
 */

const MA_COLORS = ['#FFB347','#4FC3F7','#C084FC','#FF8FA3','#60E0C8','#F5C6D0'];

function initKlineChart(containerId) {
  const dom = document.getElementById(containerId);
  if (!dom) return null;
  return echarts.init(dom);
}

function renderKlineChart(chart, klines, signals, opts = {}) {
  const { showMA = [5,10,20,50], showVolume = true, signalConfig = {},
          rallyAttempts = [], failedSignals = [] } = opts;
  const sigColors = signalConfig.colors || {};
  const sigLabels = signalConfig.labels || {};
  const sigSizes  = signalConfig.sizeBoost || {};
  const defaultColor = sigColors.standard || '#7B1FA2';

  // ── Data arrays ──
  const dates   = klines.map(k => k.date);
  const ohlc    = klines.map(k => [k.open, k.close, k.low, k.high]);
  const volumes = klines.map(k => k.volume);

  // Volume colors: match candle (close>=open → coral, close<open → mint)
  const volColors = klines.map(k =>
    (k.close >= k.open) ? 'rgba(255,107,107,0.5)' : 'rgba(38,198,218,0.5)'
  );
  const volBorders = klines.map(k =>
    (k.close >= k.open) ? '#FF6B6B' : '#26C6DA'
  );

  // ── MA series ──
  const maSeries = showMA.map((period, idx) => ({
    name: `MA${period}`,
    type: 'line', data: klines.map(k => k[`ma${period}`]),
    smooth: true, symbol: 'none',
    lineStyle: { width: 1.5, color: MA_COLORS[idx], cap: 'round' },
  }));

  // ── Signal lookup ──
  const signalDates = new Set(signals.map(s => s.date));
  const signalInfo  = {};
  signals.forEach(s => { signalInfo[s.date] = s; });

  // ── Rally Attempt (反弹尝试日) markers — dark green triangles ──
  const rallyDates = new Set(rallyAttempts.filter(r => r.status !== 'failed_d13').map(r => r.date));
  const rallyMarks = {
    name: '反弹尝试日', type: 'scatter',
    symbol: 'triangle', symbolRotate: 180, symbolSize: 12,
    data: klines.map((k, i) => {
      if (!rallyDates.has(k.date)) return null;
      return { value: [i, k.high * 1.03], itemStyle: { color: '#2E7D32', borderColor: '#FFF', borderWidth: 0.8 } };
    }).filter(d => d !== null),
    z: 2,
  };

  // ── Failed FTD lookup ──
  const failedDates = new Set(failedSignals.map(s => s.date));
  const failedInfo  = {};
  failedSignals.forEach(s => { failedInfo[s.date] = s; });

  // ── Signal pin markers ──
  const sigMarks = {
    name: signalConfig.name || '信号',
    type: 'scatter',
    data: klines
      .map((k, i) => {
        const isSignal = signalDates.has(k.date);
        const isFailed = failedDates.has(k.date);
        if (!isSignal && !isFailed) return null;
        const s = isSignal ? signalInfo[k.date] : failedInfo[k.date];
        const st = s.signal_type || 'standard';
        const color = sigColors[st] || defaultColor;
        const size  = sigSizes[st] || sigSizes.default || 18;
        return {
          value: [i, k.low * 0.97],
          signalType: st,
          itemStyle: {
            color: isFailed ? 'rgba(200,200,200,0.5)' : color,
            borderColor: isFailed ? '#999' : '#FFF',
            borderWidth: isFailed ? 0.8 : 1.5,
            borderType: isFailed ? 'dashed' : 'solid',
          },
          symbolSize: isFailed ? 14 : size,
        };
      })
      .filter(d => d !== null),
    symbol: 'pin',
    symbolRotate: 180,
    z: 10,
  };

  // ── Tooltip formatter (NO turnover rate) ──
  const tooltipFormatter = (params) => {
    const idx = params[0]?.dataIndex;
    if (idx == null) return '';
    const k = klines[idx];
    const s = signalInfo[k.date];
    const upDown = k.change_pct >= 0 ? '📈' : '📉';
    const color  = k.change_pct >= 0 ? '#FF6B6B' : '#26C6DA';
    const _isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const _bg   = _isDark ? 'rgba(30,30,46,0.6)' : 'rgba(255,255,255,0.6)';
    const _text = _isDark ? '#E0E0E0' : '#1A1A1A';

    let html = `<div style="font-family:Nunito,PingFang SC,sans-serif;font-size:8px;min-width:200px;background:${_bg};color:${_text};border-radius:8px;padding:4px">
      <div style="font-weight:800;font-size:10px;margin-bottom:4px">${upDown} ${k.date}</div>
      <table style="width:100%;border-collapse:collapse;line-height:1.3">`;

    const rows = [
      ['开盘', k.open?.toFixed(2)], ['最高', k.high?.toFixed(2)],
      ['最低', k.low?.toFixed(2)],   ['收盘', k.close?.toFixed(2)],
      ['涨跌幅', `<span style="color:${color};font-weight:700">${(k.change_pct??0).toFixed(2)}%</span>`],
      ['成交量', fmtVol(k.volume)], ['成交额', fmtAmt(k.amount)],
    ];
    if (k.vol_5d  != null) rows.push(['5日波动率', `${k.vol_5d.toFixed(2)}%`]);
    if (k.vol_10d != null) rows.push(['10日波动率', `${k.vol_10d.toFixed(2)}%`]);
    if (k.vol_20d != null) rows.push(['20日波动率', `${k.vol_20d.toFixed(2)}%`]);
    [5,10,20,50,120,250].forEach(p => {
      const key = `ma${p}`;
      if (k[key] != null) rows.push([`MA${p}`, k[key].toFixed(2)]);
    });

    // Optional extra rows from signalConfig
    if (signalConfig.getTooltipExtra) {
      const extra = signalConfig.getTooltipExtra(k, s);
      if (extra) extra.forEach(r => rows.push(r));
    }

    rows.forEach(r => {
      html += `<tr><td style="color:var(--text-tertiary);padding:0 6px 0 0;line-height:1.3;font-size:8px">${r[0]}</td><td style="text-align:right;font-weight:600;line-height:1.3;font-size:8px">${r[1]}</td></tr>`;
    });

    if (s) {
      const label = sigLabels[s.signal_type] || signalConfig.name || '';
      html += `<tr><td colspan="2" style="padding-top:3px;color:${defaultColor};font-weight:800;font-size:8px;line-height:1.3">${label}</td></tr>`;
    }

    html += '</table></div>';
    return html;
  };

  // ── Theme-aware grid colors ──
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const gridColor     = isDark ? '#2a2a3a' : '#F5F5F5';
  const axisLineColor = isDark ? '#333' : '#E0E0E0';
  const tooltipBg     = isDark ? 'rgba(30,30,46,0.6)' : 'rgba(255,255,255,0.6)';
  const tooltipText   = isDark ? '#E0E0E0' : '#1A1A1A';

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      formatter: tooltipFormatter,
      backgroundColor: tooltipBg,
      borderColor: defaultColor, borderWidth: 1, borderRadius: 14,
      padding: [8, 12], textStyle: { color: tooltipText },
      extraCssText: 'box-shadow: 0 4px 20px rgba(0,0,0,0.07);'
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 60, right: 20, top: 20, height: showVolume ? '58%' : '100%' },
      { left: 60, right: 20, top: '70%', height: '22%' }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0,1], zoomOnMouseWheel: true, moveOnMouseMove: true },
      { type: 'slider', xAxisIndex: [0,1], bottom: 5, height: 22, borderRadius: 6,
        handleStyle: { color: defaultColor },
        dataBackground: { lineStyle: { color: defaultColor }, areaStyle: { color: 'rgba(123,31,162,0.08)' } },
        selectedDataBackground: { lineStyle: { color: '#4A148C' }, areaStyle: { color: 'rgba(74,20,140,0.15)' } },
      },
    ],
    xAxis: [
      { type: 'category', data: dates, axisLine: { lineStyle: { color: axisLineColor } },
        axisLabel: { color: '#999', fontSize: 10, fontFamily: 'Nunito' } },
      { type: 'category', gridIndex: 1, data: dates, axisLine: { lineStyle: { color: axisLineColor } },
        axisLabel: { show: false } },
    ],
    yAxis: [
      { type: 'value', scale: true, splitLine: { lineStyle: { color: gridColor, width: 0.5 } },
        axisLabel: { color: '#999', fontSize: 10 } },
      { type: 'value', gridIndex: 1, axisLabel: { color: '#999', fontSize: 10, formatter: v => fmtVol(v) },
        splitLine: { show: false } },
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: { color: '#FF6B6B', color0: '#26C6DA', borderColor: '#FF6B6B', borderColor0: '#26C6DA', borderRadius: [6,6,0,0] },
      },
      ...maSeries,
      ...(sigMarks.data.length > 0 ? [sigMarks] : []),
      ...(rallyMarks.data.length > 0 ? [rallyMarks] : []),
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
        data: volumes.map((v, i) => ({ value: v, itemStyle: { color: volColors[i], borderColor: volBorders[i], borderRadius: [0,8,8,0] } })),
      },
    ],
  };

  chart.setOption(option, true);

  // ── Theme change → update grid live ──
  new MutationObserver(() => {
    const d = document.documentElement.getAttribute('data-theme') === 'dark';
    chart.setOption({ yAxis: [{ splitLine: { lineStyle: { color: d ? '#2a2a3a' : '#F5F5F5' } } }] });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  return chart;
}

function fmtVol(v) {
  if (v == null) return '—';
  if (v >= 1e8) return (v/1e8).toFixed(2) + '亿';
  if (v >= 1e4) return (v/1e4).toFixed(0) + '万';
  return v.toString();
}
function fmtAmt(v) {
  if (v == null) return '—';
  if (v >= 1e8) return (v/1e8).toFixed(2) + '亿';
  return v.toString();
}
