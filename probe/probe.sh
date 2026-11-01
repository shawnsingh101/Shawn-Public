#!/usr/bin/env bash
# Feasibility probe: can a GitHub runner reach both data sources?
UA="Mozilla/5.0 (research tool; contact via GitHub)"
echo "== press release listing =="
curl -sS -A "$UA" -o pr.html -w "status %{http_code} size %{size_download}\n" https://www.gillibrand.senate.gov/press-releases/
grep -oE 'href="https://www.gillibrand.senate.gov/news/press/release/[^"]+"' pr.html | head -5
grep -oE 'href="[^"]*(page|paged)[^"]*"' pr.html | sort -u | head -10
grep -oiE '<(article|h2|h3)[^>]*>' pr.html | sort | uniq -c | head
echo "== generator / wp-json =="
grep -oiE '<meta name="generator"[^>]*>' pr.html
grep -oiE 'wp-json[^"]*' pr.html | sort -u | head
for u in "wp-json/" "wp-json/wp/v2/types" "wp-json/wp/v2/posts?per_page=1" "wp-json/wp/v2/press_release?per_page=1" "feed/" "sitemap.xml" "sitemap_index.xml" "wp-sitemap.xml" "robots.txt"; do
  curl -sS -A "$UA" -o out.txt -D hdr.txt -w "$u -> %{http_code} %{size_download}B\n" "https://www.gillibrand.senate.gov/$u"
  grep -iE '^x-wp-total' hdr.txt
  head -c 600 out.txt; echo; echo ---
done
echo "== press listing page 2 / last pages =="
for p in 2 100 300 600; do curl -sS -A "$UA" -o p.html -w "page $p -> %{http_code} %{size_download}B\n" "https://www.gillibrand.senate.gov/press-releases/page/$p/"; grep -oE '[A-Z][a-z]+ [0-9]{1,2}, (19|20)[0-9]{2}' p.html | head -2; done
echo "== congress.gov API (DEMO_KEY) =="
for k in sponsored-legislation cosponsored-legislation; do
  curl -sS "https://api.congress.gov/v3/member/G000555/$k?api_key=DEMO_KEY&limit=1&format=json" | head -c 900; echo; echo ---
done
