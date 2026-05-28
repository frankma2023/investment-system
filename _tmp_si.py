import urllib.request, json
resp = urllib.request.urlopen('http://localhost:8788/api/strongest-index')
data = json.loads(resp.read())
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
