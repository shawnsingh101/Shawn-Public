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


def from_api(key):
    from datetime import date
    base = {"publishedDateTo": date.today().isoformat()}
    j, err = api_call(key, **base)
    if err:
        print("API base call error:", err); return []
    print("API keys:", list(j.keys()), "totalPages:", j.get("totalPages"), "totalRecords:", j.get("totalRecords"))
    first = j.get("assistanceListingsData") or []
    if first:
        print("record fields:", list(first[0].keys()))
    # find the paging parameter that actually changes the page
    pager = None
    for cand in ("pageNumber", "page", "offset"):
        j2, err2 = api_call(key, **base, **{cand: 1})
        d2 = (j2 or {}).get("assistanceListingsData") or []
        print(f"paging param {cand}: err={err2} first={(d2[0].get('assistanceListingId') if d2 else None)}")
        if d2 and first and d2[0] != first[0]:
            pager = cand; break
    out = list(first)
    pages = int(j.get("totalPages") or 1)
    if pager:
        for n in range(1, pages):
            jn, errn = api_call(key, **base, **{pager: n})
            if errn:
                print("page", n, errn); break
            out.extend(jn.get("assistanceListingsData") or [])
    print("downloaded", len(out), "listings via API")
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
