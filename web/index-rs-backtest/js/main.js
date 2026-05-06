/**
 * index-rs-backtest/js/main.js
 * 指数强度回测看板 — 主逻辑
 */
(function () {
  'use strict';

  const API_BASE = 'http://localhost:8788';

  // ── 池子映射 ──
  const POOL_META = {
    market:     { name: '全市场指数', count: 29 },
    sector_l1:  { name: '一级行业', count: 11 },
    sector_l2:  { name: '二级行业', count: 45 },
    thematic:   { name: '行业主题', count: 229 },
    strategy:   { name: '策略指数', count: 93 },
  };

  let currentPool = 'market';
  let currentData = null;       // Full API response
  let indexNames = {};          // code → name

  // ── Init ──
  async function init() {
    buildPoolSelect();
    buildTabs();
    setDefaultDate();
    await loadConfig();
  }

  function buildPoolSelect() {
    const sel = document.getElementById('pool-select');
    for (const [key, meta] of Object.entries(POOL_META)) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = `${meta.name} (${meta.count})`;
      sel.appendChild(opt);
    }
    sel.value = currentPool;
    sel.addEventListener('change', () => { currentPool = sel.value; });
  }

  function buildTabs() {
    const container = document.getElementById('pool-tabs');
    for (const [key, meta] of Object.entries(POOL_META)) {
      const tab = document.createElement('span');
      tab.className = 'pool-tab';
      tab.textContent = `${meta.name}`;
      tab.title = `${meta.name} · ${meta.count} 个指数`;
      tab.dataset.pool = key;
      tab.addEventListener('click', () => switchTab(key));
      container.appendChild(tab);
    }
    highlightTab(currentPool);
  }

  function switchTab(pool) {
    document.getElementById('pool-select').value = pool;
    currentPool = pool;
    highlightTab(pool);
    renderResults(pool);
  }

  function highlightTab(pool) {
    document.querySelectorAll('.pool-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.pool === pool);
    });
  }

  function setDefaultDate() {
    const today = new Date();
    // 回退到最后一个交易日：周一到周五，排除今天如果还在盘中
    let d = new Date(today);
    d.setDate(d.getDate() - 1);  // 默认昨天
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    document.getElementById('rs-date').value = `${yyyy}-${mm}-${dd}`;
  }

  // ── Config ──
  async function loadConfig() {
    try {
      const resp = await fetch(`${API_BASE}/api/config?signal_type=index_rs`);
      if (!resp.ok) return;
      const cfg = await resp.json();
      if (cfg && cfg.tiers) {
        setSliderIf('l1-rs120', cfg.tiers.L1?.RS_120);
        setSliderIf('l1-rs250', cfg.tiers.L1?.RS_250);
        setSliderIf('l1-rs60', cfg.tiers.L1?.RS_60);
        setSliderIf('l2-rs20', cfg.tiers.L2?.RS_20);
        setSliderIf('l2-rs60', cfg.tiers.L2?.RS_60);
        setSliderIf('l2-rs120', cfg.tiers.L2?.RS_120);
        setSliderIf('l3-rs60', cfg.tiers.L3?.RS_60);
        setSliderIf('l3-rs120', cfg.tiers.L3?.RS_120);
        setSliderIf('l3-rs20max', cfg.tiers.L3?.RS_20_max);
        setSliderIf('l3-madays', cfg.tiers.L3?.ma_days);
      }
    } catch (e) {
      console.warn('Failed to load config:', e);
    }
  }

  function setSliderIf(id, val) {
    if (val === undefined || val === null) return;
    const el = document.getElementById(id);
    if (el) { el.value = val; syncSliderVal(id); syncMaDays(); }
  }

  async function saveConfig() {
    const yaml = buildConfigYaml();
    try {
      const resp = await fetch(`${API_BASE}/api/config?signal_type=index_rs`, {
        method: 'POST',
        body: yaml,
      });
      if (resp.ok) {
        alert('✅ 配置已保存到 config/index_rs.yaml');
      } else {
        alert('❌ 保存失败');
      }
    } catch (e) {
      alert('❌ 保存失败: ' + e.message);
    }
  }

  function buildConfigYaml() {
    const getVal = id => parseInt(document.getElementById(id).value);
    return [
      '# index_rs.yaml — 指数RS强度扫描参数配置',
      '',
      'tiers:',
      '  L1:',
      `    RS_120: ${getVal('l1-rs120')}`,
      `    RS_250: ${getVal('l1-rs250')}`,
      `    RS_60: ${getVal('l1-rs60')}`,
      '  L2:',
      `    RS_20: ${getVal('l2-rs20')}`,
      `    RS_60: ${getVal('l2-rs60')}`,
      `    RS_120: ${getVal('l2-rs120')}`,
      '  L3:',
      `    RS_60: ${getVal('l3-rs60')}`,
      `    RS_120: ${getVal('l3-rs120')}`,
      `    RS_20_max: ${getVal('l3-rs20max')}`,
      `    ma_days: ${getVal('l3-madays')}`,
      '',
      'resonance:',
      '  enabled: false',
      '  strong_stock_rs: 80',
      '  strong_resonance:',
      '    strong_ratio: 40',
      '    median_rs: 75',
      '  medium_resonance:',
      '    strong_ratio_min: 20',
      '    strong_ratio_max: 40',
      '    median_rs: 65',
      '  weak_resonance:',
      '    strong_ratio: 20',
      '    median_rs: 60',
    ].join('\n');
  }

  // ── API Call ──
  async function runBacktest() {
    const btn = document.getElementById('btn-run');
    btn.disabled = true;
    btn.textContent = '⏳ 计算中...';

    const date = document.getElementById('rs-date').value;
    const pool = document.getElementById('pool-select').value || currentPool;

    try {
      const resp = await fetch(`${API_BASE}/api/index-rs?pool=${pool}&date=${date}`);
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt.substring(0, 100)}`);
      }
      currentData = await resp.json();

      // 收集指数名称
      for (const [pname, pdata] of Object.entries(currentData.pools || {})) {
        for (const item of (pdata.rankings || [])) {
          if (item.name) indexNames[item.code] = item.name;
        }
        for (const tier of ['L1','L2','L3']) {
          for (const item of (pdata.tiers || {})[tier] || []) {
            if (item.name) indexNames[item.code] = item.name;
          }
        }
      }

      renderResults(pool);
    } catch (e) {
      alert('❌ 计算失败: ' + e.message);
      console.error(e);
    } finally {
      btn.disabled = false;
      btn.textContent = '🔍 计算';
    }
  }

  // ── Render ──
  function renderResults(pool) {
    if (!currentData || !currentData.pools) return;

    const poolData = currentData.pools[pool];
    if (!poolData) {
      document.getElementById('table-pool-name').textContent = '（无数据）';
      return;
    }

    document.getElementById('table-pool-name').textContent =
      `· ${POOL_META[pool]?.name || pool} · ${currentData.as_of_date}`;

    // Stats
    const rankings = poolData.rankings || [];
    const tiers = poolData.tiers || { L1: [], L2: [], L3: [] };
    document.getElementById('stat-total').textContent = rankings.length;
    document.getElementById('stat-l1').textContent = tiers.L1.length;
    document.getElementById('stat-l2').textContent = tiers.L2.length;
    document.getElementById('stat-l3').textContent = tiers.L3.length;

    // Tier tables
    renderTierTable('table-l1', tiers.L1, pool, 'l1');
    renderTierTable('table-l2', tiers.L2, pool, 'l2');
    renderTierTable('table-l3', tiers.L3, pool, 'l3');

    document.getElementById('card-l1').style.display = tiers.L1.length ? '' : 'none';
    document.getElementById('card-l2').style.display = tiers.L2.length ? '' : 'none';
    document.getElementById('card-l3').style.display = tiers.L3.length ? '' : 'none';

    // TOP10
    renderTop10(rankings);
  }

  function renderTierTable(tableId, items, pool, tierType) {
    const container = document.getElementById(tableId);
    if (!items || !items.length) {
      container.innerHTML = '<div style="padding:12px;color:var(--text-tertiary);font-size:0.7rem;">（暂无指数入选）</div>';
      return;
    }

    let html = '<table class="data-table"><thead><tr>';
    html += '<th>代码</th><th>名称</th><th>RS_20</th><th>RS_60</th><th>RS_120</th><th>RS_250</th>';
    if (tierType === 'l2') html += '<th>加速力度</th>';
    if (tierType === 'l3') html += '<th>MA状态</th>';
    html += '</tr></thead><tbody>';

    for (const item of items) {
      const name = item.name || indexNames[item.code] || item.code;
      const rs20 = item.RS_20 ?? '—';
      const rs60 = item.RS_60 ?? '—';
      const rs120 = item.RS_120 ?? '—';
      const rs250 = item.RS_250 ?? '—';

      html += `<tr>
        <td class="mono">${item.code}</td>
        <td>${name}</td>
        <td class="${rsClass(rs20)}">${rs20}</td>
        <td class="${rsClass(rs60)}">${rs60}</td>
        <td class="${rsClass(rs120)}">${rs120}</td>
        <td class="${rsClass(rs250)}">${rs250}</td>`;
      if (tierType === 'l2') {
        html += `<td class="mono">${item.momentum_delta ?? '—'}</td>`;
      }
      if (tierType === 'l3') {
        const maDays = item.ma_days || 20;
        const maKey = `MA${maDays}`;
        const above = (item.close_above_ma || {})[maKey];
        html += `<td>${above === true ? '✅ 站上' + maDays + '日线' : above === false ? '❌ 低于' + maDays + '日线' : '—'}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    container.innerHTML = html;
  }

  function renderTop10(rankings) {
    const container = document.getElementById('table-top10');
    if (!rankings || !rankings.length) {
      container.innerHTML = '<div style="padding:12px;color:var(--text-tertiary);">暂无数据</div>';
      return;
    }

    const top10 = rankings.slice(0, 10);
    let html = '<table class="data-table"><thead><tr>';
    html += '<th>排名</th><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th>';
    html += '<th>RS_20</th><th>RS_60</th><th>RS_120</th><th>RS_250</th><th>类型</th>';
    html += '</tr></thead><tbody>';

    for (let i = 0; i < top10.length; i++) {
      const item = top10[i];
      const name = item.name || indexNames[item.code] || item.code;
      const change = item.change_pct ?? 0;
      const changeStr = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
      const changeCls = change > 0 ? 'up' : change < 0 ? 'down' : '';
      const tierLabel = getTierLabel(item);

      html += `<tr>
        <td>${i + 1}</td>
        <td class="mono">${item.code}</td>
        <td>${name}</td>
        <td class="mono">${item.close?.toFixed(2) ?? '—'}</td>
        <td class="${changeCls}">${changeStr}</td>
        <td class="${rsClass(item.RS_20)}">${item.RS_20 ?? '—'}</td>
        <td class="${rsClass(item.RS_60)}">${item.RS_60 ?? '—'}</td>
        <td class="${rsClass(item.RS_120)}">${item.RS_120 ?? '—'}</td>
        <td class="${rsClass(item.RS_250)}">${item.RS_250 ?? '—'}</td>
        <td>${tierLabel}</td>
      </tr>`;
    }
    html += '</tbody></table>';
    container.innerHTML = html;
  }

  function getTierLabel(item) {
    // Check if this item is in any tier (look across all pools)
    if (!currentData || !currentData.pools) return '—';
    for (const [pname, pdata] of Object.entries(currentData.pools)) {
      for (const tierName of ['L1','L2','L3']) {
        const tierItems = (pdata.tiers || {})[tierName] || [];
        if (tierItems.some(t => t.code === item.code)) {
          const labels = { L1: '🔴 L1', L2: '🟡 L2', L3: '🟣 L3' };
          return labels[tierName] || tierName;
        }
      }
    }
    return '—';
  }

  function rsClass(val) {
    if (val === null || val === undefined || val === '—') return '';
    if (val >= 90) return 'rs-high';
    if (val >= 70) return 'rs-mid';
    return '';
  }

  // ── Event bindings ──
  document.getElementById('btn-run').addEventListener('click', runBacktest);
  document.getElementById('btn-save').addEventListener('click', saveConfig);

  // ── Bootstrap ──
  init();

})();
