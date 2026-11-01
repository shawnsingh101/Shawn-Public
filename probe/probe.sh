#!/usr/bin/env bash
# Probe 2: inventory the site's published machine-readable endpoints (sitemaps, RSS).
# robots.txt allows all agents; we use one honest UA and pause between requests.
B=https://www.gillibrand.senate.gov
UA="gillibrand-tracker/0.1 (+https://github.com/shawnsingh101/Shawn-Public)"
echo "== sitemaps =="
for sm in $(curl -sS -A "$UA" $B/sitemap_index.xml | grep -oE '<loc>[^<]+' | sed 's/<loc>//'); do
  curl -sS -A "$UA" "$sm" -o sm.xml
  echo "$sm  urls=$(grep -c '<loc>' sm.xml)  e.g. $(grep -oE '<loc>[^<]+' sm.xml | sed -n 2p | sed 's/<loc>//')  oldest_lastmod=$(grep -oE '<lastmod>[^<]+' sm.xml | sed 's/<lastmod>//' | sort | head -1)"
  sleep 2
done
echo "== feeds =="
for f in "feed/" "feed/?paged=2" "feed/?paged=50" "feed/?paged=400"; do
  curl -sS -A "$UA" -o f.xml -w "$f -> %{http_code} %{size_download}B " "$B/$f"
  echo "items=$(grep -c '<item>' f.xml) content_encoded=$(grep -c 'content:encoded' f.xml) first=$(grep -oE '<pubDate>[^<]+' f.xml | head -1)"
  sleep 2
done
echo "== sample feed item =="
curl -sS -A "$UA" "$B/feed/" | awk '/<item>/{p=1} p{print} /<\/item>/{exit}' | head -c 2500
echo; echo "== categories in first feed page =="
curl -sS -A "$UA" "$B/feed/" | grep -oE '<category><!\[CDATA\[[^]]+' | sort | uniq -c
