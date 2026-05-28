import os, re

BASE = r'D:\hanako\investment-system\web'

# ── Standard migration for backtest-style pages ──
def migrate_backtest(dir_name, title, brand_text, current_page):
    path = os.path.join(BASE, dir_name, 'index.html')
    if not os.path.exists(path):
        print(f'  SKIP {dir_name}: no index.html')
        return False
    
    h = open(path, 'r', encoding='utf-8').read()
    if 'hanako-glass.css' in h:
        print(f'  SKIP {dir_name}: already migrated')
        return True
    
    # Backup original
    backup_path = path + '.bak'
    if not os.path.exists(backup_path):
        open(backup_path, 'w', encoding='utf-8').write(h)
    
    body_start = h.find('<body>') + len('<body>')
    body = h[body_start:]
    
    # Remove old CSS/JS
    body = re.sub(r'<link rel="stylesheet" href="\.\./shared/css/[^"]+">\s*', '', body)
    body = re.sub(r'<script src="\.\./shared/js/theme\.js"></script>\s*', '', body)
    body = body.replace('<div class="journal-dots"></div><div class="washi-tape washi-1"></div><div class="washi-tape washi-2"></div>\n', '')
    
    # Remove old <style> block
    body = re.sub(r'<style>.*?</style>\s*', '', body, flags=re.DOTALL)
    
    # Remove original app-container wrapper (prevent nesting)
    body = re.sub(r'<div class="app-container">\s*', '', body, count=1)
    
    # Fix nav init
    body = body.replace(
        f"Nav.init({{brandIcon:\"📊\",brandText:\"{brand_text}\",currentPage:\"{current_page}\"}})",
        f"Nav.init({{brandIcon:\"⬤\",brandText:\"{brand_text}\",currentPage:\"{current_page}\"}})"
    )
    
    # Build new page
    page = f'''<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={{theme:{{extend:{{colors:{{surface:'#0f0f12',card:'#1a1a1f',border:'rgba(255,255,255,.06)',muted:'#8b8b90',accent:'#f59e0b'}},fontFamily:{{sans:['Inter','system-ui','sans-serif'],display:['Instrument Serif','Georgia','serif'],mono:['JetBrains Mono','Fira Code','monospace']}}}}}}}}</script>
<link rel="stylesheet" href="../shared/css/hanako-glass.css">
<style>
  .chart-wrap{{height:520px;margin-bottom:4px}}
  .chart-legend{{display:flex;gap:12px;flex-wrap:wrap;padding:6px 0;font-size:11px;color:var(--muted)}}
  .top-bar{{display:flex;gap:12px;align-items:flex-end;padding:14px 18px;background:var(--card);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;margin-bottom:10px;box-shadow:var(--shadow-card);flex-wrap:wrap}}
  .top-bar .fld{{flex:1;min-width:80px}}
  .top-bar label{{display:block;font-size:10px;font-weight:500;color:var(--muted);margin-bottom:3px;text-transform:uppercase;letter-spacing:.03em}}
  .top-bar input,.top-bar select{{width:100%;padding:6px 10px;border:1px solid var(--border);border-radius:10px;font-size:12px;background:rgba(26,26,31,.4);color:var(--text-primary);font-family:var(--font-body);outline:none;transition:all .2s}}
  .top-bar input:focus,.top-bar select:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,158,11,.1)}}
  .bottom-layout{{display:flex;gap:12px;align-items:flex-start;margin-bottom:10px}}
  .bottom-left{{flex:1;min-width:0}}
  .bottom-right{{width:380px;flex-shrink:0}}
  @media(max-width:900px){{.bottom-layout{{flex-direction:column}}.bottom-right{{width:100%}}}}
  .param-card{{background:var(--card);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:14px;padding:12px;margin-bottom:8px}}
  .param-card-hd{{font-family:var(--font-display);font-size:14px;font-weight:400;color:#d4d4d8;cursor:pointer;display:flex;align-items:center;gap:8px}}
  .param-card-bd{{padding:8px 0 0}}.param-card-bd.collapsed{{display:none}}
  .dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
  .sr{{display:flex;align-items:center;gap:8px;padding:4px 0}}
  .sl{{font-size:11px;color:var(--muted);min-width:60px}}
  .sv{{font-size:11px;font-weight:500;color:var(--text-primary);min-width:36px;text-align:right}}
  input[type=range]{{flex:1;height:4px;-webkit-appearance:none;appearance:none;background:var(--border);border-radius:2px;outline:none}}
  input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:var(--accent)}}
  .btn-run{{padding:8px 24px;background:var(--accent-subtle);color:var(--accent);border:1px solid var(--accent-border);border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;font-family:var(--font-body);transition:all .2s;margin-top:8px}}
  .btn-run:hover{{background:rgba(245,158,11,.18)}}.btn-run:disabled{{opacity:.4;cursor:not-allowed}}
  .btn-save{{padding:8px 16px;background:transparent;color:var(--muted);border:1px solid var(--border);border-radius:10px;font-size:12px;cursor:pointer;font-family:var(--font-body);transition:all .2s;margin-top:8px;margin-left:6px}}
  .btn-save:hover{{color:#d4d4d8;border-color:var(--border-hover)}}.btn-save.saved{{color:var(--rise)}}
  .table-wrapper{{overflow-x:auto;font-size:11px}}
  .table-wrapper table{{width:100%;border-collapse:collapse}}
  .table-wrapper th{{text-align:left;padding:6px 8px;font-size:10px;font-weight:500;color:var(--muted);border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.03em}}
  .table-wrapper td{{padding:5px 8px;border-bottom:1px solid rgba(255,255,255,.03);font-weight:300}}
  .s-conf{{color:var(--fall);font-weight:500}}.s-warn{{color:var(--accent);font-weight:500}}.s-clr{{color:var(--rise);font-weight:500}}
  html[data-theme="light"] .top-bar{{background:rgba(255,255,255,.75);border-color:var(--divider)}}
  html[data-theme="light"] .top-bar input,html[data-theme="light"] .top-bar select{{background:rgba(255,255,255,.7);border-color:var(--divider);color:var(--text-primary)}}
  html[data-theme="light"] .param-card{{background:rgba(255,255,255,.75);border-color:var(--divider)}}
  html[data-theme="light"] .param-card-hd{{color:#374151}}
  html[data-theme="light"] .table-wrapper td{{border-bottom-color:rgba(0,0,0,.03)}}
</style>
</head>
<body>
<canvas id="bg-canvas"></canvas>
<script>(function(){{var c=document.getElementById("bg-canvas"),w=c.width=window.innerWidth,h=c.height=window.innerHeight;var ctx=c.getContext("2d"),N=60;var p=[];for(var i=0;i<N;i++)p.push({{x:Math.random()*w,y:Math.random()*h,r:Math.random()*1.5+.3,vx:(Math.random()-.5)*.3,vy:(Math.random()-.5)*.3,o:Math.random()*.4+.1}});function draw(){{ctx.clearRect(0,0,w,h);for(var i=0;i<N;i++){{var P=p[i];P.x+=P.vx;P.y+=P.vy;if(P.x<0)P.x=w;if(P.x>w)P.x=0;if(P.y<0)P.y=h;if(P.y>h)P.y=0;ctx.beginPath();ctx.arc(P.x,P.y,P.r,0,Math.PI*2);ctx.fillStyle="rgba(245,158,11,"+P.o+")";ctx.fill()}}for(var i=0;i<N;i++){{for(var j=i+1;j<N;j++){{var dx=p[i].x-p[j].x,dy=p[i].y-p[j].y,dist=Math.sqrt(dx*dx+dy*dy);if(dist<100){{ctx.beginPath();ctx.moveTo(p[i].x,p[i].y);ctx.lineTo(p[j].x,p[j].y);ctx.strokeStyle="rgba(245,158,11,"+((100-dist)/100*.06)+")";ctx.stroke()}}}}}}requestAnimationFrame(draw)}}draw();window.addEventListener("resize",function(){{w=c.width=window.innerWidth;h=c.height=window.innerHeight}})}})();
</script>
<div class="app-container">
''' + body
    
    # Add toggleTheme if missing
    if 'function toggleTheme' not in page:
        toggle_js = '''
// Theme toggle
function toggleTheme(){var h=document.documentElement,n=h.dataset.theme==='dark'?'light':'dark';h.dataset.theme=n;localStorage.setItem('theme',n);if(typeof renderChart==='function')setTimeout(renderChart,200)}
(function(){var s=localStorage.getItem('theme')||'dark';document.documentElement.dataset.theme=s})();
'''
        page = page.replace('</script>\n</body>', toggle_js + '</script>\n</body>')
    
    open(path, 'w', encoding='utf-8').write(page)
    print(f'  ✅ {dir_name}: {len(page)} bytes')
    return True

# ── Migrate all backtest pages ──
pages = [
    ('follow-through-day', '追盘日回测', '追盘日', 'follow-through-day'),
    ('accumulation-day', '吸筹日回测', '吸筹日', 'accumulation-day'),
    ('index-rs-backtest', '指数RS回测', '指数RS', 'index-rs-backtest'),
    ('index-crowdedness', '指数拥挤度回测', '拥挤度', 'index-crowdedness'),
    ('stock-rs-backtest', '个股RS回测', '个股RS', 'stock-rs-backtest'),
    ('index-ad-backtest', '机构吸筹出货回测', 'AD回测', 'index-ad-backtest'),
    ('divergence-backtest', '指数背离回测', '背离', 'divergence-backtest'),
    ('cup-handle-backtest', '杯柄形态回测', '杯柄', 'cup-handle-backtest'),
    ('double-bottom', '双重底回测', '双重底', 'double-bottom'),
    ('flat-base', '扁平基部回测', '扁平基部', 'flat-base'),
    ('base-breakout', '基部突破回测', '基部突破', 'base-breakout'),
    ('pocket-pivot', '口袋支点回测', '口袋支点', 'pocket-pivot'),
    ('railroad-tracks', '铁轨线回测', '铁轨线', 'railroad-tracks'),
    ('climax-top', '高潮见顶回测', '高潮见顶', 'climax-top'),
    ('top-pattern', '头部形态回测', '头部形态', 'top-pattern'),
    ('volume-divergence', '量价背离回测', '量价背离', 'volume-divergence'),
    ('breakout-failure', '突破失败回测', '突破失败', 'breakout-failure'),
]

print(f'Migrating {len(pages)} backtest pages...')
for d, title, brand, cp in pages:
    migrate_backtest(d, title, brand, cp)

print('\nDone.')
