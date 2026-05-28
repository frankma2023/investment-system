/**
 * Nav.js (Glass Q Edition) — 玻璃拟态Q版导航栏
 *
 * 用法:
 *   <nav id="top-nav"></nav>
 *   <script src="../shared/js/nav.js"></script>
 *   <script>Nav.init({brandText:'每日精选',currentPage:'screening'})</script>
 */

(function (global) {
  'use strict';
  var Nav = {}, config = {};

  var BACKTEST_ITEMS = [
    { href: '../distribution-day/',     icon: '📉', label: '抛盘日',           page: 'distribution-day' },
    { href: '../follow-through-day/',   icon: '📈', label: '追盘日',           page: 'follow-through-day' },
    { href: '../accumulation-day/',     icon: '📦', label: '吸筹日',           page: 'accumulation-day' },
    { href: '../index-rs-backtest/',    icon: '🏆', label: '指数RS强度',       page: 'index-rs-backtest' },
    { href: '../index-crowdedness/',    icon: '📊', label: '指数拥挤度',       page: 'index-crowdedness' },
    { href: '../stock-rs-backtest/',    icon: '💪', label: '个股RS强度',       page: 'stock-rs-backtest' },
    { href: '../index-ad-backtest/',    icon: '🔍', label: '机构吸筹/出货',    page: 'index-ad-backtest' },
    { href: '../divergence-backtest/',  icon: '⚠️', label: '指数背离',         page: 'divergence-backtest' },
    { href: '../base-breakout/',        icon: '🏔️', label: '基部突破',         page: 'base-breakout' },
    { href: '../breakout-failure/',     icon: '⚠️', label: '突破失败',         page: 'breakout-failure' },
    { href: '../cup-handle-backtest/',  icon: '☕', label: '杯柄形态',         page: 'cup-handle-backtest' },
    { href: '../saucer-base-backtest/', icon: '🥏', label: '碟形基部',         page: 'saucer-base-backtest' },
    { href: '../double-bottom/',        icon: '📐', label: '双重底',           page: 'double-bottom' },
    { href: '../flat-base/',            icon: '📏', label: '扁平基部',         page: 'flat-base' },
    { href: '../climax-top/',           icon: '📉', label: '高潮见顶',         page: 'climax-top' },
    { href: '../railroad-tracks/',      icon: '🚂', label: '铁轨线',           page: 'railroad-tracks' },
    { href: '../top-pattern/',          icon: '⛰️', label: '头部形态',         page: 'top-pattern' },
    { href: '../volume-divergence/',    icon: '📊', label: '量价背离',         page: 'volume-divergence' },
    { href: '../pocket-pivot/',         icon: '🎯', label: '口袋支点',         page: 'pocket-pivot' },
    { href: '../pattern-scan/',         icon: '🔎', label: '形态识别',         page: 'pattern-scan' },
  ];

  var MAIN_ITEMS = [
    { href: '../market-scan/',          icon: '📊', label: '大盘扫描',         page: 'market-scan' },
    { href: '../index-scan/',           icon: '🔬', label: '指数扫描',         page: 'index-scan' },
    { href: '../stock-valuation/',      icon: '💎', label: '个股扫描',         page: 'stock-valuation' },
    { href: '../pattern-scan/',         icon: '🔎', label: '形态识别',         page: 'pattern-scan' },
    { href: '../daily-pattern-scan/',   icon: '📋', label: '形态扫描',         page: 'daily-pattern-scan' },
    { href: '../canslim-scores/',       icon: '🎯', label: 'CAN SLIM',          page: 'canslim-scores' },
    { href: '../discipline/screening.html', icon: '⭐', label: '每日精选',     page: 'screening' },
    { href: '../discipline/',           icon: '🧠', label: '知行',              page: 'discipline' },
  ];

  function render() {
    var el = document.getElementById('top-nav');
    if (!el) return;

    var cp = config.currentPage || '';

    // Build nav with glass Q style
    var html = '<div style="display:flex;align-items:center;justify-content:space-between;width:100%">';

    // Brand
    html += '<div style="font-family:Nunito,sans-serif;font-size:.78rem;font-weight:900;letter-spacing:-.02em;background:linear-gradient(135deg,#FF6B8A,#A78BFA);-webkit-background-clip:text;-webkit-text-fill-color:transparent">' + (config.brandText || '') + '</div>';

    // Links
    html += '<div style="display:flex;gap:8px;align-items:center">';

    // Home
    var homeActive = cp === 'home';
    html += '<a href="../" style="font-size:.58rem;font-weight:700;color:' + (homeActive?'#A78BFA':'#8B6B9E') + ';text-decoration:none;padding:3px 8px;border-radius:12px;transition:all .2s' + (homeActive?';background:rgba(167,139,250,.1)':'') + '">🏠</a>';

    // Backtest dropdown
    var isBacktest = BACKTEST_ITEMS.some(function(b) { return b.page === cp; });
    html += '<div class="nav-drop" style="position:relative;display:inline-flex">';
    html += '<a href="javascript:void(0)" style="font-size:.58rem;font-weight:700;color:' + (isBacktest?'#A78BFA':'#8B6B9E') + ';text-decoration:none;padding:3px 8px;border-radius:12px;cursor:pointer;transition:all .2s' + (isBacktest?';background:rgba(167,139,250,.1)':'') + '">回测 ▾</a>';
    html += '<div class="nav-drop-menu" style="display:none;position:absolute;top:100%;left:0;background:rgba(255,255,255,.85);backdrop-filter:blur(30px);-webkit-backdrop-filter:blur(30px);border:2px solid rgba(255,255,255,.65);border-radius:18px;padding:4px 0;min-width:130px;z-index:999;box-shadow:0 8px 30px rgba(167,139,250,.15)">';
    for (var i = 0; i < BACKTEST_ITEMS.length; i++) {
      var b = BACKTEST_ITEMS[i];
      html += '<a href="' + b.href + '" style="display:block;padding:5px 14px;font-size:.55rem;color:' + (b.page===cp?'#A78BFA;font-weight:700':'#8B6B9E;font-weight:400') + ';text-decoration:none">' + b.icon + ' ' + b.label + '</a>';
    }
    html += '</div></div>';

    // Main items
    for (var j = 0; j < MAIN_ITEMS.length; j++) {
      var m = MAIN_ITEMS[j];
      var active = m.page === cp;
      html += '<a href="' + m.href + '" style="font-size:.58rem;font-weight:' + (active?'700':'400') + ';color:' + (active?'#A78BFA':'#8B6B9E') + ';text-decoration:none;padding:3px 8px;border-radius:12px;transition:all .2s' + (active?';background:rgba(167,139,250,.1)':'') + '">' + m.icon + ' ' + m.label + '</a>';
    }

    html += '</div></div>';
    el.innerHTML = html;

    // Hover events for dropdown
    var drops = el.querySelectorAll('.nav-drop');
    drops.forEach(function(drop) {
      var menu = drop.querySelector('.nav-drop-menu');
      drop.addEventListener('mouseenter', function() { menu.style.display = 'block'; });
      drop.addEventListener('mouseleave', function() { menu.style.display = 'none'; });
    });

    // Hover effects on all links
    var links = el.querySelectorAll('a');
    links.forEach(function(a) {
      a.addEventListener('mouseenter', function() {
        if (!this.classList.contains('active-nav')) {
          this.style.background = 'rgba(167,139,250,0.08)';
          this.style.color = '#A78BFA';
          this.style.transform = 'translateY(-1px)';
          this.style.boxShadow = '0 3px 10px rgba(167,139,250,0.15)';
        }
      });
      a.addEventListener('mouseleave', function() {
        if (!this.classList.contains('active-nav')) {
          this.style.background = '';
          this.style.color = '';
          this.style.transform = '';
          this.style.boxShadow = '';
        }
      });
    });
  }

  Nav.init = function(cfg) {
    config = cfg || {};
    render();
  };

  global.Nav = Nav;
})(window);
