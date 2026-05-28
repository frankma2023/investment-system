import re

f = open(r'D:\hanako\investment-system\web\stock-valuation\index.html', 'r', encoding='utf-8')
h = f.read()
f.close()

# New head content (raw triple-quoted string)
new_head = """<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="UTF-8">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>个股全维度分析</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{surface:'#0f0f12',card:'#1a1a1f',border:'rgba(255,255,255,.06)',muted:'#8b8b90',accent:'#f59e0b'},fontFamily:{sans:['Inter','system-ui','sans-serif'],display:['Instrument Serif','Georgia','serif'],mono:['JetBrains Mono','Fira Code','monospace']}}}}</script>
<script src="../shared/js/echarts.min.js"></script>
<style>
  *,::before,::after{box-sizing:border-box;margin:0;padding:0}
  body{background:#0f0f12;color:#e4e4e7;font-family:'Inter',system-ui,sans-serif;font-size:13px;line-height:1.5;min-height:100vh;overflow-x:hidden}
  :root{--bg:#0f0f12;--card:#1a1a1f;--border:rgba(255,255,255,.06);--muted:#8b8b90;--accent:#f59e0b;--rise:#10b981;--fall:#ef4444;--font-display:'Instrument Serif',Georgia,serif;--color-up:#10b981;--color-down:#ef4444;--color-accent:#f59e0b;--color-accent-subtle:rgba(245,158,11,.08);--text-primary:#e4e4e7;--text-secondary:#a1a1aa;--text-tertiary:var(--muted);--divider:rgba(255,255,255,.06);--card-bg:rgba(26,26,31,.6);--bg-surface:rgba(255,255,255,.02)}
  #bg-canvas{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.4}
  .app-container{position:relative;z-index:1;max-width:1340px;margin:0 auto;padding:20px 24px 48px}
  .container{max-width:1340px;margin:0 auto;padding:20px 24px 48px;position:relative;z-index:1}
  .top-bar{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:14px}
  .top-bar label{font-size:11px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px;letter-spacing:.02em;text-transform:uppercase}
  .top-bar input,.top-bar select{font-family:'Inter',system-ui,sans-serif;padding:7px 12px;border:1px solid var(--border);border-radius:10px;font-size:13px;background:rgba(26,26,31,.6);color:#e4e4e7;outline:none;transition:all .2s;backdrop-filter:blur(10px)}
  .top-bar input:focus,.top-bar select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,158,11,.1)}
  .tabs{display:flex;gap:6px;margin-bottom:14px;overflow-x:auto;padding-bottom:4px;flex-wrap:wrap}
  .tab{padding:7px 16px;border:1px solid var(--border);border-radius:10px;background:rgba(26,26,31,.4);color:var(--muted);cursor:pointer;font-family:'Inter',system-ui,sans-serif;font-size:12px;font-weight:500;transition:all .2s ease;white-space:nowrap;backdrop-filter:blur(10px)}
  .tab:hover{border-color:rgba(255,255,255,.15);color:#d4d4d8}
  .tab.active{background:rgba(245,158,11,.12);color:var(--accent);border-color:rgba(245,158,11,.3)}
  .tab-content{display:none;animation:fadeIn .4s ease}
  .tab-content.active{display:block}
  @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
  .stat-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:14px}
  .stat-card{background:rgba(26,26,31,.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:12px;padding:12px 10px;text-align:center;transition:all .25s ease;box-shadow:0 1px 2px rgba(0,0,0,.2),0 4px 16px rgba(0,0,0,.1)}
  .stat-card:hover{border-color:rgba(255,255,255,.1);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.2)}
  .stat-card .val{font-family:var(--font-display);font-size:1.3rem;font-weight:400;color:#f5f5f4}
  .stat-card .lbl{font-size:10px;color:var(--muted);margin-top:4px;font-weight:500;letter-spacing:.03em;text-transform:uppercase}
  .chart-card{background:rgba(26,26,31,.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;padding:14px;margin-bottom:12px;transition:all .25s ease;box-shadow:0 1px 2px rgba(0,0,0,.2),0 4px 16px rgba(0,0,0,.1)}
  .chart-card:hover{border-color:rgba(255,255,255,.1)}
  .chart-title{font-family:var(--font-display);font-size:15px;font-weight:400;color:#d4d4d8;letter-spacing:.01em;margin-bottom:6px}
  .chart-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
  .result-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
  .result-grid .full{grid-column:1/-1}
  .analysis-text{font-size:12px;color:#a1a1aa;line-height:1.6;margin-top:6px;padding:10px 12px;background:rgba(255,255,255,.02);border-radius:8px;border:1px solid rgba(255,255,255,.03)}
  .xhs-card{background:rgba(26,26,31,.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;padding:14px;margin-bottom:10px;transition:all .25s ease;box-shadow:0 1px 2px rgba(0,0,0,.2),0 4px 16px rgba(0,0,0,.1)}
  .xhs-card:hover{border-color:rgba(255,255,255,.1)}
  .xhs-card-header{display:flex;align-items:center;margin-bottom:10px;gap:8px}
  .xhs-card-label{font-family:var(--font-display);font-size:15px;font-weight:400;color:#d4d4d8;letter-spacing:.01em}
  .mini-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
  .mini-table th{text-align:left;padding:8px 8px;font-size:10px;font-weight:500;color:var(--muted);border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.04em}
  .mini-table td{padding:7px 8px;border-bottom:1px solid rgba(255,255,255,.03);font-weight:300}
  .mini-table .mono{font-family:'JetBrains Mono',monospace;font-size:11px}
  .mini-table tr:hover td{background:rgba(255,255,255,.02)}
  .metric-row{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
  .metric-item{flex:1;min-width:65px;text-align:center;padding:10px 8px;background:rgba(255,255,255,.02);border-radius:10px;border:1px solid rgba(255,255,255,.03)}
  .metric-item .val{font-family:var(--font-display);font-size:1.1rem;font-weight:400;color:#f5f5f4}
  .metric-item .lbl{font-size:10px;color:var(--muted);margin-top:3px;text-transform:uppercase;letter-spacing:.03em}
  .metric-item .val.up{color:var(--rise)}.metric-item .val.down{color:var(--fall)}
  .tag{display:inline-block;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:500}
  .tag-green{background:rgba(16,185,129,.12);color:var(--rise);border:1px solid rgba(16,185,129,.2)}
  .tag-red{background:rgba(239,68,68,.12);color:var(--fall);border:1px solid rgba(239,68,68,.2)}
  .tag-orange{background:rgba(245,158,11,.12);color:var(--accent);border:1px solid rgba(245,158,11,.2)}
  .stock-header{display:flex;align-items:center;gap:10px;margin-bottom:8px}
  .stock-header .code{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--muted)}
  .stock-header .name{font-family:var(--font-display);font-size:1.1rem;font-weight:400;color:#f5f5f4}
  .nav-dropdown{position:relative;display:inline-flex}
  .nav-dropdown-menu{display:none;position:absolute;top:100%;left:0;background:rgba(20,20,25,.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--border);border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.4);min-width:150px;padding:6px 0;z-index:200;white-space:nowrap}
  .nav-dropdown:hover .nav-dropdown-menu{display:block}
  .nav-dropdown-menu a{display:block;padding:7px 16px;font-size:12px;color:var(--muted);text-decoration:none;transition:all .15s;font-family:'Inter',system-ui,sans-serif}
  .nav-dropdown-menu a:hover{background:rgba(245,158,11,.08);color:#e4e4e7}
  .xhs-loading,.loading-row{text-align:center;padding:24px;color:var(--muted);font-weight:300}
  .btn-analysis{padding:4px 12px;border:1px solid var(--border);border-radius:8px;background:transparent;cursor:pointer;font-size:11px;font-family:'Inter',system-ui,sans-serif;color:var(--muted);transition:all .2s}
  .btn-analysis:hover{border-color:rgba(255,255,255,.15);color:#d4d4d8;background:rgba(255,255,255,.04)}
  @media(max-width:768px){.chart-grid,.result-grid{grid-template-columns:1fr}.stat-cards{grid-template-columns:repeat(2,1fr)}.app-container,.container{padding:12px 10px 40px}}
  .chart-card,.stat-card,.xhs-card{transition:opacity .5s ease,transform .5s ease,border-color .25s ease,box-shadow .25s ease}
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
<div class="container">
"""

# Find body start in original
body_start = h.find('<body>') + len('<body>')
body_content = h[body_start:]

# Remove decorator divs
body_content = body_content.replace('<div class="journal-dots"></div><div class="washi-tape washi-1"></div><div class="washi-tape washi-2"></div>\n', '')
body_content = body_content.replace('<div class="app-container">\n', '')

# Fix theme toggle to always be dark
body_content = body_content.replace(
    "function toggleTheme(){var h=document.documentElement,n=h.dataset.theme==='dark'?'light':'dark';h.dataset.theme=n;localStorage.setItem('stkv-theme',n);setTimeout(loadAll,200)}",
    "function toggleTheme(){var h=document.documentElement;h.dataset.theme='dark';localStorage.setItem('stkv-theme','dark');setTimeout(loadAll,200)}"
)

# Fix theme init
body_content = body_content.replace(
    "(function(){var s=localStorage.getItem('stkv-theme')||'light';document.documentElement.dataset.theme=s})();",
    "(function(){document.documentElement.dataset.theme='dark'})();"
)

# Fix isDark check
body_content = body_content.replace(
    "var isDark=document.documentElement.dataset.theme==='dark'",
    "var isDark=true"
)

# Assemble
complete = new_head + body_content

f = open(r'D:\hanako\investment-system\web4\stock-valuation\index.html', 'w', encoding='utf-8')
f.write(complete)
f.close()

print(f'Size: {len(complete)} bytes')
print('Done')
