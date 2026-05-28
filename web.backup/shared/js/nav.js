/**
 * Nav.js — 欧奈尔投资系统全站统一导航栏
 *
 * 所有页面引用此文件，导航栏自动生成。新增页面只需改一处。
 *
 * 用法:
 *   <nav id="top-nav"></nav>
 *   <script src="../shared/js/nav.js"></script>
 *   <script>Nav.init({brandIcon:'🔎',brandText:'形态识别',currentPage:'pattern-scan'})</script>
 *
 * currentPage 取值：
 *   'home' | 'distribution-day' | 'follow-through-day' | 'accumulation-day'
 *   | 'index-rs-backtest' | 'index-crowdedness' | 'stock-rs-backtest'
 *   | 'index-ad-backtest' | 'divergence-backtest' | 'strongest-index'
 *   | 'cup-handle-backtest' | 'base-breakout' | 'pocket-pivot'
 *   | 'pattern-scan' | 'canslim-scorecard' | 'saucer-base-backtest'
 *   | 'index-scan' | 'index-valuation' | 'stock-valuation' | 'market-scan'
 *   | 'daily-pattern-scan' | 'canslim-scores'
 *   | 'railroad-tracks' | 'climax-top' | 'top-pattern' | 'double-bottom' | 'flat-base'
 *   | 'breakout-failure'
 *   | 'discipline' | 'discipline-observation' | 'discipline-watchlist' | 'discipline-trades'
 */

// ── API 代理：前端与后端分离部署时，自动将 /api/ 请求转发到 Flask ──
(function () {
  var API_BASE = 'http://localhost:8788';
  var _fetch = window.fetch;
  window.fetch = function (url, options) {
    if (typeof url === 'string' && url.indexOf('/api/') === 0) {
      url = API_BASE + url;
    }
    return _fetch.call(window, url, options);
  };
})();

(function (global) {
  'use strict';

  var Nav = {};
  var config = {};

  // ─── 导航结构定义（增删页面只改这里） ───
  var BACKTEST_ITEMS = [
    { href: '../distribution-day/',     icon: '📉', label: '抛盘日',           page: 'distribution-day' },
    { href: '../follow-through-day/',   icon: '📈', label: '追盘日',           page: 'follow-through-day' },
    { href: '../accumulation-day/',     icon: '📦', label: '吸筹日',           page: 'accumulation-day' },
    { href: '../index-rs-backtest/',    icon: '🏆', label: '指数RS强度',       page: 'index-rs-backtest' },
    { href: '../index-crowdedness/',    icon: '📊', label: '指数拥挤度',       page: 'index-crowdedness' },
    { href: '../stock-rs-backtest/',    icon: '💪', label: '个股RS强度',       page: 'stock-rs-backtest' },
    { href: '../index-ad-backtest/',    icon: '🔍', label: '机构吸筹/出货',    page: 'index-ad-backtest' },
    { href: '../divergence-backtest/',  icon: '⚠️', label: '指数背离',         page: 'divergence-backtest' },
    { href: '../strongest-index/',      icon: '⭐', label: '最强指数',         page: 'strongest-index' },
    { href: '../cup-handle-backtest/',  icon: '☕', label: '杯柄形态',         page: 'cup-handle-backtest' },
    { href: '../double-bottom/',        icon: '📐', label: '双重底',           page: 'double-bottom' },
    { href: '../flat-base/',            icon: '📏', label: '扁平基部',         page: 'flat-base' },
    { href: '../saucer-base-backtest/', icon: '🥏', label: '碟形基部',         page: 'saucer-base-backtest' },
    { href: '../base-breakout/',        icon: '🏔️', label: '基部突破',         page: 'base-breakout' },
    { href: '../pocket-pivot/',         icon: '🎯', label: '口袋支点',         page: 'pocket-pivot' },
    { href: '../railroad-tracks/',      icon: '🚂', label: '铁轨线',           page: 'railroad-tracks' },
    { href: '../climax-top/',           icon: '📉', label: '高潮见顶',         page: 'climax-top' },
    { href: '../top-pattern/',          icon: '⛰️', label: '头部形态',         page: 'top-pattern' },
    { href: '../volume-divergence/',    icon: '📊', label: '量价背离',         page: 'volume-divergence' },
    { href: '../breakout-failure/',    icon: '⚠️', label: '突破失败',         page: 'breakout-failure' },
    { href: '../pattern-scan/',         icon: '🔎', label: '形态识别',         page: 'pattern-scan' },
    { href: '../canslim-scorecard/',    icon: '🎯', label: 'CAN SLIM 评分卡',  page: 'canslim-scorecard' },
    { href: '../discipline/screening-backtest.html', icon: '📊', label: '精选回测', page: 'screening-backtest' },
    { href: '../discipline/screening-backtest-index.html', icon: '📈', label: '指数回测', page: 'screening-backtest-index' },
  ];

  var MAIN_ITEMS = [
    { href: '../index-scan/',           icon: '🔬', label: '指数扫描',         page: 'index-scan' },
    { href: '../index-valuation/',      icon: '📈', label: '指数估值',         page: 'index-valuation' },
    { href: '../stock-valuation/',      icon: '💎', label: '个股扫描',         page: 'stock-valuation' },
    { href: '../market-scan/',          icon: '📊', label: '大盘扫描',         page: 'market-scan' },
    { href: '../daily-pattern-scan/',   icon: '📋', label: '形态扫描',         page: 'daily-pattern-scan' },
    { href: '../canslim-scores/',       icon: '🎯', label: 'CAN SLIM',          page: 'canslim-scores' },
    { href: '../pattern-scan/',         icon: '🔎', label: '形态识别',         page: 'pattern-scan' },
  ];

  function render() {
    var el = document.getElementById('top-nav');
    if (!el) return;
    el.className = 'top-nav';

    var cp = config.currentPage || '';

    var html = '<div class="nav-brand"><span class="nav-fox">' + (config.brandIcon || '🦊') + '</span><span>' + (config.brandText || '') + '</span>';
    if (config.brandSub) html += '<span class="nav-greeting">' + config.brandSub + '</span>';
    html += '</div><div class="nav-links">';

    // 首页
    html += '<a href="../" class="nav-item' + (cp === 'home' ? ' active' : '') + '">看板</a>';

    // 回测下拉
    html += '<div class="nav-dropdown"><a href="javascript:void(0)" class="nav-item' + (BACKTEST_ITEMS.some(function (b) { return b.page === cp; }) ? ' active' : '') + '">回测 ▾</a><div class="nav-dropdown-menu">';
    for (var i = 0; i < BACKTEST_ITEMS.length; i++) {
      var b = BACKTEST_ITEMS[i];
      html += '<a href="' + b.href + '" class="' + (b.page === cp ? 'active' : '') + '">' + b.label + '</a>';
    }
    html += '</div></div>';

    // 主导航项
    for (var j = 0; j < MAIN_ITEMS.length; j++) {
      var m = MAIN_ITEMS[j];
      html += '<a href="' + m.href + '" class="nav-item' + (m.page === cp ? ' active' : '') + '">' + m.label + '</a>';
    }

    // 仓位管理 → 知行系统
    html += '<a href="../discipline/" class="nav-item' + (cp === 'discipline' ? ' active' : '') + '">知行</a>';
    // 精选
    html += '<a href="../discipline/screening.html" class="nav-item' + (cp === 'screening' ? ' active' : '') + '">精选</a>';
    // 主题按钮
    html += '<button class="theme-toggle" onclick="if(typeof toggleTheme==\'function\')toggleTheme();else{document.documentElement.dataset.theme=document.documentElement.dataset.theme===\'dark\'?\'light\':\'dark\'}">🌙</button>';

    html += '</div>';
    el.innerHTML = html;
  }

  Nav.init = function (cfg) {
    config = cfg || {};
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', render);
    } else {
      render();
    }
  };

  // 暴露给全局
  global.Nav = Nav;

})(typeof window !== 'undefined' ? window : this);
