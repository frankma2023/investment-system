import os
t=i=0
for r,d,f in os.walk(r'D:\hanako\investment-system\web'):
 for fn in f:
  if not fn.endswith('.html') or 'shared' in r or '.bak' in fn or 'demo' in r or 'node_modules' in r: continue
  p=os.path.join(r,fn);h=open(p,encoding='utf-8').read()
  if 'hanako-glass.css' not in h: continue
  t+=1;body=h[h.find('<body>'):]
  if ('echarts' in h and 'echarts.min.js' not in h) or \
     ('KlineChart' in h and 'kline-chart.js' not in h) or \
     'theme.js' in h or 'theme.css' in h or \
     'function toggleTheme' not in h or \
     body.count('class="app-container"')>1:
   i+=1;print(f'ISSUE: {os.path.relpath(p,base)}')
print(f'Migrated:{t} Clean:{t-i}')
