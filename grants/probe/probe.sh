#!/usr/bin/env bash
# Probe 2: grants page structure + the linked guide PDFs (one polite request each).
UA="gillibrand-tracker/0.1 (+https://github.com/shawnsingh101/Shawn-Public)"
mkdir -p out/pdfs
curl -sS -A "$UA" -o out/grants.html https://www.gillibrand.senate.gov/help/grants/
curl -sS -A "$UA" -o out/grants_.html -w "grants_ %{http_code}\n" https://www.gillibrand.senate.gov/help/grants_/
python3 - <<'PY'
import re,html
s=open('out/grants.html',encoding='utf-8',errors='replace').read()
m=re.search(r'<main.*?</main>',s,re.S) or re.search(r'<body.*',s,re.S)
body=m.group(0)
links=re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',body,re.S)
for h,t in links:
    t=re.sub(r'<[^>]+>','',t).strip()
    if t: print("LINK",h,"|",html.unescape(t)[:100])
txt=re.sub(r'<(script|style).*?</\1>',' ',body,flags=re.S)
txt=html.unescape(re.sub(r'<[^>]+>','\n',txt))
txt=re.sub(r'\n\s*\n+','\n',txt)
print("=== TEXT ===");print(txt[:6000])
PY
grep -oE 'href="[^"]+\.pdf"' out/grants.html | sed 's/href="//;s/"$//' | sort -u > out/pdfs.txt
echo "== PDFs: $(wc -l < out/pdfs.txt)"
while read u; do sleep 2; curl -sS -A "$UA" -o "out/pdfs/$(basename "$u")" -w "%{http_code} %{size_download}B $u\n" "$u"; done < out/pdfs.txt
