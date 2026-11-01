"""Harvest every press release from gillibrand.senate.gov.

Uses only the site's published machine-readable endpoints (robots.txt allows
all agents): the RSS feed, which carries full text and pages back through the
whole archive via ?paged=N, and the XML sitemaps, used to check completeness.

Output: data/press/<year>.json  (list of releases, newest first)
        data/press_meta.json     (counts + completeness check)

Usage: python harvest/press.py [--full]
  --full  walk the entire feed (default: stop once a page has nothing new)
"""
import glob
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, fetch, html_to_text, load_json, save_json  # noqa: E402

BASE = "https://www.gillibrand.senate.gov"
NS = {"content": "http://purl.org/rss/1.0/modules/content/",
      "dc": "http://purl.org/dc/elements/1.1/"}
PAUSE = 2.0  # seconds between requests
PRESS_DIR = os.path.join(DATA, "press")


def load_existing():
    out = {}
    for p in glob.glob(os.path.join(PRESS_DIR, "*.json")):
        for r in load_json(p, []):
            out[r["url"]] = r
    return out


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        url = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        dt = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else None
        body = it.findtext("content:encoded", default="", namespaces=NS) or it.findtext("description") or ""
        items.append({
            "id": (it.findtext("guid") or url).strip(),
            "title": html_to_text(it.findtext("title") or ""),
            "date": dt.strftime("%Y-%m-%d") if dt else "",
            "url": url,
            "categories": [c.text for c in it.findall("category") if c.text and c.text != "Uncategorized"],
            "text": html_to_text(body),
        })
    return items


def sitemap_urls():
    status, idx = fetch(f"{BASE}/sitemap_index.xml")
    urls = set()
    for sm in re.findall(r"<loc>([^<]+)</loc>", idx.decode()):
        if "post-sitemap" not in sm:
            continue
        time.sleep(PAUSE)
        _, body = fetch(sm)
        urls.update(u for u in re.findall(r"<loc>([^<]+)</loc>", body.decode()) if "/news/press/release/" in u)
    return urls


def main():
    full = "--full" in sys.argv
    have = load_existing()
    print(f"existing releases: {len(have)}; mode={'full' if full or not have else 'incremental'}", flush=True)
    if not have:
        full = True
    page, added = 1, 0
    while True:
        url = f"{BASE}/feed/" + (f"?paged={page}" if page > 1 else "")
        status, body = fetch(url)
        if status == 404:
            print(f"page {page}: end of feed", flush=True)
            break
        items = parse_feed(body)
        if not items:
            break
        new = [i for i in items if i["url"] not in have]
        for i in items:
            have[i["url"]] = i  # refresh text too (edits happen)
        added += len(new)
        if page % 25 == 0 or new:
            print(f"page {page}: {len(items)} items, {len(new)} new, oldest {items[-1]['date']}", flush=True)
        if not full and not new:
            break
        page += 1
        time.sleep(PAUSE)

    by_year = {}
    for r in have.values():
        by_year.setdefault(r["date"][:4] or "unknown", []).append(r)
    for y, rows in by_year.items():
        rows.sort(key=lambda r: (r["date"], r["title"]), reverse=True)
        save_json(os.path.join(PRESS_DIR, f"{y}.json"), rows, compact=True)

    # Completeness check against the site's own sitemaps.
    time.sleep(PAUSE)
    sm = sitemap_urls()
    norm = lambda u: u.rstrip("/").lower()
    got = {norm(u) for u in have}
    missing = sorted(u for u in sm if norm(u) not in got)
    dates = sorted(r["date"] for r in have.values() if r["date"])
    meta = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(have),
        "added_this_run": added,
        "oldest": dates[0] if dates else None,
        "newest": dates[-1] if dates else None,
        "by_year": {y: len(v) for y, v in sorted(by_year.items())},
        "sitemap_press_urls": len(sm),
        "in_sitemap_but_not_in_feed": len(missing),
        "missing_sample": missing[:50],
    }
    save_json(os.path.join(DATA, "press_meta.json"), meta)
    print({k: v for k, v in meta.items() if k != "missing_sample"}, flush=True)


if __name__ == "__main__":
    main()
