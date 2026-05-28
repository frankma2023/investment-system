import pdfplumber

pdf = pdfplumber.open(r'C:\Users\74295\.hanako\session-files\fd677aa40576f3ca9061a4ea\1de1a6c5f8b2ac3971a8017f3939942f1779696313191_mpkxbzha_1dd0cd0b.pdf')

all_text = []
for i, page in enumerate(pdf.pages):
    chars = page.chars
    # Get main font size (exclude watermark)
    by_size = {}
    for c in chars:
        sz = round(c.get('size', 0) or 0, 1)
        by_size[sz] = by_size.get(sz, 0) + 1
    main_size = max(by_size, key=by_size.get)
    
    # Extract lines with main font
    lines = {}
    for c in chars:
        if round(c.get('size', 0) or 0, 1) == main_size:
            y = round(c['top'], 0)
            if y not in lines:
                lines[y] = []
            lines[y].append(c)
    
    page_text = []
    for y in sorted(lines.keys()):
        line_chars = sorted(lines[y], key=lambda c: c['x0'])
        text = ''.join(c['text'] for c in line_chars)
        page_text.append(text)
    
    all_text.append('\n'.join(page_text))

pdf.close()

full = '\n\n===PAGE BREAK===\n\n'.join(all_text)
# Save and print
with open(r'C:\Users\74295\.hanako\session-files\fd677aa40576f3ca9061a4ea\extracted.txt', 'w', encoding='utf-8') as f:
    f.write(full)
print(full[:500])
print(f'... total {len(full)} chars saved')
