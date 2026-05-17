<template>
  <div ref="chartRef" :style="{ height: height + 'px', width: '100%' }"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as echarts from '@/../shared/js/echarts.min.js'

const props = defineProps({
  klines: { type: Array, default: () => [] },
  signals: { type: Array, default: () => [] },
  height: { type: Number, default: 520 },
  maLines: { type: Array, default: () => [5, 10, 20, 60, 120, 250] },
  showVolume: { type: Boolean, default: true },
  showMACD: { type: Boolean, default: false },
  showRSI: { type: Boolean, default: false },
  signalMarkers: { type: Array, default: () => [] },
  // 信号→marker 转换函数的注入点
  markerBuilder: { type: Function, default: null },
})

const emit = defineEmits(['ready'])

const chartRef = ref(null)
let chart = null
let resizeObserver = null

// MAs
const maColors = ['#FF9800', '#2196F3', '#4CAF50', '#9C27B0', '#795548', '#607D8B']

const series = computed(() => {
  if (!props.klines.length) return []
  const kdata = props.klines.map(k => [k.open, k.close, k.low, k.high])
  const dates = props.klines.map(k => k.date)

  const cmas = {}
  for (const p of props.maLines) {
    cmas[p] = computeMA(props.klines, p)
  }

  // 成交量
  const volumes = props.klines.map((k, i) => ({
    value: k.volume,
    itemStyle: {
      color: k.close >= k.open ? 'rgba(229,57,53,0.35)' : 'rgba(38,198,218,0.35)',
    },
  }))
  const volMA5 = computeMA(props.klines.map(k => ({ close: k.volume })), 5).map(v => v?.[0] ?? null)

  // 信号标记
  const markers = buildMarkers(dates)

  return { kdata, dates, cmas, volumes, volMA5, markers }
})

function computeMA(data, period) {
  const result = []
  let sum = 0
  for (let i = 0; i < data.length; i++) {
    const v = data[i].close
    if (v != null) {
      sum += v
      if (i >= period) sum -= data[i - period].close
      result.push(i >= period - 1 ? [sum / period] : [null])
    } else {
      result.push([null])
    }
  }
  return result
}

function buildMarkers(dates) {
  const pts = []

  // 信号标注
  for (const s of props.signals) {
    const idx = dates.indexOf(s.signal_date)
    if (idx < 0) continue
    const bp = s.buy_point || s.prior_high_price || s.close
    pts.push({
      value: [idx, bp],
      symbol: 'diamond',
      symbolSize: 18,
      symbolRotate: 0,
      itemStyle: { color: '#E91E63', borderColor: '#FFF', borderWidth: 1 },
      label: { show: false },
    })
  }

  // 额外的标记（前高/杯底等）
  for (const m of props.signalMarkers) {
    const idx = dates.indexOf(m.date)
    if (idx < 0) continue
    pts.push({
      value: [idx, m.price],
      symbol: m.symbol || 'circle',
      symbolSize: m.size || 12,
      itemStyle: { color: m.color || '#FF9800', borderColor: '#FFF', borderWidth: 0.5 },
    })
  }

  return pts
}

function getTheme() {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

function render() {
  if (!chart || !props.klines.length) return
  const { kdata, dates, cmas, volumes, volMA5, markers } = series.value

  const themeColors = getTheme() === 'dark'
    ? { bg: '#1a1a2e', text: '#aaa', grid: 'rgba(255,255,255,0.06)', cross: '#666' }
    : { bg: '#fff', text: '#666', grid: 'rgba(0,0,0,0.06)', cross: '#999' }

  const option = {
    backgroundColor: themeColors.bg,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', crossStyle: { color: themeColors.cross } },
      backgroundColor: getTheme() === 'dark' ? 'rgba(30,30,50,0.92)' : 'rgba(255,255,255,0.92)',
      borderColor: themeColors.grid,
      textStyle: { fontSize: 11, color: getTheme() === 'dark' ? '#ddd' : '#333' },
      formatter: (params) => {
        if (!params?.length) return ''
        const di = params[0].dataIndex
        const k = props.klines[di]
        if (!k) return ''
        const chg = k.close - k.open
        const chgPct = k.open > 0 ? (chg / k.open * 100).toFixed(2) : '0'
        const col = chg >= 0 ? '#E53935' : '#26C6DA'
        const sign = chg >= 0 ? '+' : ''
        const fmtVol = (v) => v >= 1e8 ? (v / 1e8).toFixed(2) + '亿' : v >= 1e4 ? (v / 1e4).toFixed(0) + '万' : v.toFixed(0)

        return `<div style="font-size:12px;font-weight:700;margin-bottom:4px">📅 ${k.date}</div>
          <div>开盘 <b>${k.open.toFixed(2)}</b></div>
          <div>最高 <b>${k.high.toFixed(2)}</b></div>
          <div>最低 <b>${k.low.toFixed(2)}</b></div>
          <div>收盘 <b style="color:${col}">${k.close.toFixed(2)}</b></div>
          <div>涨跌 <b style="color:${col}">${sign}${chg.toFixed(2)} (${sign}${chgPct}%)</b></div>
          <div>成交量 <b>${fmtVol(k.volume)}</b></div>`
      },
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },

    grid: [
      { left: '9%', right: '2%', top: 10, height: props.showMACD || props.showRSI ? '47%' : props.showVolume ? '58%' : '80%' },
      { left: '9%', right: '2%', top: props.showMACD || props.showRSI ? '62%' : props.showVolume ? '72%' : 'auto', height: '12%' },
      ...(props.showMACD ? [{ left: '9%', right: '2%', top: '78%', height: '8%' }] : []),
    ],

    xAxis: [
      { type: 'category', data: dates, axisLabel: { fontSize: 9, color: themeColors.text }, axisLine: { lineStyle: { color: themeColors.grid } }, axisTick: { show: false } },
      { type: 'category', data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: themeColors.grid } }, axisTick: { show: false }, gridIndex: 1 },
      ...(props.showMACD ? [{ type: 'category', data: dates, axisLabel: { fontSize: 8, color: themeColors.text }, axisLine: { lineStyle: { color: themeColors.grid } }, axisTick: { show: false }, gridIndex: 2 }] : []),
    ],

    yAxis: [
      { type: 'value', scale: true, axisLabel: { fontSize: 9, color: themeColors.text, formatter: v => v.toFixed(1) }, splitLine: { lineStyle: { color: themeColors.grid } } },
      { type: 'value', scale: true, axisLabel: { fontSize: 8, color: themeColors.text }, gridIndex: 1, splitLine: { show: false }, min: 0 },
      ...(props.showMACD ? [{ type: 'value', scale: true, axisLabel: { fontSize: 8, color: themeColors.text }, gridIndex: 2, splitLine: { lineStyle: { color: themeColors.grid } } }] : []),
    ],

    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, ...(props.showMACD ? [2] : [])], start: 0, end: 100, zoomOnMouseWheel: true, moveOnMouseMove: true },
      { type: 'slider', xAxisIndex: [0, 1, ...(props.showMACD ? [2] : [])], start: 0, end: 100, height: 18, bottom: 6,
        borderColor: themeColors.grid, backgroundColor: themeColors.bg,
        dataBackground: { lineStyle: { color: themeColors.text }, areaStyle: { color: 'rgba(128,128,128,0.08)' } },
        handleStyle: { color: '#888' }, textStyle: { fontSize: 9, color: themeColors.text },
      },
    ],

    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: kdata,
        itemStyle: { color: '#E53935', color0: '#26C6DA', borderColor: '#E53935', borderColor0: '#26C6DA' },
        markPoint: markers.length ? { data: [], symbol: 'diamond', symbolSize: 1 } : undefined,
      },
      // MA lines
      ...props.maLines.map((p, i) => ({
        name: `MA${p}`,
        type: 'line',
        data: cmas[p],
        smooth: true,
        symbol: 'none',
        lineStyle: { width: i === 0 ? 1 : i <= 3 ? 1 : 1, color: maColors[i % maColors.length], type: i >= 4 ? 'dashed' : 'solid' },
      })),
      // Signal scatter
      ...(markers.length ? [{
        name: '标记',
        type: 'scatter',
        data: markers,
        z: 10,
        xAxisIndex: 0, yAxisIndex: 0,
      }] : []),
      // Volume bar
      ...(props.showVolume ? [{
        name: '成交量',
        type: 'bar',
        data: volumes,
        xAxisIndex: 1, yAxisIndex: 1,
        barWidth: '60%',
      }, {
        name: 'VOL_MA5',
        type: 'line',
        data: volMA5,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1, color: '#FF9800', type: 'dashed' },
        xAxisIndex: 1, yAxisIndex: 1,
      }] : []),
      // MACD
      ...(props.showMACD ? buildMACDSeries() : []),
    ],
  }

  chart.setOption(option, true)
}

function buildMACDSeries() {
  if (props.klines.length < 26) return []
  const closes = props.klines.map(k => k.close)
  const ema12 = ema(closes, 12)
  const ema26 = ema(closes, 26)
  const dif = ema12.map((v, i) => v - ema26[i])
  const dea = ema(dif, 9)
  const macd = dif.map((v, i) => (v - dea[i]) * 2)

  return [
    { name: 'DIF', type: 'line', data: dif, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#E91E63' }, xAxisIndex: 2, yAxisIndex: 2 },
    { name: 'DEA', type: 'line', data: dea, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#2196F3' }, xAxisIndex: 2, yAxisIndex: 2 },
    { name: 'MACD', type: 'bar', data: macd.map((v, i) => ({ value: v, itemStyle: { color: v >= 0 ? 'rgba(229,57,53,0.5)' : 'rgba(38,198,218,0.5)' } })),
      xAxisIndex: 2, yAxisIndex: 2, barWidth: '50%' },
  ]
}

function ema(data, period) {
  const result = new Array(data.length).fill(0)
  if (data.length === 0) return result
  const k = 2 / (period + 1)
  result[0] = data[0]
  for (let i = 1; i < data.length; i++) {
    result[i] = data[i] * k + result[i - 1] * (1 - k)
  }
  return result
}

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, getTheme(), { renderer: 'canvas' })
  render()

  resizeObserver = new ResizeObserver(() => {
    chart?.resize()
  })
  resizeObserver.observe(chartRef.value)
}

// 监听属性变化
watch(() => [props.klines, props.signals, props.signalMarkers, props.showVolume, props.showMACD], () => {
  nextTick(() => render())
}, { deep: true })

// 主题监听
const themeObserver = new MutationObserver(() => {
  if (chart) {
    chart.dispose()
    chart = echarts.init(chartRef.value, getTheme(), { renderer: 'canvas' })
    render()
  }
})

onMounted(() => {
  nextTick(() => initChart())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  emit('ready', chart)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart?.dispose()
})

defineExpose({ getChart: () => chart, refresh: render })
</script>
