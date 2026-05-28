import re

f = open(r'D:\hanako\investment-system\web\pattern-scan\index.html', 'r', encoding='utf-8')
h = f.read()
f.close()

css = '''<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{surface:'#0f0f12',card:'#1a1a1f',border:'rgba(255,255,255,.06)',muted:'#8b8b90',accent:'#f59e0b',sp:'rgba(255,255,255,.04)'},fontFamily:{sans:['Inter','system-ui','sans-serif'],display:['"Instrument Serif"','Georgia','serif'],mono:['"JetBrains Mono"','"Fira Code"','monospace']}}}}</script>
<style>
  *,::before,::after{box-sizing:border-box;margin:0;padding:0}
  body{background:#0f0f12;color:#e4e4e7;font-family:'Inter',system-ui,sans-serif;font-size:13px;line-height:1.5;min-height:100vh;overflow-x:hidden}
  :root{--bg:#0f0f12;--card:#1a1a1f;--border:rgba(255,255,255,.06);--muted:#8b8b90;--accent:#f59e0b;--rise:#10b981;--fall:#ef4444;--font-display:'Instrument Serif',Georgia,serif;--color-up:#10b981;--color-down:#ef4444;--color-accent:#f59e0b;--color-accent-subtle:rgba(245,158,11,.08);--text-primary:#e4e4e7;--text-secondary:#a1a1aa;--text-tertiary:var(--muted);--divider:rgba(255,255,255,.06);--card-bg:rgba(26,26,31,.6);--bg-surface:rgba(255,255,255,.02);--color-up:#10b981;--color-down:#ef4444}

  #bg-canvas{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.4}
  .app-container{max-width:1340px;margin:0 auto;padding:20px 24px 48px;position:relative;z-index:1}

  /* Top Bar */
  .top-bar{display:flex;gap:12px;align-items:flex-end;padding:16px 20px;background:rgba(26,26,31,.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,.2),0 4px 16px rgba(0,0,0,.1);flex-wrap:wrap}
  .top-bar .fld{flex:1;min-width:90px}
  .top-bar label{display:block;font-size:10px;font-weight:500;color:var(--muted);margin-bottom:4px;letter-spacing:.02em;text-transform:uppercase}
  .top-bar input,.top-bar select{width:100%;padding:7px 12px;border:1px solid var(--border);border-radius:10px;font-size:12px;background:rgba(26,26,31,.4);color:#e4e4e7;font-family:'Inter',system-ui,sans-serif;outline:none;transition:all .2s}
  .top-bar input:focus,.top-bar select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,158,11,.1)}
  .btn-scan{padding:8px 24px;background:rgba(245,158,11,.12);color:var(--accent);border:1px solid rgba(245,158,11,.3);border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;font-family:'Inter',system-ui,sans-serif;transition:all .2s}
  .btn-scan:hover{background:rgba(245,158,11,.18)}.btn-scan:disabled{opacity:.4;cursor:not-allowed}

  /* Mode buttons */
  .mode-btn{padding:4px 10px;border:1px solid var(--border);border-radius:8px;background:rgba(26,26,31,.4);color:var(--muted);font-size:11px;cursor:pointer;white-space:nowrap;flex-shrink:0;font-family:'Inter',system-ui,sans-serif;transition:all .2s}
  .mode-btn.active{background:rgba(245,158,11,.12);color:var(--accent);border-color:rgba(245,158,11,.3)}

  /* Chart controls */
  .chart-controls{display:flex;gap:16px;align-items:center;padding:6px 0;margin-bottom:6px}
  .chart-controls .ctrl-group{display:flex;align-items:center;gap:4px}
  .chart-controls .ctrl-label{font-size:10px;font-weight:500;color:var(--muted);margin-right:4px;text-transform:uppercase;letter-spacing:.04em}
  .chart-controls .ctrl-btn{padding:5px 14px;border:1px solid var(--border);border-radius:10px;background:rgba(26,26,31,.4);color:var(--muted);font-size:11px;cursor:pointer;transition:all .2s;font-family:'Inter',system-ui,sans-serif;backdrop-filter:blur(10px)}
  .chart-controls .ctrl-btn:hover{border-color:rgba(255,255,255,.15);color:#d4d4d8}
  .chart-controls .ctrl-btn.active{background:rgba(245,158,11,.12);color:var(--accent);border-color:rgba(245,158,11,.3)}

  /* Chart */
  .chart-wrap{width:100%;height:560px;margin-bottom:0}

  /* Signal legend */
  .signal-legend{display:flex;gap:12px;flex-wrap:wrap;padding:6px 0 10px 0;font-size:11px;align-items:center;color:var(--muted)}
  .signal-legend .sl-item{display:inline-flex;align-items:center;gap:4px;font-size:11px;color:#a1a1aa}

  /* Bottom layout */
  .bottom-layout{display:flex;gap:14px;align-items:flex-start;margin-bottom:10px}
  .bottom-left{flex:1;min-width:0}
  .bottom-right{width:340px;flex-shrink:0}
  @media(max-width:900px){.bottom-layout{flex-direction:column}.bottom-right{width:100%}}

  /* Cards */
  .xhs-card{background:rgba(26,26,31,.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;padding:14px;margin-bottom:10px;box-shadow:0 1px 2px rgba(0,0,0,.2),0 4px 16px rgba(0,0,0,.1)}
  .xhs-card:hover{border-color:rgba(255,255,255,.1)}
  .xhs-card-header{display:flex;align-items:center;margin-bottom:8px;gap:8px}
  .xhs-card-label{font-family:var(--font-display);font-size:15px;font-weight:400;color:#d4d4d8;letter-spacing:.01em}

  /* Rec */
  .rec-section{margin-bottom:8px}
  .rec-section:last-child{margin-bottom:0}
  .rec-label{font-size:11px;font-weight:500;color:var(--accent);margin-bottom:3px;display:flex;align-items:center;gap:4px}
  .rec-text{font-size:12px;color:#a1a1aa;line-height:1.6}

  /* Timeline */
  .timeline-wrap{max-height:520px;overflow-y:auto}
  .tl-item{display:flex;align-items:flex-start;gap:10px;padding:7px 8px;cursor:pointer;transition:background .15s;border-radius:10px;border-bottom:1px solid rgba(255,255,255,.03)}
  .tl-item:last-child{border-bottom:none}
  .tl-item:hover{background:rgba(245,158,11,.06)}
  .tl-dot{width:10px;height:10px;border-radius:50%;margin-top:4px;flex-shrink:0}
  .tl-info{flex:1;min-width:0}
  .tl-date{font-size:10px;color:var(--muted)}
  .tl-name{font-size:12px;font-weight:500;color:#d4d4d8}
  .tl-desc{font-size:10px;color:#a1a1aa;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .tl-empty{font-size:12px;color:var(--muted);text-align:center;padding:32px 0}

  /* Legend row */
  .legend-row{display:flex;gap:12px;flex-wrap:wrap;padding:6px 0;font-size:11px;align-items:center;color:var(--muted)}
  .legend-row .lg-item{display:flex;align-items:center;gap:5px;cursor:default}
  .legend-row .lg-dot{width:9px;height:9px;border-radius:2px}

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

  /* Light mode */
  html[data-theme="light"] body{background:#f8f9fa;color:#1a1a2e}
  html[data-theme="light"] :root{--bg:#f8f9fa;--card:#ffffff;--border:rgba(0,0,0,.08);--muted:#6b7280;--accent:#d97706;--rise:#059669;--fall:#dc2626;--text-primary:#1a1a2e;--text-secondary:#4b5563;--text-tertiary:#6b7280;--card-bg:rgba(255,255,255,.8);--bg-surface:rgba(0,0,0,.02);--color-up:#10b981;--color-down:#ef4444;--color-accent:#d97706;--color-accent-subtle:rgba(217,119,6,.08);--divider:rgba(0,0,0,.08)}
  html[data-theme="light"] .top-bar{background:rgba(255,255,255,.75);border:1px solid rgba(0,0,0,.06)}
  html[data-theme="light"] .top-bar label{color:#6b7280}
  html[data-theme="light"] .top-bar input,html[data-theme="light"] .top-bar select{background:rgba(255,255,255,.7);border:1px solid rgba(0,0,0,.08);color:#1a1a2e}
  html[data-theme="light"] .btn-scan{background:rgba(217,119,6,.08);color:#d97706;border-color:rgba(217,119,6,.2)}
  html[data-theme="light"] .mode-btn{background:rgba(255,255,255,.6);border:1px solid rgba(0,0,0,.08);color:#6b7280}
  html[data-theme="light"] .mode-btn.active{background:rgba(217,119,6,.08);color:#d97706;border-color:rgba(217,119,6,.2)}
  html[data-theme="light"] .chart-controls .ctrl-btn{background:rgba(255,255,255,.6);border:1px solid rgba(0,0,0,.08);color:#6b7280}
  html[data-theme="light"] .chart-controls .ctrl-btn:hover{border-color:rgba(0,0,0,.15);color:#374151}
  html[data-theme="light"] .chart-controls .ctrl-btn.active{background:rgba(217,119,6,.08);color:#d97706;border-color:rgba(217,119,6,.2)}
  html[data-theme="light"] .xhs-card{background:rgba(255,255,255,.75);border:1px solid rgba(0,0,0,.06);box-shadow:0 1px 3px rgba(0,0,0,.04),0 4px 16px rgba(0,0,0,.04)}
  html[data-theme="light"] .xhs-card-label{color:#374151}
  html[data-theme="light"] .rec-text{color:#4b5563}
  html[data-theme="light"] .tl-item{border-bottom:1px solid rgba(0,0,0,.04)}
  html[data-theme="light"] .tl-item:hover{background:rgba(217,119,6,.04)}
  html[data-theme="light"] .tl-name{color:#1a1a2e}
  html[data-theme="light"] .tl-desc{color:#4b5563}
  html[data-theme="light"] .signal-legend{color:#6b7280}
  html[data-theme="light"] .nav-brand{color:#374151}
  html[data-theme="light"] .nav-item{color:#6b7280}
  html[data-theme="light"] .nav-item:hover{color:#1a1a2e;background:rgba(0,0,0,.03)}
  html[data-theme="light"] .nav-item.active{color:#d97706;background:rgba(217,119,6,.08)}
  html[data-theme="light"] .nav-dropdown-menu{background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.08);box-shadow:0 12px 40px rgba(0,0,0,.1)}
  html[data-theme="light"] .nav-dropdown-menu a{color:#6b7280}
  html[data-theme="light"] .nav-dropdown-menu a:hover{background:rgba(217,119,6,.06);color:#1a1a2e}
  html[data-theme="light"] .theme-toggle{color:#6b7280;border:1px solid rgba(0,0,0,.1)}
  html[data-theme="light"] .theme-toggle:hover{border-color:rgba(0,0,0,.2);color:#1a1a2e}
  html[data-theme="light"] .chart-controls .ctrl-label{color:#6b7280}
  html[data-theme="light"] #bg-canvas{opacity:.25}

  @media(max-width:768px){.app-container{padding:12px 10px 40px}}
</style>'''

# Build new head
head_end = h.find('</head>')
body_start = h.find('<body>') + len('<body>')

new_head = '''<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>形态识别</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="../shared/js/echarts.min.js"></script>
''' + css + '''
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
    for(var i=0;i<N;i++){var p=particles[i];p.x+=p.vx;p.y+=p.vy;if(p.x<0)p.x=w;if(p.x>w)p.x=0;if(p.y<0)p.y=h;if(p.y>h)p.y=0;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle='rgba(245,158,11,'+p.o+')';ctx.fill()}
    for(var i=0;i<N;i++){for(var j=i+1;j<N;j++){var dx=particles[i].x-particles[j].x,dy=particles[i].y-particles[j].y,dist=Math.sqrt(dx*dx+dy*dy);if(dist<100){ctx.beginPath();ctx.moveTo(particles[i].x,particles[i].y);ctx.lineTo(particles[j].x,particles[j].y);ctx.strokeStyle='rgba(245,158,11,'+((100-dist)/100*.06)+')';ctx.stroke()}}}
    requestAnimationFrame(draw);
  }
  draw();
  window.addEventListener('resize',function(){w=c.width=window.innerWidth;h=c.height=window.innerHeight});
})();
</script>
<div class="app-container">
'''

# Get body content (remove old head)
body_content = h[body_start:]
# Remove old external CSS and style block
body_content = re.sub(r'<link rel="stylesheet" href="\.\./shared/css/[^"]+">\s*', '', body_content)
body_content = re.sub(r'<script src="\.\./shared/js/theme\.js"></script>\s*', '', body_content)
body_content = re.sub(r'<style>.*?</style>\s*', '', body_content, flags=re.DOTALL)

# Fix nav
body_content = body_content.replace('<script src="../shared/js/nav.js"></script>', '<script src="../shared/js/nav.js"></script>')

# Add toggleTheme for glass design system nav button
body_content = body_content.replace('</script>\n\n</body>', '''  // Global theme toggle for nav button
  if(typeof toggleTheme!=='function'){window.toggleTheme=function(){var h=document.documentElement,n=h.dataset.theme==='dark'?'light':'dark';h.dataset.theme=n;localStorage.setItem('theme',n)}}
</script>

</body>''')

complete = new_head + body_content

f = open(r'D:\hanako\investment-system\web4\pattern-scan\index.html', 'w', encoding='utf-8')
f.write(complete)
f.close()

print(f'Size: {len(complete)} bytes')
print('Done')
