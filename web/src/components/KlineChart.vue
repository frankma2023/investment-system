<template>
  <div class="kc-wrap">
    <div class="kc-toolbar" v-if="showToolbar">
      <!-- 周期选择 -->
      <div class="kc-periods">
        <button v-for="p in ['day','week','month']" :key="p"
          :class="['kc-btn', { active: period === p }]"
          @click="$emit('update:period', p)">{{ periodLabel(p) }}</button>
      </div>

      <!-- MA切换 -->
      <div class="kc-mas">
        <button v-for="ma in availableMAs" :key="ma"
          :class="['kc-ma-pill', { on: activeMAs.includes(ma) }]"
          @click="toggleMA(ma)">MA{{ ma }}</button>
      </div>

      <!-- 副图切换 -->
      <div class="kc-subs" v-if="showSubControls">
        <label :class="['kc-sub-toggle', { on: showVolume }]" @click="$emit('update:showVolume', !showVolume)">VOL</label>
        <label :class="['kc-sub-toggle', { on: showMACD }]" @click="$emit('update:showMACD', !showMACD)">MACD</label>
      </div>
    </div>
    <div ref="chartRef" :style="{ height: chartHeight + 'px', width: '100%' }"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  klines: { type: Array, default: () => [] },
  signals: { type: Array, default: () => [] },
  height: { type: Number, default: 520 },
  availableMAs: { type: Array, default: () => [5, 10, 20, 60, 120, 250] },
  activeMAs: { type: Array, default: () => [5, 10, 20, 60, 120, 250] },
  showVolume: { type: Boolean, default: true },
  showMACD: { type: Boolean, default: false },
  signalMarkers: { type: Array, default: () => [] },
  period: { type: String, default: 'day' },
  showToolbar: { type: Boolean, default: true },
  showSubControls: { type: Boolean, default: true },
})

const emit = defineEmits(['ready', 'update:period', 'update:showVolume', 'update:showMACD', 'update:activeMAs'])

const chartRef = ref(null)
let chart = null
let resizeObserver = null

const chartHeight = computed(() => props.showToolbar ? props.height - 30 : props.height)

const maColors = ['#FF9800', '#2196F3', '#4CAF50', '#9C27B0', '#795548', '#607D8B']

function periodLabel(p) { return { day: '日K', week: '周K', month: '月K' }[p] }

function toggleMA(ma) {
  const next = props.activeMAs.includes(ma)
    ? props.activeMAs.filter(v => v !== ma)
    : [...props.activeMAs, ma].sort((a, b) => a - b)
  emit('update:activeMAs', next)
}

const series = computed(() => {
  if (!props.klines.length) return {}
  const kdata = props.klines.map(k => [k.open, k.close, k.low, k.high])
  const dates = props.klines.map(k => k.date)
  const cmas = {}
  for (const p of props.activeMAs) cmas[p] = computeMA(props.klines, p)
  const volumes = props.klines.map((k, i) => ({
    value: k.volume,
    itemStyle: { color: k.close >= k.open ? 'rgba(229,57,53,0.35)' : 'rgba(38,198,218,0.35)' },
  }))
  const markers = buildMarkers(dates)
  return { kdata, dates, cmas, volumes, markers }
})

function computeMA(data, period) {
  const result = []
  let sum = 0, count = 0
  for (let i = 0; i < data.length; i++) {
    const v = data[i].close
    if (v != null) {
      sum += v; count++
      if (i >= period) { sum -= data[i - period].close }
      result.push(i >= period - 1 ? sum / period : null)
    } else {
      result.push(null)
    }
  }
  return result
}

function buildMarkers(dates) {
  const pts = []
  for (const s of props.signals) {
    const idx = dates.indexOf(s.signal_date)
    if (idx < 0) continue
    const bp = s.buy_point || s.prior_high_price || s.close
    pts.push({ value: [idx, bp], symbol: 'diamond', symbolSize: 18, itemStyle: { color: '#E91E63', borderColor: '#FFF', borderWidth: 1 } })
  }
  for (const m of props.signalMarkers) {
    const idx = dates.indexOf(m.date)
    if (idx < 0) continue
    pts.push({ value: [idx, m.price], symbol: m.symbol || 'circle', symbolSize: m.size || 12, itemStyle: { color: m.color || '#FF9800' } })
  }
  return pts
}

function getTheme() { return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light' }

function render() {
  if (!chart || !props.klines.length) return
  const { kdata, dates, cmas, volumes, markers } = series.value
  if (!kdata?.length) return

  const dark = getTheme() === 'dark'
  const tColors = dark
    ? { bg: '#1a1a2e', text: '#aaa', grid: 'rgba(255,255,255,0.06)', cross: '#666' }
    : { bg: '#fff', text: '#666', grid: 'rgba(0,0,0,0.06)', cross: '#999' }

  const hasSub = props.showVolume || props.showMACD
  const gridH1 = props.showMACD ? '47%' : hasSub ? '58%' : '80%'

  const option = {
    backgroundColor: tColors.bg,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: tColors.cross } },
      backgroundColor: dark ? 'rgba(30,30,50,0.92)' : 'rgba(255,255,255,0.92)',
      borderColor: tColors.grid,
      textStyle: { fontSize: 11, color: dark ? '#ddd' : '#333' },
      formatter: (params) => {
        if (!params?.length) return ''
        const di = params[0].dataIndex
        const k = props.klines[di]; if (!k) return ''
        const chg = k.close - k.open, cp = k.open > 0 ? (chg / k.open * 100).toFixed(2) : '0'
        const col = chg >= 0 ? '#E53935' : '#26C6DA'; const s = chg >= 0 ? '+' : ''
        const fv = v => v >= 1e8 ? (v/1e8).toFixed(2)+'亿' : v >= 1e4 ? (v/1e4).toFixed(0)+'万' : v.toFixed(0)

        // 收集MA值
        let maHtml = ''
        for (const p of params) {
          if (p.seriesName?.startsWith('MA') && p.value != null) {
            maHtml += `<div>${p.seriesName} <b>${Number(p.value).toFixed(2)}</b></div>`
          }
        }

        return `<div style="font-size:12px;font-weight:700;margin-bottom:4px">📅 ${k.date}</div>
          <div>开 <b>${k.open.toFixed(2)}</b> 高 <b>${k.high.toFixed(2)}</b></div>
          <div>低 <b>${k.low.toFixed(2)}</b> 收 <b style="color:${col}">${k.close.toFixed(2)}</b></div>
          <div>涨跌 <b style="color:${col}">${s}${chg.toFixed(2)} (${s}${cp}%)</b></div>
          <div>量 <b>${fv(k.volume)}</b></div>
          ${maHtml}`
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: '9%', right: '2%', top: 15, height: gridH1 },
      ...(props.showVolume ? [{ left: '9%', right: '2%', top: props.showMACD ? '62%' : '72%', height: '12%' }] : []),
      ...(props.showMACD ? [{ left: '9%', right: '2%', top: '78%', height: '8%' }] : []),
    ],
    xAxis: [
      { type: 'category', data: dates, axisLabel: { fontSize: 9, color: tColors.text }, axisLine: { lineStyle: { color: tColors.grid } }, axisTick: { show: false } },
      ...(props.showVolume ? [{ type: 'category', data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: tColors.grid } }, axisTick: { show: false }, gridIndex: 1 }] : []),
      ...(props.showMACD ? [{ type: 'category', data: dates, axisLabel: { fontSize: 8, color: tColors.text }, axisTick: { show: false }, gridIndex: props.showVolume ? 2 : 1 }] : []),
    ],
    yAxis: [
      { type: 'value', scale: true, axisLabel: { fontSize: 9, color: tColors.text, formatter: v => v.toFixed(1) }, splitLine: { lineStyle: { color: tColors.grid } } },
      ...(props.showVolume ? [{ type: 'value', scale: true, axisLabel: { fontSize: 8, color: tColors.text }, gridIndex: 1, splitLine: { show: false }, min: 0 }] : []),
      ...(props.showMACD ? [{ type: 'value', scale: true, axisLabel: { fontSize: 8, color: tColors.text }, gridIndex: props.showVolume ? 2 : 1, splitLine: { lineStyle: { color: tColors.grid } } }] : []),
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: 'all', start: 0, end: 100, zoomOnMouseWheel: true, moveOnMouseMove: true },
      { type: 'slider', xAxisIndex: 'all', start: 0, end: 100, height: 18, bottom: 6, borderColor: tColors.grid, backgroundColor: tColors.bg },
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: kdata, itemStyle: { color: '#E53935', color0: '#26C6DA', borderColor: '#E53935', borderColor0: '#26C6DA' } },
      ...props.activeMAs.map((p, i) => ({
        name: `MA${p}`, type: 'line', data: cmas[p], smooth: true, symbol: 'none',
        lineStyle: { width: p >= 60 ? 1.2 : 1, color: maColors[i % maColors.length], type: p >= 120 ? 'dashed' : 'solid' },
      })),
      ...(markers.length ? [{ name: '标记', type: 'scatter', data: markers, z: 10 }] : []),
      ...(props.showVolume ? [
        { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1, barWidth: '60%' },
      ] : []),
      ...(props.showMACD ? buildMACDSeries(props.showVolume ? 2 : 1) : []),
    ],
  }

  chart.setOption(option, true)
}

function buildMACDSeries(gridIdx) {
  if (props.klines.length < 26) return []
  const closes = props.klines.map(k => k.close)
  const [dif, dea, macd] = calcMACD(closes)
  return [
    { name: 'DIF', type: 'line', data: dif, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#E91E63' }, xAxisIndex: gridIdx, yAxisIndex: gridIdx },
    { name: 'DEA', type: 'line', data: dea, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#2196F3' }, xAxisIndex: gridIdx, yAxisIndex: gridIdx },
    { name: 'MACD', type: 'bar', data: macd.map(v => ({ value: v, itemStyle: { color: v >= 0 ? 'rgba(229,57,53,0.5)' : 'rgba(38,198,218,0.5)' } })), xAxisIndex: gridIdx, yAxisIndex: gridIdx, barWidth: '50%' },
  ]
}

function calcMACD(data) {
  const k12 = 2/13, k26 = 2/27, k9 = 2/10
  const ema12 = [data[0]], ema26 = [data[0]]
  for (let i = 1; i < data.length; i++) {
    ema12.push(data[i] * k12 + ema12[i-1] * (1 - k12))
    ema26.push(data[i] * k26 + ema26[i-1] * (1 - k26))
  }
  const dif = ema12.map((v, i) => v - ema26[i])
  const dea = [dif[0]]
  for (let i = 1; i < dif.length; i++) dea.push(dif[i] * k9 + dea[i-1] * (1 - k9))
  const macd = dif.map((v, i) => (v - dea[i]) * 2)
  return [dif, dea, macd]
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, getTheme(), { renderer: 'canvas' })
  render()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
}

watch(() => [props.klines, props.signals, props.signalMarkers, props.showVolume, props.showMACD, props.activeMAs, props.period], () => {
  nextTick(() => render())
}, { deep: true })

const themeObserver = new MutationObserver(() => {
  if (!chart) return
  chart.dispose()
  chart = echarts.init(chartRef.value, getTheme(), { renderer: 'canvas' })
  render()
})

onMounted(() => {
  nextTick(() => initChart())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  emit('ready', chart)
})

onUnmounted(() => { resizeObserver?.disconnect(); themeObserver?.disconnect(); chart?.dispose() })
defineExpose({ getChart: () => chart, refresh: render })
</script>

<style scoped>
.kc-wrap { position: relative; }
.kc-toolbar {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 10px; background: var(--card-bg, #fff); border-radius: 8px 8px 0 0;
  border: 1px solid var(--divider, #e5e7eb); border-bottom: none;
  font-size: 0.6rem; flex-wrap: wrap;
}
.kc-btn {
  padding: 3px 10px; border: 1px solid var(--divider, #e5e7eb); border-radius: 4px;
  background: transparent; color: var(--text-secondary, #555); cursor: pointer;
  font-size: 0.58rem; font-weight: 600;
}
.kc-btn.active { background: #FE2C55; color: #fff; border-color: #FE2C55; }
.kc-ma-pill {
  padding: 2px 7px; border: 1px solid var(--divider, #e5e7eb); border-radius: 3px;
  background: transparent; color: var(--text-tertiary, #888); cursor: pointer;
  font-size: 0.55rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;
}
.kc-ma-pill.on { background: var(--color-accent, #2563eb); color: #fff; border-color: var(--color-accent, #2563eb); }
.kc-sub-toggle {
  padding: 3px 8px; border: 1px solid var(--divider, #e5e7eb); border-radius: 4px;
  cursor: pointer; font-size: 0.55rem; font-weight: 600; user-select: none;
  color: var(--text-tertiary, #888);
}
.kc-sub-toggle.on { background: #4CAF50; color: #fff; border-color: #4CAF50; }
.kc-periods, .kc-mas, .kc-subs { display: flex; gap: 4px; align-items: center; }
</style>
