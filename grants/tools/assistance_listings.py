"""Download the official catalog of federal assistance programs (SAM.gov
Assistance Listings) and save it as grants/data/assistance_listings.json.

Tries the public bulk extract first (no key); falls back to the SAM.gov API
when SAM_API_KEY is set. Each record keeps the listing number, title, agency,
objectives, eligibility, uses, financial info, contacts and website.
"""
import csv, io, json, os, sys, urllib.error, urllib.request, urllib.parse

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


def api_call(key, **params):
    q = urllib.parse.urlencode({"api_key": key, **params})
    try:
        st, body = get(f"https://api.sam.gov/assistance-listings/v1/search?{q}")
        return json.loads(body), None
    except urllib.error.HTTPError as e:
        return None, f"{e.code}: {e.read()[:400]!r}"
    except Exception as e:
        return None, str(e)


KEEP = ("assistanceListingId", "title", "popularLongName", "status", "publishedDate", "federalOrganization",
        "programWebPage", "overview", "financialInformation", "criteriaForApplying", "assistanceApplication",
        "contacts", "relatedFederalAssistance")


def slim(r):
    return {k: r.get(k) for k in KEEP}


def from_api(key):
    """Free SAM.gov keys allow only a handful of requests per day, so ask for
    large pages and stop as soon as everything is in."""
    from datetime import date
    out, page, pages, size = [], 1, 1, 1000
    while page <= pages:
        j, err = api_call(key, publishedDateTo=date.today().isoformat(), pageSize=size, pageNumber=page)
        if err:
            print("API error on page", page, err); break
        data = j.get("assistanceListingsData") or []
        pages = int(j.get("totalPages") or 1)
        print(f"page {page}/{pages}: {len(data)} records (pageSize reported {j.get('pageSize')}, total {j.get('totalRecords')})")
        out.extend(slim(r) for r in data)
        if not data or len(out) >= int(j.get("totalRecords") or 0):
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
