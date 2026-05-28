import re

f = open(r'D:\hanako\investment-system\web\stock-valuation\index.html', 'r', encoding='utf-8')
original = f.read()
f.close()

# Extract body content (everything after <body>)
body_start = original.find('<body>') + len('<body>')
body = original[body_start:]

# Remove external CSS/JS links, decorators
body = re.sub(r'<link rel="stylesheet" href="\.\./shared/css/[^"]+">\s*', '', body)
body = re.sub(r'<script src="\.\./shared/js/theme\.js"></script>\s*', '', body)
body = body.replace('<div class="journal-dots"></div><div class="washi-tape washi-1"></div><div class="washi-tape washi-2"></div>\n', '')
body = body.replace('<div class="app-container">\n', '')

# Remove old <style> block
body = re.sub(r'<style>.*?</style>\s*', '', body, flags=re.DOTALL)

# Fix nav init
body = body.replace('Nav.init({brandIcon:"💎",brandText:"个股扫描",currentPage:"stock-valuation"})',
                     'Nav.init({brandIcon:"⬤",brandText:"个股扫描",currentPage:"stock-valuation"})')

# === BUILD COMPLETE PAGE ===
page = '''<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>个股全维度分析</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{surface:'#0f0f12',card:'#1a1a1f',border:'rgba(255,255,255,.06)',muted:'#8b8b90',accent:'#f59e0b'},fontFamily:{sans:['Inter','system-ui','sans-serif'],display:['Instrument Serif','Georgia','serif'],mono:['JetBrains Mono','Fira Code','monospace']}}}}</script>
<link rel="stylesheet" href="../shared/css/hanako-glass.css">
<script src="../shared/js/echarts.min.js"></script>
<style>
  /* Page-specific: layout + tab grid overrides */
  .top-bar{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:10px}
  .top-bar label{font-size:11px;font-weight:500;color:var(--muted);display:block;margin-bottom:2px;letter-spacing:.02em;text-transform:uppercase}
  .top-bar input,.top-bar select{font-family:var(--font-body);padding:5px 10px;border:1px solid var(--border);border-radius:10px;font-size:12px;background:var(--card);color:var(--text-primary);outline:none;transition:all .2s;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
  .top-bar input:focus,.top-bar select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,158,11,.1)}
  .tabs{display:flex;gap:6px;margin-bottom:10px;overflow-x:auto;padding-bottom:4px;flex-wrap:wrap}
  .tab{padding:7px 16px;border:1px solid var(--border);border-radius:10px;background:rgba(26,26,31,.4);color:var(--muted);cursor:pointer;font-family:var(--font-body);font-size:12px;font-weight:500;transition:all .2s ease;white-space:nowrap;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
  .tab:hover{border-color:var(--border-hover);color:#d4d4d8}
  .tab.active{background:var(--accent-subtle);color:var(--accent);border-color:var(--accent-border)}
  .tab-content{display:none;animation:fadeIn .4s ease}
  .tab-content.active{display:block}
  #tab-val .chart-grid{grid-template-columns:1fr}
  #tab-profit .chart-grid{grid-template-columns:repeat(2,1fr)}
  #tab-health .chart-grid{grid-template-columns:repeat(2,1fr)}
  #tab-eval .result-grid{grid-template-columns:repeat(2,1fr)}
  .stock-header{display:flex;align-items:center;gap:10px;margin-bottom:8px}
  .stock-header .code{font-family:var(--font-mono);font-size:13px;color:var(--muted)}
  .stock-header .name{font-family:var(--font-display);font-size:1.1rem;font-weight:400;color:var(--text-primary)}
  @media(max-width:768px){#tab-profit .chart-grid,#tab-health .chart-grid,#tab-eval .result-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<canvas id="bg-canvas"></canvas>
<script>
(function(){var c=document.getElementById("bg-canvas"),w=c.width=window.innerWidth,h=c.height=window.innerHeight;var ctx=c.getContext("2d"),N=60;var p=[];for(var i=0;i<N;i++)p.push({x:Math.random()*w,y:Math.random()*h,r:Math.random()*1.5+.3,vx:(Math.random()-.5)*.3,vy:(Math.random()-.5)*.3,o:Math.random()*.4+.1});function draw(){ctx.clearRect(0,0,w,h);for(var i=0;i<N;i++){var P=p[i];P.x+=P.vx;P.y+=P.vy;if(P.x<0)P.x=w;if(P.x>w)P.x=0;if(P.y<0)P.y=h;if(P.y>h)P.y=0;ctx.beginPath();ctx.arc(P.x,P.y,P.r,0,Math.PI*2);ctx.fillStyle="rgba(245,158,11,"+P.o+")";ctx.fill()}for(var i=0;i<N;i++){for(var j=i+1;j<N;j++){var dx=p[i].x-p[j].x,dy=p[i].y-p[j].y,dist=Math.sqrt(dx*dx+dy*dy);if(dist<100){ctx.beginPath();ctx.moveTo(p[i].x,p[i].y);ctx.lineTo(p[j].x,p[j].y);ctx.strokeStyle="rgba(245,158,11,"+((100-dist)/100*.06)+")";ctx.stroke()}}}requestAnimationFrame(draw)}draw();window.addEventListener("resize",function(){w=c.width=window.innerWidth;h=c.height=window.innerHeight})})();
</script>
<div class="app-container">
''' + body

f = open(r'D:\hanako\investment-system\web4\stock-valuation\index.html', 'w', encoding='utf-8')
f.write(page)
f.close()

print(f'Size: {len(page)} bytes')
print('JS untouched - CSS only replacement')
