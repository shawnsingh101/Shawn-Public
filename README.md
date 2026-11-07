# Gillibrand Record Search

Searches every bill Sen. Kirsten Gillibrand has sponsored or co-sponsored
(from the official Congress.gov API) and every press release on
gillibrand.senate.gov, by topic and time period. Results show an overview plus
a table (type, title, date, summary, link) that can be downloaded for Excel.

- `index.html` — the search page (runs entirely in the browser; no install).
- `harvest/press.py` — downloads press releases from the site's RSS feed and
  checks them against its sitemaps for completeness.
- `harvest/bills.py` — downloads bills, CRS summaries, subjects and co-sponsor
  dates from the Congress.gov API (needs the `CONGRESS_API_KEY` secret).
  Withdrawn co-sponsorships are excluded.
- `.github/workflows/harvest.yml` — runs both harvesters nightly and commits
  the results to `data/`.

All data comes from public sources. Nothing typed into the search page is sent
anywhere.
