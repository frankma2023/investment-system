<template>
  <div class="app">
    <div class="top-bar">
      <input v-model="stockCode" placeholder="股票代码" style="width:100px;padding:8px 12px;border:1px solid var(--divider);border-radius:10px;font-size:0.8rem;background:var(--card-bg);color:var(--text-primary)" @keydown.enter="fetchData" />
      <span v-if="stockName" style="font-size:0.7rem;color:var(--text-tertiary);padding-top:8px">{{ stockName }}</span>
      <button class="btn-run" @click="fetchData">🔍 查询</button>
      <span class="signal-count" v-if="signals.length">🎯 {{ signals.length }} 信号</span>
    </div>

    <KlineChart
      ref="klineRef"
      :klines="klines"
      :signals="signals"
      :signal-markers="signalMarkers"
      v-model:period="period"
      v-model:show-volume="showVolume"
      v-model:show-m-a-c-d="showMACD"
      v-model:activeMAs="activeMAs"
      :height="520"
      @ready="onChartReady"
    />

    <div v-if="signals.length" class="signal-table">
      <div class="xhs-card">
        <div class="xhs-card-header"><span class="xhs-card-label">📋 信号明细</span></div>
        <table>
          <thead><tr><th>日期</th><th>类型</th><th>前高</th><th>杯底</th><th>回调</th><th>买点</th><th>量比</th></tr></thead>
          <tbody>
            <tr v-for="(s, i) in signals.slice().reverse()" :key="i">
              <td style="font-weight:700">{{ s.signal_date }}</td>
              <td>{{ s.pattern_type }}</td>
              <td class="t-up">{{ s.prior_high_price }}</td>
              <td>{{ s.bottom_price }}</td>
              <td>{{ s.drawdown_pct }}%</td>
              <td>{{ s.buy_point }}</td>
              <td>{{ s.breakout_vol_ratio }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>输入股票代码（如 601318）查看碟形基部/杯柄形态信号</p>
      <p style="font-size:0.65rem;color:var(--text-tertiary)">碟形基部和杯柄形态是欧奈尔经典买入形态，较为罕见</p>
    </div>
    <footer class="page-footer">❤️ 投资手账本 · Vue 3 K线图组件 v1</footer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import KlineChart from '@/components/KlineChart.vue'

const stockCode = ref('601318')
const stockName = ref('')
const klines = ref([])
const signals = ref([])
const signalMarkers = ref([])
const klineRef = ref(null)
const period = ref('day')
const showVolume = ref(true)
const showMACD = ref(false)
const activeMAs = ref([5, 10, 20, 60, 120, 250])

async function fetchData() {
  const code = stockCode.value.trim()
  if (!code) return
  try { const nr = await fetch(`/api/stock-name?code=${code}&mode=stock`); if (nr.ok) { const nd = await nr.json(); stockName.value = nd.name || '' } } catch (e) {}
  const today = new Date().toISOString().split('T')[0]
  const start = `${new Date().getFullYear() - 2}-01-01`
  try {
    const r = await fetch(`/api/saucer-base?stock=${code}&date=${today}&start=${start}`)
    const d = await r.json()
    if (d.klines?.length) { klines.value = d.klines; signals.value = d.signals || []; signalMarkers.value = buildMarkers(d.signals); return }
  } catch (e) {}
  try {
    const r = await fetch(`/api/cup-handle?stock=${code}&date=${today}&start=${start}`)
    const d = await r.json()
    if (d.klines?.length) { klines.value = d.klines; signals.value = d.signals || []; signalMarkers.value = buildMarkers(d.signals) }
  } catch (e) {}
}

function buildMarkers(signals) {
  const m = []
  for (const s of signals) {
    if (s.prior_high_date && s.prior_high_price) m.push({ date: s.prior_high_date, price: s.prior_high_price, color: '#FF9800', symbol: 'circle', size: 10 })
    if (s.bottom_date && s.bottom_price) m.push({ date: s.bottom_date, price: s.bottom_price, color: '#4CAF50', symbol: 'circle', size: 10 })
  }
  return m
}

function onChartReady(c) { console.log('KlineChart ready') }
</script>

<style scoped>
.app { max-width: 1200px; margin: 0 auto; padding: 16px; }
.top-bar { display: flex; gap: 12px; align-items: center; padding: 14px 18px; background: var(--card-bg); border-radius: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.btn-run { padding: 9px 24px; background: #FE2C55; color: #FFF; border: none; border-radius: 12px; font-size: 0.9rem; font-weight: 800; cursor: pointer; }
.signal-count { font-size: 0.7rem; font-weight: 700; color: #E91E63; margin-left: auto; }
.signal-table { margin-top: 12px; }
.signal-table table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
.signal-table th, .signal-table td { padding: 5px 8px; text-align: center; border-bottom: 1px solid var(--divider); }
.signal-table th { font-size: 0.65rem; font-weight: 700; color: var(--text-secondary); }
.t-up { color: #E53935; font-weight: 700; }
.empty-state { text-align: center; padding: 40px 20px; color: var(--text-secondary); font-size: 0.8rem; }
.xhs-card { background: var(--card-bg); border-radius: 18px; padding: 14px; box-shadow: 0 1px 6px rgba(0,0,0,0.04); }
.xhs-card-header { margin-bottom: 8px; }
.xhs-card-label { font-size: 0.75rem; font-weight: 800; color: var(--text-primary); }
.page-footer { text-align: center; padding: 20px; font-size: 0.65rem; color: var(--text-tertiary); }
</style>
