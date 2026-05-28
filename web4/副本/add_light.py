import re

f = open(r'D:\hanako\investment-system\web4\stock-valuation\index.html', 'r', encoding='utf-8')
h = f.read()
f.close()

light_css = """
  /* Light theme overrides */
  html[data-theme="light"] body{background:#f8f9fa;color:#1a1a2e}
  html[data-theme="light"] :root{--bg:#f8f9fa;--card:#ffffff;--border:rgba(0,0,0,.08);--muted:#6b7280;--accent:#d97706;--rise:#059669;--fall:#dc2626;--text-primary:#1a1a2e;--text-secondary:#4b5563;--text-tertiary:#6b7280;--card-bg:rgba(255,255,255,.8);--bg-surface:rgba(0,0,0,.02)}
  html[data-theme="light"] .chart-card,html[data-theme="light"] .xhs-card,html[data-theme="light"] .stat-card{background:rgba(255,255,255,.75);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid rgba(0,0,0,.06);box-shadow:0 1px 3px rgba(0,0,0,.04),0 4px 16px rgba(0,0,0,.04)}
  html[data-theme="light"] .stat-card:hover,html[data-theme="light"] .chart-card:hover,html[data-theme="light"] .xhs-card:hover{border-color:rgba(0,0,0,.1);box-shadow:0 4px 20px rgba(0,0,0,.06)}
  html[data-theme="light"] .stat-card .val,html[data-theme="light"] .metric-item .val{color:#1a1a2e}
  html[data-theme="light"] .chart-title,html[data-theme="light"] .xhs-card-label{color:#374151}
  html[data-theme="light"] .tab{background:rgba(255,255,255,.6);border:1px solid rgba(0,0,0,.08);color:#6b7280}
  html[data-theme="light"] .tab:hover{border-color:rgba(0,0,0,.15);color:#374151}
  html[data-theme="light"] .tab.active{background:rgba(217,119,6,.08);color:#d97706;border-color:rgba(217,119,6,.2)}
  html[data-theme="light"] .top-bar input,html[data-theme="light"] .top-bar select{background:rgba(255,255,255,.7);border:1px solid rgba(0,0,0,.08);color:#1a1a2e}
  html[data-theme="light"] .top-bar label{color:#6b7280}
  html[data-theme="light"] .analysis-text{color:#4b5563;background:rgba(0,0,0,.02);border:1px solid rgba(0,0,0,.04)}
  html[data-theme="light"] .mini-table th{color:#6b7280;border-bottom:1px solid rgba(0,0,0,.06)}
  html[data-theme="light"] .mini-table td{border-bottom:1px solid rgba(0,0,0,.03)}
  html[data-theme="light"] .mini-table tr:hover td{background:rgba(0,0,0,.02)}
  html[data-theme="light"] .nav-dropdown-menu{background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.08);box-shadow:0 12px 40px rgba(0,0,0,.1)}
  html[data-theme="light"] .nav-dropdown-menu a{color:#6b7280}
  html[data-theme="light"] .nav-dropdown-menu a:hover{background:rgba(217,119,6,.06);color:#1a1a2e}
  html[data-theme="light"] .top-nav{background:rgba(255,255,255,.75);border:1px solid rgba(0,0,0,.06)}
  html[data-theme="light"] .nav-brand{color:#374151}
  html[data-theme="light"] .nav-item{color:#6b7280}
  html[data-theme="light"] .nav-item:hover{color:#1a1a2e;background:rgba(0,0,0,.03)}
  html[data-theme="light"] .nav-item.active{color:#d97706;background:rgba(217,119,6,.08)}
  html[data-theme="light"] .theme-toggle{color:#6b7280;border:1px solid rgba(0,0,0,.1)}
  html[data-theme="light"] .theme-toggle:hover{border-color:rgba(0,0,0,.2);color:#1a1a2e}
  html[data-theme="light"] .metric-item{background:rgba(0,0,0,.02);border:1px solid rgba(0,0,0,.04)}
  html[data-theme="light"] .tag-green{background:rgba(5,150,105,.08);color:#059669;border:1px solid rgba(5,150,105,.15)}
  html[data-theme="light"] .tag-red{background:rgba(220,38,38,.08);color:#dc2626;border:1px solid rgba(220,38,38,.15)}
  html[data-theme="light"] .tag-orange{background:rgba(217,119,6,.08);color:#d97706;border:1px solid rgba(217,119,6,.15)}
  html[data-theme="light"] #bg-canvas{opacity:.25}
  html[data-theme="light"] .btn-analysis{color:#6b7280;border:1px solid rgba(0,0,0,.1)}
  html[data-theme="light"] .btn-analysis:hover{color:#1a1a2e;background:rgba(0,0,0,.03)}
  html[data-theme="light"] .stock-header .code{color:#6b7280}
  html[data-theme="light"] .stock-header .name{color:#1a1a2e}
  html[data-theme="light"] .xhs-loading,html[data-theme="light"] .loading-row{color:#6b7280}
"""

# Insert before @media
h = h.replace('@media(max-width:768px)', light_css + '\n  @media(max-width:768px)')

f = open(r'D:\hanako\investment-system\web4\stock-valuation\index.html', 'w', encoding='utf-8')
f.write(h)
f.close()
print('Light mode CSS added')
