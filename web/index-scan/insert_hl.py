h = open(r'D:\hanako\investment-system\web\index-scan\index.html', 'r', encoding='utf-8').read()

style_end = h.find('</style>')
last_brace = h.rfind('}', 0, style_end)
if last_brace < 0:
    last_brace = h.find('<style>') + 7

new_rules = """.scan-stat.hl-rs{background:rgba(245,158,11,.06);border-color:rgba(245,158,11,.25)}.scan-stat.hl-rs .val{color:var(--accent)}
.scan-stat.hl-ad{background:rgba(59,130,246,.06);border-color:rgba(59,130,246,.25)}.scan-stat.hl-ad .val{color:#3b82f6}
.scan-stat.hl-warn{background:rgba(239,68,68,.06);border-color:rgba(239,68,68,.25)}.scan-stat.hl-warn .val{color:var(--fall)}
.scan-stat.hl-ok{background:rgba(16,185,129,.06);border-color:rgba(16,185,129,.25)}.scan-stat.hl-ok .val{color:var(--rise)}
.scan-stat.hl-t1{background:rgba(168,85,247,.06);border-color:rgba(168,85,247,.25)}.scan-stat.hl-t1 .val{color:#a78bfa}
"""

h = h[:last_brace+1] + new_rules + h[last_brace+1:]

# Fix tier L1 to use hl-t1
old = 'class="scan-stat hl-warn"><div class="val">'+'tierCounts.L1'
new = 'class="scan-stat hl-t1"><div class="val">'+'tierCounts.L1'
if old in h:
    h = h.replace(old, new)
    print('Fixed tier L1 to hl-t1')

open(r'D:\hanako\investment-system\web\index-scan\index.html', 'w', encoding='utf-8').write(h)

# Verify
style = h[h.find('<style>'):h.find('</style>')]
print('hl-warn in style:', 'hl-warn' in style)
print('hl-t1 in style:', 'hl-t1' in style)
print('hl-warn in JS:', 'hl-warn' in h[h.find('</style>'):])
