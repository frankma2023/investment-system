/**
 * KlineChart.js — 欧奈尔投资系统通用K线图组件
 * 
 * 提取自 base-breakout 页面的精调样式，支持所有回测看板复用。
 * 一行引入，一行渲染。
 *
 * ═══ 完整页面模板（复制粘贴即可） ═══
 *
 * <link rel="stylesheet" href="../shared/css/theme.css">
 * <link rel="stylesheet" href="../shared/css/base.css">
 * <link rel="stylesheet" href="../shared/css/xhs-cards.css">
 * <link rel="stylesheet" href="../shared/css/components.css">
 * <script src="../shared/js/echarts.min.js"></script>
 * <script src="../shared/js/kline-chart.js"></script>
 *
 * <!-- 控制栏 -->
 * <div class="top-bar">
 *   <div class="fld" style="flex:0.5;min-width:80px">
 *     <label>类型</label><select id="mode"><option value="stock">个股</option><option value="index">指数</option></select>
 *   </div>
 *   <div class="code-wrap"><div class="fld">
 *     <label>代码</label><input type="text" id="stock-code" value="600519" onkeydown="if(event.key==='Enter')run()">
 *     <span id="stock-name" style="margin-left:6px;font-weight:700;font-size:0.85rem"></span>
 *   </div></div>
 *   <div class="fld" style="flex:0.5;min-width:90px">
 *     <label>周期</label><select id="period" onchange="run()"><option value="day">日线</option><option value="week">周线</option><option value="month">月线</option></select>
 *   </div>
 *   <div class="fld"><label>开始</label><input type="date" id="date-start"></div>
 *   <div class="fld"><label>结束</label><input type="date" id="date-end"></div>
 * </div>
 *
 * <!-- K线图容器（无需设置宽高，CSS已处理） -->
 * <div id="chart" class="chart-wrap"></div>
 *
 * <!-- 左右分栏 -->
 * <div class="bottom-layout">
 *   <div class="bottom-left">
 *     <!-- 参数卡片 -->
 *     <div class="param-card">
 *       <div class="param-card-hd" onclick="this.nextElementSibling.classList.toggle('collapsed')">
 *         <span class="dot" style="background:#FE2C55"></span>🔴 参数
 *       </div>
 *       <div class="param-card-bd">
 *         <div class="sr"><span class="sl">参数名</span><input type="range" min="0" max="100" value="50"><span class="sv">50%</span></div>
 *         <div class="tog-row"><span class="sl">开关</span><button class="tsw on" onclick="this.classList.toggle('on');this.classList.toggle('off')"></button></div>
 *       </div>
 *     </div>
 *     <button class="btn-run" onclick="run()">🔍 运行识别</button>
 *     <button class="btn-save" onclick="saveCfg()">💾 保存配置</button>
 *   </div>
 *   <div class="bottom-right">
 *     <div class="xhs-card"><div class="xhs-card-header"><span class="xhs-card-label">📋 信号明细</span></div><div id="table"></div></div>
 *   </div>
 * </div>
 *
 * ═══ JS 用法 ═══
 *
 * var chart = KlineChart.create({
 *   container: document.getElementById('chart'),
 *   klines: data,
 *   signals: signals,
 *   signalMap: signalMap,
 * });
 * chart.update(newData, newSignals, newMap);
 * chart.dispose();
 */

(function (global) {
  'use strict';

  // ─── 默认配置 ──────────────────
  var DEFAULTS = {
    // 容器（必填）
    container: null,

    // 高度
    height: 520,

    // 均线周期
    maLines: [5, 10, 20, 60, 120, 250],
    // 各均线颜色（与周期一一对应）
    maColors: ['#E91E63', '#FF9800', '#F4B400', '#4CAF50', '#2196F3', '#9C27B0'],
    // 均线宽度覆盖: {5:1, 10:1, 60:1.2, 250:1.5}
    maWidths: { 5: 1, 10: 1, 20: 1, 60: 1.2, 120: 1.2, 250: 1.5 },

    // 信号标注样式
    signalSymbol: 'pin',       // ECharts scatter symbol: pin/diamond/triangle/circle
    signalColor: '#A349A4',    // 信号点颜色
    signalSize: 28,            // 信号点大小
    signalLabel: false,        // 是否显示文字标签
    signalTooltipPrefix: '🎯 突破日',  // tooltip 中信号的标题

    // 额外的标记（前高/杯底等）
    extraMarkers: [],          // [{date, price, symbol, color, size}]

    // 均线tooltip文字色
    maTooltipColors: null,     // null=使用maColors，自定义: ['red','#FF9800',...]

    // 成交量副图
    showVolume: true,

    // K线颜色
    upColor: '#E53935',        // 阳线
    downColor: '#26C6DA',      // 阴线

    // 背景
    darkBg: '#2A2627',
    lightBg: '#fff',

    // 网格
    gridMainHeight: '60%',     // 主图高度
    gridVolTop: '75%',         // 成交量顶部位置
    gridVolHeight: '15%',      // 成交量高度
  };

  // ─── 工具函数 ──────────────────
  function computeMA(data, period, field) {
    field = field || 'close';
    var result = [], sum = 0;
    for (var i = 0; i < data.length; i++) {
      var v = data[i][field];
      if (v != null) {
        sum += v;
        if (i >= period) sum -= data[i - period][field];
        result.push(i >= period - 1 ? sum / period : null);
      } else {
        result.push(null);
      }
    }
    return result;
  }

  function isDark() {
    return document.documentElement.dataset.theme === 'dark';
  }

  function fmtVolume(v) {
    if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
    return v.toFixed(0);
  }

  // ─── 构造函数 ──────────────────
  function KlineChart(options) {
    this.opts = Object.assign({}, DEFAULTS, options || {});
    if (!this.opts.container) throw new Error('KlineChart: container is required');

    // 创建图表容器
    this.container = this.opts.container;
    if (this.container.querySelector('.kc-chart-div')) {
      // 已存在则复用
      this.chartDom = this.container.querySelector('.kc-chart-div');
    } else {
      this.chartDom = document.createElement('div');
      this.chartDom.className = 'kc-chart-div';
      this.chartDom.style.cssText = 'width:100%;height:' + this.opts.height + 'px';
      this.container.appendChild(this.chartDom);
    }

    this.chart = echarts.init(this.chartDom, isDark() ? 'dark' : null, { renderer: 'canvas' });
    this.klines = [];
    this.signals = [];
    this.signalMap = {};
    this.extraMarkers = this.opts.extraMarkers || [];

    // 主题切换
    var self = this;
    this._themeObserver = new MutationObserver(function () {
      if (!self.chart || self.chart.isDisposed()) return;
      var oldOpt = self.chart.getOption();
      self.chart.dispose();
      self.chart = echarts.init(self.chartDom, isDark() ? 'dark' : null, { renderer: 'canvas' });
      if (self.klines.length) self._render();
    });
    this._themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    // resize
    this._resizeTimer = null;
    window.addEventListener('resize', function () {
      if (self._resizeTimer) clearTimeout(self._resizeTimer);
      self._resizeTimer = setTimeout(function () {
        self.chart && !self.chart.isDisposed() && self.chart.resize();
      }, 200);
    });
  }

  KlineChart.prototype.update = function (klines, signals, signalMap, extraMarkers) {
    this.klines = klines || [];
    this.signals = signals || [];
    this.signalMap = signalMap || {};
    this.extraMarkers = extraMarkers || this.opts.extraMarkers || [];
    if (!this.chart || this.chart.isDisposed()) {
      this.chart = echarts.init(this.chartDom, isDark() ? 'dark' : null, { renderer: 'canvas' });
    }
    this._render();
  };

  KlineChart.prototype._render = function () {
    var self = this;
    var ck = this.klines;
    var cs = this.signals;
    var sm = this.signalMap;
    var o = this.opts;
    if (!ck.length) { this.chart.clear(); return; }

    var dates = ck.map(function (k) { return k.date; });

    // ── 均线计算 ──
    var mas = {};
    o.maLines.forEach(function (p) { mas[p] = computeMA(ck, p); });

    // ── 信号点（支持 per-point 样式覆盖）──
    var pts = [];
    cs.forEach(function (s) {
      var si = dates.indexOf(s.signal_date || s.date);
      if (si < 0) return;
      var y = s.y != null ? s.y : s.buy_point;
      var sy = s.symbol || o.signalSymbol;
      var ss = s.size || s.signalSize || o.signalSize;
      var sc = s.color || o.signalColor;
      var label = s.label || (o.signalTooltipPrefix + ' ¥' + (s.buy_point != null ? s.buy_point : y));
      pts.push({
        name: o.signalTooltipPrefix,
        coord: [si, y],
        value: label,
        symbol: sy,
        symbolSize: ss,
        itemStyle: { color: sc, borderColor: '#FFF', borderWidth: 1 },
        label: { show: !!o.signalLabel },
      });
    });

    // 额外标记
    var xtraMarks = [];
    (this.extraMarkers || []).forEach(function (m) {
      var si = dates.indexOf(m.date);
      if (si < 0) return;
      xtraMarks.push({
        name: m.label || '',
        coord: [si, m.price],
        value: m.label || '',
        symbol: m.symbol || 'circle',
        symbolSize: m.size || 12,
        itemStyle: { color: m.color || '#FF9800', borderColor: '#FFF', borderWidth: 0.5 },
        label: { show: false },
      });
    });

    var dark = isDark();
    var bg = dark ? o.darkBg : o.lightBg;
    var tx = dark ? '#ccc' : '#333';

    // ── MA tooltip 色 ──
    var maTipColors = o.maTooltipColors || o.maColors;

    var option = {
      backgroundColor: bg,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: dark ? 'rgba(0,0,0,0.85)' : 'rgba(255,255,255,0.85)',
        borderColor: 'transparent',
        borderWidth: 0,
        textStyle: { color: dark ? '#eee' : '#333', fontSize: 11 },
        formatter: function (params) {
          if (!params || !params.length) return '';
          var di = params[0].dataIndex, d = ck[di];
          if (!d) return '';
          var oo = d.open, cc = d.close, h = d.high, l = d.low, v = d.volume;
          var chg = oo > 0 ? ((cc - oo) / oo * 100).toFixed(2) : '—';
          var amp = h > l ? ((h - l) / l * 100).toFixed(2) : '—';
          var vs = fmtVolume(v);
          var ln = '<div style="line-height:1.9;font-size:11px">';
          ln += '<div style="font-weight:700;font-size:13px;margin-bottom:4px">' + d.date + '</div>';
          ln += '<div>开盘 <b>' + oo.toFixed(2) + '</b></div>';
          ln += '<div>收盘 <b>' + cc.toFixed(2) + '</b></div>';
          ln += '<div>最高 <span style="color:' + self.opts.upColor + '">' + h.toFixed(2) + '</span></div>';
          ln += '<div>最低 <span style="color:' + self.opts.downColor + '">' + l.toFixed(2) + '</span></div>';
          ln += '<div>涨幅 <span style="color:' + (cc >= oo ? self.opts.upColor : self.opts.downColor) + '">' + (cc >= oo ? '+' : '') + chg + '%</span></div>';
          ln += '<div>振幅 ' + amp + '%</div>';
          ln += '<div>成交量 ' + vs + '</div>';

          // MA 值
          for (var mi = 0; mi < o.maLines.length; mi++) {
            var p = o.maLines[mi];
            var mav = mas[p][di];
            if (mav != null) {
              ln += '<div>MA' + p + ' <span style="color:' + maTipColors[mi % maTipColors.length] + '">' + mav.toFixed(2) + '</span></div>';
            }
          }

          // 信号信息
          if (sm[d.date]) {
            var s = sm[d.date];
            ln += '<div style="color:' + (s.color || o.signalColor) + ';font-weight:700;padding-top:2px">' + (s.label || o.signalTooltipPrefix + ' 买点=' + (s.buy_point != null ? s.buy_point : '—') + ' 回调=' + (s.drawdown_pct != null ? s.drawdown_pct + '%' : '—')) + '</div>';
          }

          ln += '</div>';
          return ln;
        },
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [
        { left: '8%', right: '1%', top: 8, height: o.gridMainHeight },
        ...(o.showVolume ? [{ left: '8%', right: '1%', top: o.gridVolTop, height: o.gridVolHeight }] : []),
      ],
      xAxis: [
        { type: 'category', data: dates, axisLabel: { fontSize: 9, color: tx }, axisLine: { lineStyle: { color: '#ccc' } } },
        ...(o.showVolume ? [{ type: 'category', data: dates, axisLabel: { show: false }, gridIndex: 1 }] : []),
      ],
      yAxis: [
        { type: 'value', scale: true, axisLabel: { fontSize: 9, color: tx }, splitLine: { lineStyle: { color: dark ? '#3a3a3a' : '#eee' } } },
        ...(o.showVolume ? [{ type: 'value', scale: true, axisLabel: { fontSize: 8 }, gridIndex: 1, splitLine: { show: false } }] : []),
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: o.showVolume ? [0, 1] : [0] },
        { type: 'slider', xAxisIndex: o.showVolume ? [0, 1] : [0], height: 16, bottom: 4 },
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: ck.map(function (k) { return [k.open, k.close, k.low, k.high]; }),
          itemStyle: { color: o.upColor, color0: o.downColor, borderColor: o.upColor, borderColor0: o.downColor },
          markPoint: {
            data: pts.concat(xtraMarks),
            symbol: o.signalSymbol,
            symbolSize: o.signalSize,
            itemStyle: { color: o.signalColor },
            label: { show: !!o.signalLabel },
          },
        },
        ...(o.showVolume ? [{
          name: '成交量',
          type: 'bar',
          data: ck.map(function (k, i) {
            return {
              value: k.volume,
              itemStyle: { color: ck[i].close >= ck[i].open ? o.upColor : o.downColor },
            };
          }),
          xAxisIndex: 1,
          yAxisIndex: 1,
        }] : []),
      ],
    };

    // 添加均线 Series
    for (var mi2 = 0; mi2 < o.maLines.length; mi2++) {
      var p2 = o.maLines[mi2];
      var w = (o.maWidths && o.maWidths[p2]) || 1;
      option.series.push({
        name: 'MA' + p2,
        type: 'line',
        data: mas[p2],
        smooth: true,
        symbol: 'none',
        lineStyle: { width: w, color: o.maColors[mi2 % o.maColors.length] },
      });
    }

    this.chart.setOption(option, true);
  };

  KlineChart.prototype.dispose = function () {
    if (this._themeObserver) { this._themeObserver.disconnect(); this._themeObserver = null; }
    if (this.chart && !this.chart.isDisposed()) { this.chart.dispose(); this.chart = null; }
    if (this.chartDom && this.chartDom.parentNode) { this.chartDom.parentNode.removeChild(this.chartDom); }
  };

  // ─── 工厂函数 ──────────────────
  KlineChart.create = function (options) {
    return new KlineChart(options);
  };

  // ─── 工具：聚合日线→周线/月线 ──
  KlineChart.aggregate = function (klines, period) {
    if (!klines || !klines.length) return [];
    if (period === 'day') return klines;
    var result = [], current = null;
    klines.forEach(function (k) {
      var d = new Date(k.date);
      var key;
      if (period === 'week') {
        var start = new Date(d);
        start.setDate(d.getDate() - d.getDay());
        key = start.toISOString().slice(0, 10);
      } else {
        key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
      }
      if (!current || current.key !== key) {
        if (current) result.push(current.row);
        current = {
          key: key,
          row: { date: k.date, open: k.open, high: k.high, low: k.low, close: k.close, volume: k.volume },
        };
      } else {
        current.row.high = Math.max(current.row.high, k.high);
        current.row.low = Math.min(current.row.low, k.low);
        current.row.close = k.close;
        current.row.volume += k.volume;
        current.row.date = k.date;
      }
    });
    if (current) result.push(current.row);
    return result;
  };

  // 导出
  global.KlineChart = KlineChart;

})(typeof window !== 'undefined' ? window : this);