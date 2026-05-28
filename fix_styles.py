import os, re

BASE = r'D:\hanako\investment-system\web'
# Classes already in hanako-glass.css (don't need to be restored)
SHARED_CLASSES = [
    'top-nav', 'nav-brand', 'nav-links', 'nav-item', 'nav-dropdown', 'nav-dropdown-menu',
    'app-container', 'theme-toggle', 'chart-card', 'chart-title', 'glass-card',
    'xhs-card', 'xhs-card-header', 'xhs-card-label', 'stat-card',
    'data-table', 'mini-table', 'table-shell', 'scr-table',
    'glass-input', 'glass-select', 'btn-glass', 'btn-accent', 'pill-tab',
    'tag', 'tag-green', 'tag-red', 'tag-orange', 'tag-purple', 'tag-cyan',
    'badge', 'badge-up', 'badge-warn', 'badge-down',
    'modal-overlay', 'modal-card', 'modal-close',
    'loading', 'analysis-text', 'metric-row', 'metric-item',
    'chart-grid', 'result-grid', 'stat-cards',
    'stock-header', 'page-header', 'toolbar', 'fadeIn', 'reveal',
    'signal-legend', 'lg-item', 'lg-dot', 'lg-circle',
]

def fix_page(dirpath, filename):
    path = os.path.join(BASE, dirpath, filename)
    bak = path + '.bak'
    if not os.path.exists(bak): return False
    if 'hanako-glass.css' not in open(path, 'r', encoding='utf-8').read(): return False
    
    ho = open(bak, 'r', encoding='utf-8').read()
    hn = open(path, 'r', encoding='utf-8').read()
    
    mo = re.search(r'<style>(.*?)</style>', ho, re.DOTALL)
    if not mo: return False
    
    old_css = mo.group(1)
    
    # Filter out shared rules and classless rules (body, table, th, td)
    lines = old_css.strip().split('\n')
    keep_lines = []
    for line in lines:
        line_s = line.strip()
        # Skip empty lines
        if not line_s: continue
        # Skip rules for base elements that hanako-glass handles
        if re.match(r'^(body|html|\*|::)', line_s): continue
        # Skip rules for shared classes
        skip = False
        for sc in SHARED_CLASSES:
            if re.match(r'\.' + re.escape(sc) + r'[{,\s]', line_s):
                skip = True
                break
        if skip: continue
        # Convert old variable names to new ones
        line_s = line_s.replace('var(--card-bg)', 'var(--card)')
        line_s = line_s.replace('var(--divider)', 'var(--border)')
        line_s = line_s.replace('var(--color-accent-subtle)', 'var(--accent-subtle)')
        line_s = line_s.replace('var(--color-accent)', 'var(--accent)')
        line_s = line_s.replace('var(--text-tertiary)', 'var(--muted)')
        line_s = line_s.replace('var(--color-up)', 'var(--rise)')
        line_s = line_s.replace('var(--color-down)', 'var(--fall)')
        line_s = line_s.replace('#FE2C55', 'var(--fall)')
        keep_lines.append(line)
    
    if not keep_lines:
        return True  # nothing to add
    
    restored_css = '\n'.join(keep_lines)
    
    # Insert restored CSS after the last existing style rule
    # Find the last '}' before </style>
    style_end = hn.find('</style>')
    insert_pos = hn.rfind('}', 0, style_end)
    if insert_pos < 0: return False
    
    new_h = hn[:insert_pos+1] + '\n' + restored_css + hn[insert_pos+1:]
    
    open(path, 'w', encoding='utf-8').write(new_h)
    return True

# Fix all migrated pages
fixed = 0
for root, dirs, files in os.walk(BASE):
    for f in files:
        if f.endswith('.html') and 'shared' not in root and 'market-scan-demo' not in root and 'kline-demo' not in root and 'node_modules' not in root:
            rel = os.path.relpath(os.path.join(root, f), BASE)
            if fix_page(os.path.dirname(rel), f):
                fixed += 1
                print(f'  ✅ {rel}')

print(f'\nFixed {fixed} pages')
