import sys
sys.path.insert(0, 'src')
from scanners.chanlun import get_echarts_option, analyze
try:
    r = get_echarts_option('000985', 'D', 100)
    print(f"get_echarts_option: {type(r).__name__}, keys={list(r.keys())[:5]}")
except Exception as e:
    print(f"ERROR: {e}")
