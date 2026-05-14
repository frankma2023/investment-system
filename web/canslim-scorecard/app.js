/**
 * CAN SLIM 评分卡 前端逻辑
 */
var API = 'http://localhost:8788/api/canslim-score';
var API_CFG = 'http://localhost:8788/api/config?signal_type=canslim_scorecard';
var chart = null;

document.addEventListener('DOMContentLoaded', function() {
  var today = new Date().toISOString().slice(0, 10);
  document.getElementById('date').value = today;
  chart = echarts.init(document.getElementById('radar-chart'));
  document.querySelector('.theme-toggle').addEventListener('click', function() {
    var html = document.documentElement;
    html.dataset.theme = html.dataset.theme === 'light' ? 'dark' : 'light';
    this.textContent = html.dataset.theme === 'light' ? '🌙' : '☀️';
  });
  loadConfig();
  doScore();
});

function doScore() {
  var code = document.getElementById('code').value.trim();
  var date = document.getElementById('date').value;
  var btn = document.querySelector('.btn-run');
  btn.disabled = true; btn.textContent = '...';

  fetch(API + '?code=' + code + '&date=' + date)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      renderScore(d);
      renderRadar(d);
    })
    .catch(function(e) { alert('Error: ' + e.message); })
    .finally(function() { btn.disabled = false; btn.textContent = '🎯 评分'; });
}

function renderScore(d) {
  var dims = ['C','A','N','S','L','I'];
  var maxes = [23, 17, 14, 9, 21, 18];
  dims.forEach(function(dim, i) {
    var s = d[dim];
    document.getElementById(dim.toLowerCase() + '-score').textContent = s.score + '/' + maxes[i];
    document.getElementById(dim.toLowerCase() + '-detail').textContent = s.detail || '';
  });
  document.getElementById('total-score').textContent = d.score + '/100';
  var badge = document.getElementById('grade-badge');
  badge.textContent = d.grade + '级';
  badge.className = 'grade-badge grade-' + d.grade;
  if (d.M && d.M.position) {
    document.getElementById('m-advice').textContent = '大盘: ' + d.M.position;
  }
}

function renderRadar(d) {
  var dims = ['C','A','N','S','L','I'];
  var maxes = [23, 17, 14, 9, 21, 18];
  var labels = ['C 当期盈利','A 年度盈利','N 形态新高','S 供给需求','L 领军股','I 机构认同'];
  var values = dims.map(function(dim, i) {
    return Math.round(d[dim].score / maxes[i] * 100);
  });

  chart.setOption({
    radar: {
      indicator: labels.map(function(l) { return {name: l, max: 100}; }),
      shape: 'polygon',
      radius: '60%',
      axisName: { fontSize: 10, color: 'var(--text-tertiary)' }
    },
    series: [{
      type: 'radar',
      data: [{value: values, name: d.stock_code,
        areaStyle: {color: 'rgba(254,44,85,0.15)'},
        lineStyle: {color: '#FE2C55', width: 2},
        itemStyle: {color: '#FE2C55'}
      }],
      symbol: 'circle', symbolSize: 6
    }]
  }, true);
}

function saveResults() {
  var code = document.getElementById('code').value.trim();
  var date = document.getElementById('date').value;
  var btn = event.target;
  btn.textContent = '保存中...'; btn.disabled = true;

  fetch(API, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({stock_code: code, date: date})
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    btn.textContent = d.saved ? '✅ 已保存' : '失败';
    setTimeout(function() { btn.textContent = '💾 保存结果'; btn.disabled = false; }, 2000);
  })
  .catch(function(e) { alert('Error: ' + e); btn.textContent = '💾 保存结果'; btn.disabled = false; });
}

function saveConfig() {
  // Collect params from input fields and save via /api/config
  var config = {canslim_scorecard: {}};
  document.querySelectorAll('.param-card-bd input').forEach(function(inp) {
    var path = inp.dataset.path;
    var val = inp.type === 'number' ? parseFloat(inp.value) : inp.value;
    var keys = path.split('.');
    var obj = config.canslim_scorecard;
    for (var i = 0; i < keys.length - 1; i++) {
      if (!obj[keys[i]]) obj[keys[i]] = {};
      obj = obj[keys[i]];
    }
    obj[keys[keys.length - 1]] = val;
  });

  fetch(API_CFG, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({signal_type: 'canslim_scorecard', config: config})
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    var btn = event.target;
    btn.textContent = '✅ 已保存';
    setTimeout(function() { btn.textContent = '⚙️ 保存配置'; }, 2000);
  });
}

function loadConfig() {
  fetch(API_CFG)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d || !d.canslim_scorecard) return;
      var cfg = d.canslim_scorecard;
      // Build simplified param inputs
      var sections = {
        'c': {
          title: 'C 当期盈利', paths: [
            ['eps_yoy_tiers', 'EPS增速阈值(优秀/良好/及格 %)', '25,18,10'],
            ['eps_yoy_scores', '对应得分', '12,8,5'],
            ['eps_accel_threshold', '加速度阈值(%)', '10'],
            ['revenue_yoy_tiers', '营收增速阈值(%)', '25,15'],
            ['nonrecurring_ratio', '扣非占比阈值(%)', '90'],
          ]
        },
        'a': {
          title: 'A 年度盈利', paths: [
            ['eps_cagr_3y_tiers', '3年CAGR阈值(%)', '25,15,5'],
            ['stability_cv_threshold', '稳定性CV阈值(%)', '30'],
          ]
        },
        'n': {
          title: 'N 形态新高', paths: [
            ['high52_tiers', '52周高点阈值(%)', '-5,-15'],
            ['high52_scores', '对应得分', '7,5'],
            ['high_lookback_days', '回溯天数', '5'],
          ]
        },
        's': {
          title: 'S 供给需求', paths: [
            ['market_cap_tiers', '市值分档(亿)', '50,200,500'],
            ['vol_ratio_tiers', '量比阈值', '1.5,1.2'],
          ]
        },
        'l': {
          title: 'L 领军股', paths: [
            ['rs250_tiers', 'RS250阈值', '95,90,80,70'],
            ['excess_return_threshold', '超额收益阈值(%)', '5'],
          ]
        },
        'i': {
          title: 'I 机构认同', paths: [
            ['inst_holding_tiers', '机构持股阈值(%)', '15,5,1'],
            ['analyst_coverage_tiers', '研报覆盖阈值', '3,1'],
            ['debt_ratio_warning', '负债率警告阈值(%)', '60'],
          ]
        }
      };

      Object.keys(sections).forEach(function(key) {
        var sec = sections[key];
        var div = document.getElementById('params-' + key);
        var html = '';
        sec.paths.forEach(function(p) {
          var val = getNested(cfg, p[0]) || p[2];
          html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;font-size:0.6rem">';
          html += '<span style="width:130px;flex-shrink:0;color:var(--text-tertiary)">' + p[1] + '</span>';
          html += '<input type="text" data-path="' + key + '.' + p[0] + '" value="' + val + '" style="flex:1;padding:3px 6px;border:1px solid var(--divider);border-radius:6px;font-size:0.6rem;background:var(--card-bg);color:var(--text-primary)">';
          html += '</div>';
        });
        div.innerHTML = html;
      });
    });
}

function getNested(obj, path) {
  return path.split('.').reduce(function(o, k) { return o ? o[k] : null; }, obj);
}
