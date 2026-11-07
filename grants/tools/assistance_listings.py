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


STATE = os.path.join("grants", "data", "_catalog_state.json")


def load(path, default):
    try:
        return json.load(open(path))
    except (FileNotFoundError, ValueError):
        return default


def main():
    """Build up the full catalog a few pages a day (free SAM.gov keys allow 10
    requests/day), then keep it current with small 'changed since' requests."""
    from datetime import date
    key = os.environ.get("SAM_API_KEY")
    if not key:
        sys.exit("SAM_API_KEY is not set")
    budget = int(os.environ.get("SAM_MAX_CALLS", "8"))
    state = load(STATE, {})
    catalog = {r["assistanceListingId"]: r for r in load(OUT, []) if r.get("assistanceListingId")}
    calls = 0

    def fetch(**params):
        nonlocal calls
        calls += 1
        j, err = api_call(key, pageSize=100, **params)
        if err:
            print("API error:", err)
        return j

    if not state.get("complete"):
        state.setdefault("snapshot_date", date.today().isoformat())
        done = set(state.get("pages_done", []))
        total = state.get("total_pages")
        page = 1
        while calls < budget:
            while page in done:
                page += 1
            if total and page > total:
                break
            j = fetch(publishedDateTo=state["snapshot_date"], pageNumber=page)
            if not j:
                break
            total = state["total_pages"] = int(j.get("totalPages") or 1)
            state["total_records"] = j.get("totalRecords")
            for r in j.get("assistanceListingsData") or []:
                catalog[r["assistanceListingId"]] = slim(r)
            done.add(page)
            print(f"page {page}/{total} ok; catalog now {len(catalog)}")
        state["pages_done"] = sorted(done)
        if total and len(done) >= total:
            state["complete"] = True
            state["last_full"] = state["snapshot_date"]
            state["changes_since"] = state["snapshot_date"]
    else:
        page = 1
        while calls < budget:
            j = fetch(publishedDateFrom=state["changes_since"], pageNumber=page)
            if not j:
                break
            rows = j.get("assistanceListingsData") or []
            for r in rows:
                catalog[r["assistanceListingId"]] = slim(r)
            print(f"changes page {page}/{j.get('totalPages')}: {len(rows)} updated listings")
            if page >= int(j.get("totalPages") or 1):
                state["changes_since"] = date.today().isoformat()
                break
            page += 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(sorted(catalog.values(), key=lambda r: r["assistanceListingId"]), f, ensure_ascii=False, separators=(",", ":"))
    state["listings"] = len(catalog)
    state["calls_last_run"] = calls
    json.dump(state, open(STATE, "w"), indent=1)
    print(json.dumps({k: v for k, v in state.items() if k != "pages_done"}))


if __name__ == "__main__":
    main()
