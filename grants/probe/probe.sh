#!/usr/bin/env bash
# Probe which grant-guide sources are reachable from a runner. One honest request each.
UA="gillibrand-tracker/0.1 (+https://github.com/shawnsingh101/Shawn-Public)"
B=https://www.gillibrand.senate.gov
echo "== grants page =="; curl -sS -A "$UA" -o g.html -w "%{http_code} %{size_download}B\n" $B/help/grants/
echo "== page sitemap entries mentioning grant/funding =="
curl -sS -A "$UA" $B/page-sitemap.xml | grep -oE '<loc>[^<]+' | sed 's/<loc>//' | grep -iE 'grant|fund|guide|help' 
echo "== feed mentions of grant guides =="
curl -sS -A "$UA" "$B/?s=grant+guide&feed=rss2" -o s.xml -w "search feed %{http_code}\n"; grep -oE '<title>[^<]+' s.xml | head -15
curl -sS -A "$UA" "$B/feed/?s=funding+guide" -o s2.xml -w "feed?s %{http_code}\n"; grep -oE '<title>[^<]+' s2.xml | head -10
echo "== uploads dir / a PDF =="
for u in "$B/wp-content/uploads/" "$B/wp-json/wp/v2/media?search=guide&per_page=5"; do curl -sS -A "$UA" -o x -w "$u -> %{http_code}\n" "$u"; head -c 300 x; echo; sleep 2; done
echo "== grants.gov search2 API =="
curl -sS -X POST https://api.grants.gov/v1/api/search2 -H 'Content-Type: application/json' -d '{"keyword":"broadband","oppStatuses":"forecasted|posted","rows":3}' | head -c 1500; echo
echo "== grants.gov fetchOpportunity =="
curl -sS -X POST https://api.grants.gov/v1/api/fetchOpportunity -H 'Content-Type: application/json' -d '{"opportunityId":289999}' | head -c 600; echo
echo "== SAM.gov assistance listings (public page + API with DEMO_KEY) =="
curl -sS -A "$UA" -o /dev/null -w "sam.gov page %{http_code}\n" https://sam.gov/assistance-listings
curl -sS "https://api.sam.gov/assistance-listings/v1/search?api_key=DEMO_KEY&keyword=broadband&pageSize=2" | head -c 800; echo
echo "== NYS sources =="
for u in https://grantsmanagement.ny.gov/ https://data.ny.gov/api/views/metadata/v1?limit=1 https://esd.ny.gov/ https://www.ny.gov/services/find-grants ; do curl -sS -A "$UA" -o /dev/null -w "$u -> %{http_code}\n" "$u"; sleep 1; done
