"""Download the official catalog of federal assistance programs (SAM.gov
Assistance Listings) and save it as grants/data/assistance_listings.json.

Tries the public bulk extract first (no key); falls back to the SAM.gov API
when SAM_API_KEY is set. Each record keeps the listing number, title, agency,
objectives, eligibility, uses, financial info, contacts and website.
"""
import csv, io, json, os, sys, urllib.request, urllib.parse

UA = "gillibrand-grant-guides/0.1 (+https://github.com/shawnsingh101/Shawn-Public)"
OUT = os.path.join("grants", "data", "assistance_listings.json")
EXTRACTS = [
    "https://sam.gov/api/prod/fileextractservices/v1/api/download/Assistance%20Listings/AssistanceListings_DataGov_PUBLIC_CURRENT.csv?privacy=Public",
    "https://s3.amazonaws.com/falextracts/Assistance%20Listings/AssistanceListings_DataGov_PUBLIC_CURRENT.csv",
]


def get(url, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
        return r.status, r.read()


def from_extract():
    for u in EXTRACTS:
        try:
            st, body = get(u)
            text = body.decode("utf-8-sig", "replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            print(f"extract {u[:70]}… -> {st}, {len(rows)} rows; columns: {list(rows[0].keys())[:40] if rows else []}")
            if rows:
                return rows
        except Exception as e:
            print(f"extract {u[:70]}… failed: {e}")
    return []


def from_api(key):
    out, page = [], 0
    while True:
        q = urllib.parse.urlencode({"api_key": key, "pageSize": 100, "pageNumber": page, "status": "Active"})
        try:
            st, body = get(f"https://api.sam.gov/assistance-listings/v1/search?{q}")
        except Exception as e:
            print("API error:", e); break
        j = json.loads(body)
        if page == 0:
            print("API keys:", list(j.keys())[:20])
        items = j.get("assistanceListingsData") or j.get("results") or j.get("data") or []
        out.extend(items)
        if not items or len(items) < 100:
            break
        page += 1
    return out


def main():
    rows = from_extract()
    if not rows and os.environ.get("SAM_API_KEY"):
        rows = from_api(os.environ["SAM_API_KEY"])
    if not rows:
        sys.exit("No assistance listing data could be downloaded (add SAM_API_KEY secret).")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"saved {len(rows)} listings to {OUT}")


if __name__ == "__main__":
    main()
