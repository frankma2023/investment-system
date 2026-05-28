import re

p = r'D:\hanako\investment-system\web\index-scan\index.html'
h = open(p, 'r', encoding='utf-8').read()

# 1. Replace old badge rules with unified system
old_badge_block = '''.badge-rs { background:var(--color-accent-bg); color:var(--accent); }
.badge-ad-a { background:rgba(16,185,129,.08); color:var(--rise); }
.badge-ad-e { background:var(--color-down-bg); color:var(--fall); }
.badge-crowd-high { background:rgba(16,185,129,.08); color:var(--rise); border:1px solid rgba(16,185,129,.2); }
.badge-crowd-low { background:var(--color-down-bg); color:var(--fall); border:1px solid var(--color-down-border); }
.badge-div-top { background:rgba(16,185,129,.08); color:var(--rise); }
.badge-div-bot { background:var(--color-down-bg); color:var(--fall); }
.badge-tier-L1 { background:rgba(16,185,129,.08); color:var(--rise); border:1px solid rgba(16,185,129,.2); }
.badge-tier-L2 { background:var(--color-neutral-bg); color:var(--muted); border:1px solid var(--color-neutral-border); }
.badge-tier-L3 { background:rgba(160,80,255,0.08); color:#8A40D0; border:1px solid rgba(160,80,255,0.15); }'''

new_badge_block = '''.badge-rs{background:rgba(245,158,11,.1);color:var(--accent);border:1px solid rgba(245,158,11,.2)}
.badge-ad-a{background:rgba(59,130,246,.1);color:#3b82f6;border:1px solid rgba(59,130,246,.2)}
.badge-ad-e{background:rgba(239,68,68,.1);color:var(--fall);border:1px solid rgba(239,68,68,.2)}
.badge-crowd-high{background:rgba(239,68,68,.1);color:var(--fall);border:1px solid rgba(239,68,68,.2)}
.badge-crowd-low{background:rgba(16,185,129,.1);color:var(--rise);border:1px solid rgba(16,185,129,.2)}
.badge-div-top{background:rgba(239,68,68,.1);color:var(--fall);border:1px solid rgba(239,68,68,.2)}
.badge-div-bot{background:rgba(16,185,129,.1);color:var(--rise);border:1px solid rgba(16,185,129,.2)}
.badge-tier-L1{background:rgba(168,85,247,.1);color:#a78bfa;border:1px solid rgba(168,85,247,.2)}
.badge-tier-L2{background:rgba(245,158,11,.1);color:var(--accent);border:1px solid rgba(245,158,11,.2)}
.badge-tier-L3{background:rgba(255,255,255,.04);color:var(--muted);border:1px solid var(--border)}'''

h = h.replace(old_badge_block, new_badge_block)

# 2. Replace old highlight rules with color-coded variants  
old_hl = '''.scan-stat.highlight { border-color:rgba(16,185,129,.2); background:rgba(16,185,129,.08); }
.scan-stat.highlight .val { color:var(--rise); }
.highlight { border-color:rgba(16,185,129,.2); background:rgba(16,185,129,.08); }
.highlight .val { color:var(--rise); }'''

new_hl = '''.scan-stat.highlight{border-color:rgba(16,185,129,.25);background:rgba(16,185,129,.06)}.scan-stat.highlight .val{color:var(--rise)}
.highlight{border-color:rgba(16,185,129,.25);background:rgba(16,185,129,.06)}.highlight .val{color:var(--rise)}
/* Color-coded stat card variants */
.scan-stat.hl-rs{background:rgba(245,158,11,.06);border-color:rgba(245,158,11,.25)}.scan-stat.hl-rs .val{color:var(--accent)}
.scan-stat.hl-ad{background:rgba(59,130,246,.06);border-color:rgba(59,130,246,.25)}.scan-stat.hl-ad .val{color:#3b82f6}
.scan-stat.hl-warn{background:rgba(239,68,68,.06);border-color:rgba(239,68,68,.25)}.scan-stat.hl-warn .val{color:var(--fall)}
.scan-stat.hl-ok{background:rgba(16,185,129,.06);border-color:rgba(16,185,129,.25)}.scan-stat.hl-ok .val{color:var(--rise)}
.scan-stat.hl-t1{background:rgba(168,85,247,.06);border-color:rgba(168,85,247,.25)}.scan-stat.hl-t1 .val{color:#a78bfa}'''

h = h.replace(old_hl, new_hl)

# 3. Update JS class names to use hl-warn for crowding/divergence alerts
h = h.replace("class='scan-stat highlight'", "class='scan-stat hl-warn'")
h = h.replace("class=\"scan-stat highlight\"", "class=\"scan-stat hl-warn\"")

open(p, 'w', encoding='utf-8').write(h)
print('Done')
