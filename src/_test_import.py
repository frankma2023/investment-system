from scanners.chanlun import analyze
r = analyze('000985', 'D', 200)
print('bi:', r.get('bi_count'), 'error:', r.get('error'))
