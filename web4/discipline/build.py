import re

f = open(r'D:\hanako\investment-system\web\discipline\screening.html', 'r', encoding='utf-8')
h = f.read()
f.close()

# New head
new_head = '''<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="UTF-8">
<link rel="icon" href="../images/favicon.svg" type="image/svg+xml">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日精选 · 知行</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{surface:'#0f0f12',card:'#1a1a1f',border:'rgba(255,255,255,.06)',muted:'#8b8b90',accent:'#f59e0b'},fontFamily:{sans:['Inter','system-ui','sans-serif'],display:['Instrument Serif','Georgia','serif'],mono:['JetBrains Mono','Fira Code','monospace']}}}}</script>
<style>
  *,::before,::after{box-sizing:border-box;margin:0;padding:0}
  body{background:#0f0f12;color:#e4e4e7;font-family:'Inter',system-ui,sans-serif;font-size:13px;line-height:1.5;min-height:100vh;overflow-x:hidden}
  :root{--bg:#0f0f12;--card:#1a1a1f;--border:rgba(255,255,255,.06);--muted:#8b8b90;--accent:#f59e0b;--rise:#10b981;--fall:#ef4444;--font-display:'Instrument Serif',Georgia,serif;--color-up:#10b981;--color-down:#ef4444;--color-accent:#f59e0b;--color-accent-subtle:rgba(245,158,11,.08);--text-primary:#e4e4e7;--text-secondary:#a1a1aa;--text-tertiary:var(--muted);--divider:rgba(255,255,255,.06);--card-bg:rgba(26,26,31,.6);--bg-surface:rgba(255,255,255,.02)}

  #bg-canvas{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.4}
  .container,.app-container{max-width:1340px;margin:0 auto;padding:20px 24px 48px;position:relative;z-index:1}

  /* Hero */
  .panel-header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px}
  .panel-header h1{font-family:var(--font-display);font-size:1.2rem;font-weight:400;color:#d4d4d8;letter-spacing:-.01em}
  .mkt-badge{display:inline-block;font-size:11px;font-weight:500;padding:4px 14px;border-radius:12px;border:1px solid var(--border);backdrop-filter:blur(10px)}
  .mkt-up{color:var(--rise);background:rgba(16,185,129,.08);border-color:rgba(16,185,129,.2)}
  .mkt-cor{color:var(--accent);background:rgba(245,158,11,.08);border-color:rgba(245,158,11,.2)}
  .mkt-bear{color:var(--fall);background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.2)}
  .info-row{font-size:11px;color:var(--muted);margin:4px 0 10px}

  /* Tabs */
  .mode-tabs{display:flex;gap:6px;margin:10px 0}
  .mode-tab{padding:7px 18px;border:1px solid var(--border);border-radius:10px;font-family:'Inter',system-ui,sans-serif;font-size:12px;font-weight:500;cursor:pointer;background:rgba(26,26,31,.4);color:var(--muted);transition:all .2s;backdrop-filter:blur(10px)}
  .mode-tab:hover{border-color:rgba(255,255,255,.15);color:#d4d4d8}
  .mode-tab.active{background:rgba(245,158,11,.12);color:var(--accent);border-color:rgba(245,158,11,.3)}

  /* Toolbar */
  .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0 16px}
  .toolbar input,.toolbar select{font-family:'Inter',system-ui,sans-serif;padding:7px 12px;border:1px solid var(--border);border-radius:10px;font-size:12px;background:rgba(26,26,31,.6);color:#e4e4e7;outline:none;transition:all .2s;backdrop-filter:blur(10px)}
  .toolbar input:focus,.toolbar select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,158,11,.1)}
  .toolbar input::placeholder{color:var(--muted)}

  /* Table */
  .scr-table{width:100%;border-collapse:collapse;font-size:12px}
  .scr-table thead{position:sticky;top:0;z-index:5}
  .scr-table th{text-align:center;padding:9px 4px;border-bottom:1px solid var(--border);font-size:10px;font-weight:500;color:var(--muted);cursor:pointer;user-select:none;white-space:nowrap;background:rgba(26,26,31,.9);backdrop-filter:blur(10px);text-transform:uppercase;letter-spacing:.04em}
  .scr-table th:hover{color:#d4d4d8}
  .scr-table td{padding:8px 4px;border-bottom:1px solid rgba(255,255,255,.03);text-align:center;font-weight:300}
  .scr-table tbody tr:hover{background:rgba(255,255,255,.02)}
  .scr-table a{color:var(--accent);text-decoration:none;font-weight:500}

  /* Tags */
  .tag{display:inline-block;padding:2px 7px;border-radius:6px;font-size:10px;font-weight:500}
  .tag-l{background:rgba(168,85,247,.12);color:#a78bfa;border:1px solid rgba(168,85,247,.2)}
  .tag-b{background:rgba(6,182,212,.12);color:#06b6d4;border:1px solid rgba(6,182,212,.2)}
  .tag-d{background:rgba(239,68,68,.12);color:var(--fall);border:1px solid rgba(239,68,68,.2)}

  /* Score bar */
  .score-bar{display:inline-block;height:5px;border-radius:3px;vertical-align:middle;margin-right:3px;transition:width .4s ease}

  /* Buttons */
  .btn-xs{font-family:'Inter',system-ui,sans-serif;font-size:10px;font-weight:500;padding:4px 10px;border:1px solid var(--border);border-radius:8px;cursor:pointer;background:rgba(26,26,31,.5);color:var(--muted);text-decoration:none;display:inline-block;transition:all .2s}
  .btn-xs:hover{color:#d4d4d8;background:rgba(255,255,255,.04);border-color:rgba(255,255,255,.1)}
  .btn-xs.add{background:rgba(245,158,11,.12);color:var(--accent);border-color:rgba(245,158,11,.3)}
  .btn-xs.add:hover{background:rgba(245,158,11,.18)}

  /* Modal */
  .modal-overlay{background:rgba(0,0,0,.55);backdrop-filter:blur(6px)}
  .modal-card{background:rgba(26,26,31,.9);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid var(--border);border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.4)}
  .modal-card h2{font-family:var(--font-display);font-size:1rem;font-weight:400;color:#d4d4d8;letter-spacing:-.01em}
  .modal-close-btn{background:none;border:none;font-size:1.2rem;cursor:pointer;color:var(--muted);transition:color .2s}
  .modal-close-btn:hover{color:#d4d4d8}

  /* Loading */
  .loading{text-align:center;padding:40px;color:var(--muted);font-weight:300}

  /* Nav */
  .top-nav{display:flex;align-items:center;justify-content:space-between;padding:8px 18px;margin-bottom:18px;background:rgba(26,26,31,.7);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--border);border-radius:14px;position:relative;z-index:100}
  .nav-brand{display:flex;align-items:center;gap:8px;font-family:'Inter',system-ui,sans-serif;font-size:13px;font-weight:500;color:#d4d4d8;letter-spacing:-.01em}
  .nav-links{display:flex;gap:4px;align-items:center}
  .nav-item{font-family:'Inter',system-ui,sans-serif;font-size:11px;font-weight:500;color:var(--muted);text-decoration:none;padding:5px 10px;border-radius:8px;transition:all .2s ease}
  .nav-item:hover{color:#d4d4d8;background:rgba(255,255,255,.04)}
  .nav-item.active{color:var(--accent);background:rgba(245,158,11,.1)}
  .nav-dropdown{position:relative;display:inline-flex}
  .nav-dropdown-menu{display:none;position:absolute;top:100%;left:0;background:rgba(20,20,25,.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--border);border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.4);min-width:150px;padding:6px 0;z-index:200;white-space:nowrap}
  .nav-dropdown:hover .nav-dropdown-menu{display:block}
  .nav-dropdown-menu a{display:block;padding:7px 16px;font-size:12px;color:var(--muted);text-decoration:none;transition:all .15s;font-family:'Inter',system-ui,sans-serif}
  .nav-dropdown-menu a:hover{background:rgba(245,158,11,.08);color:#e4e4e7}
  .nav-dropdown-menu a.active{color:var(--accent);background:rgba(245,158,11,.1)}
  .theme-toggle{width:28px;height:28px;border:1px solid var(--border);border-radius:8px;background:transparent;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;transition:all .2s;color:var(--muted)}
  .theme-toggle:hover{border-color:rgba(255,255,255,.2);color:#d4d4d8}

  /* Table wrapper (glass card) */
  .table-shell{background:rgba(26,26,31,.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.2),0 4px 16px rgba(0,0,0,.1)}

  /* Light theme overrides */
  html[data-theme="light"] body{background:#f8f9fa;color:#1a1a2e}
  html[data-theme="light"] :root{--bg:#f8f9fa;--card:#ffffff;--border:rgba(0,0,0,.08);--muted:#6b7280;--accent:#d97706;--rise:#059669;--fall:#dc2626;--text-primary:#1a1a2e;--text-secondary:#4b5563;--text-tertiary:#6b7280;--card-bg:rgba(255,255,255,.8);--bg-surface:rgba(0,0,0,.02)}
  html[data-theme="light"] .top-nav,.container,.app-container .table-shell{background:rgba(255,255,255,.75);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid rgba(0,0,0,.06)}
  html[data-theme="light"] .panel-header h1{color:#374151}
  html[data-theme="light"] .info-row{color:#6b7280}
  html[data-theme="light"] .mode-tab{background:rgba(255,255,255,.6);border:1px solid rgba(0,0,0,.08);color:#6b7280}
  html[data-theme="light"] .mode-tab:hover{border-color:rgba(0,0,0,.15);color:#374151}
  html[data-theme="light"] .mode-tab.active{background:rgba(217,119,6,.08);color:#d97706;border-color:rgba(217,119,6,.2)}
  html[data-theme="light"] .toolbar input,html[data-theme="light"] .toolbar select{background:rgba(255,255,255,.7);border:1px solid rgba(0,0,0,.08);color:#1a1a2e}
  html[data-theme="light"] .scr-table th{background:rgba(255,255,255,.9);color:#6b7280;border-bottom:1px solid rgba(0,0,0,.06)}
  html[data-theme="light"] .scr-table td{border-bottom:1px solid rgba(0,0,0,.03)}
  html[data-theme="light"] .scr-table tbody tr:hover{background:rgba(0,0,0,.02)}
  html[data-theme="light"] .btn-xs{background:rgba(255,255,255,.6);border:1px solid rgba(0,0,0,.08);color:#6b7280}
  html[data-theme="light"] .btn-xs:hover{color:#1a1a2e;background:rgba(0,0,0,.03)}
  html[data-theme="light"] .btn-xs.add{background:rgba(217,119,6,.08);color:#d97706;border-color:rgba(217,119,6,.2)}
  html[data-theme="light"] .modal-card{background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.06)}
  html[data-theme="light"] .modal-card h2{color:#374151}
  html[data-theme="light"] .loading{color:#6b7280}
  html[data-theme="light"] .nav-brand{color:#374151}
  html[data-theme="light"] .nav-item{color:#6b7280}
  html[data-theme="light"] .nav-item:hover{color:#1a1a2e;background:rgba(0,0,0,.03)}
  html[data-theme="light"] .nav-item.active{color:#d97706;background:rgba(217,119,6,.08)}
  html[data-theme="light"] .nav-dropdown-menu{background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.08);box-shadow:0 12px 40px rgba(0,0,0,.1)}
  html[data-theme="light"] .nav-dropdown-menu a{color:#6b7280}
  html[data-theme="light"] .nav-dropdown-menu a:hover{background:rgba(217,119,6,.06);color:#1a1a2e}
  html[data-theme="light"] .tag-l{background:rgba(168,85,247,.08);color:#7c3aed;border:1px solid rgba(168,85,247,.15)}
  html[data-theme="light"] .tag-b{background:rgba(6,182,212,.08);color:#0891b2;border:1px solid rgba(6,182,212,.15)}
  html[data-theme="light"] .tag-d{background:rgba(239,68,68,.08);color:#dc2626;border:1px solid rgba(239,68,68,.15)}
  html[data-theme="light"] #bg-canvas{opacity:.25}
  html[data-theme="light"] .mkt-up{color:#059669}
  html[data-theme="light"] .mkt-cor{color:#d97706}
  html[data-theme="light"] .mkt-bear{color:#dc2626}
  html[data-theme="light"] .scr-table a{color:#d97706}

  @media(max-width:768px){.container,.app-container{padding:12px 10px 40px}}
</style>
</head>
<body>
<canvas id="bg-canvas"></canvas>
<script>
(function(){
  var c=document.getElementById('bg-canvas'),w=c.width=window.innerWidth,h=c.height=window.innerHeight;
  var ctx=c.getContext('2d'),particles=[],N=60;
  for(var i=0;i<N;i++)particles.push({x:Math.random()*w,y:Math.random()*h,r:Math.random()*1.5+.3,vx:(Math.random()-.5)*.3,vy:(Math.random()-.5)*.3,o:Math.random()*.4+.1});
  function draw(){
    ctx.clearRect(0,0,w,h);
    for(var i=0;i<N;i++){
      var p=particles[i];p.x+=p.vx;p.y+=p.vy;
      if(p.x<0)p.x=w;if(p.x>w)p.x=0;if(p.y<0)p.y=h;if(p.y>h)p.y=0;
      ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle='rgba(245,158,11,'+p.o+')';ctx.fill();
    }
    for(var i=0;i<N;i++){
      for(var j=i+1;j<N;j++){
        var dx=particles[i].x-particles[j].x,dy=particles[i].y-particles[j].y,dist=Math.sqrt(dx*dx+dy*dy);
        if(dist<100){ctx.beginPath();ctx.moveTo(particles[i].x,particles[i].y);ctx.lineTo(particles[j].x,particles[j].y);ctx.strokeStyle='rgba(245,158,11,'+((100-dist)/100*.06)+')';ctx.stroke()}
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
  window.addEventListener('resize',function(){w=c.width=window.innerWidth;h=c.height=window.innerHeight});
})();
</script>
<div class="app-container">
'''

# Find the body content starts at
body_start = h.find('<body>') + len('<body>')
body_content = h[body_start:]

# Remove external CSS links and theme.js
body_content = body_content.replace('<link rel="stylesheet" href="../shared/css/theme.css"><link rel="stylesheet" href="../shared/css/base.css">\n  <link rel="stylesheet" href="../shared/css/xhs-cards.css"><link rel="stylesheet" href="../shared/css/components.css">\n  <script src="../shared/js/theme.js"></script>', '')

# Wrap table in glass shell
body_content = body_content.replace("document.getElementById('table-wrap').innerHTML='<div class=\"loading\">加载中...</div>';", 
    "document.getElementById('table-wrap').innerHTML='<div class=\"loading\">加载中...</div>';")
body_content = body_content.replace("h+='</tbody></table>';", "h+='</tbody></table></div>';")
body_content = body_content.replace("let h='<table class=\"scr-table\"><thead><tr>';", 
    "let h='<div class=\"table-shell\"><table class=\"scr-table\"><thead><tr>';")

# Update modal HTML to use glass classes
body_content = body_content.replace(
    '<div style="background:var(--card-bg);max-width:800px;margin:40px auto;border-radius:16px;padding:32px;position:relative;">',
    '<div class="modal-card" style="max-width:800px;margin:40px auto;padding:32px;position:relative;">')
body_content = body_content.replace(
    '<button onclick="document.getElementById(\'rec-modal\').style.display=\'none\'" style="position:absolute;top:12px;right:16px;background:none;border:none;font-size:1.2rem;cursor:pointer;color:var(--text-secondary);">✕</button>',
    '<button class="modal-close-btn" onclick="document.getElementById(\'rec-modal\').style.display=\'none\'" style="position:absolute;top:12px;right:16px;">✕</button>')
body_content = body_content.replace(
    '<div style="background:var(--card-bg);max-width:900px;margin:40px auto;border-radius:16px;padding:32px;position:relative;">',
    '<div class="modal-card" style="max-width:900px;margin:40px auto;padding:32px;position:relative;">')
body_content = body_content.replace(
    '<button onclick="document.getElementById(\'oneil-modal\').style.display=\'none\'" style="position:absolute;top:12px;right:16px;background:none;border:none;font-size:1.2rem;cursor:pointer;color:var(--text-secondary);">✕</button>',
    '<button class="modal-close-btn" onclick="document.getElementById(\'oneil-modal\').style.display=\'none\'" style="position:absolute;top:12px;right:16px;">✕</button>')

# Remove "📝" and "🧭" from buttons
body_content = body_content.replace('">📝 精选理由</a>','"> 精选理由</a>')
body_content = body_content.replace('">🧭 欧奈尔说</a>','"> 欧奈尔说</a>')

# Update nav init
body_content = body_content.replace(
    "Nav.init({brandIcon:'🦊',brandText:'知行',currentPage:'screening'});",
    "Nav.init({brandIcon:'⬤',brandText:'每日精选',currentPage:'screening'});")

# Update theme toggle ref
body_content = body_content.replace(
    '../shared/js/nav.js',
    '../shared/js/nav.js')

# Assemble
complete = new_head + body_content

f = open(r'D:\hanako\investment-system\web4\discipline\screening.html', 'w', encoding='utf-8')
f.write(complete)
f.close()

print(f'Size: {len(complete)} bytes')
print('Done')
