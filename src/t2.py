from scanners.chanlun import analyze
r = analyze('600519', 'D', 200)
print('bi:', r.get('bi_count'), 'err:', r.get('error'))
if r.get('error'):
    import traceback
    traceback.print_exc()
