"""Harvest every bill Gillibrand sponsored or co-sponsored, via the official
Congress.gov API (key in env CONGRESS_API_KEY; free at api.data.gov/signup).

For each bill: titles, dates, latest action, policy area, legislative subjects,
the latest CRS summary, and (for co-sponsorships) her co-sponsor date; bills
whose co-sponsorship she withdrew are dropped.

Output: data/bills/<congress>.json, data/bills_meta.json
Resumable: already-complete bills are skipped; stops cleanly at a time budget
(env BUDGET_MIN, default 330) so a later run can continue.
"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, fetch, html_to_text, load_json, save_json  # noqa: E402

API = "https://api.congress.gov/v3"
MEMBER = "G000555"
KEY = os.environ.get("CONGRESS_API_KEY", "")
PAUSE = 0.8  # ~4,500 requests/hour, under the 5,000/hour limit
BILLS_DIR = os.path.join(DATA, "bills")
START = time.time()
BUDGET = float(os.environ.get("BUDGET_MIN", "330")) * 60

TYPE_SLUG = {
    "S": "senate-bill", "HR": "house-bill", "SRES": "senate-resolution",
    "HRES": "house-resolution", "SJRES": "senate-joint-resolution",
    "HJRES": "house-joint-resolution", "SCONRES": "senate-concurrent-resolution",
    "HCONRES": "house-concurrent-resolution",
}
TYPE_LABEL = {"S": "S.", "HR": "H.R.", "SRES": "S.Res.", "HRES": "H.Res.", "SJRES": "S.J.Res.",
              "HJRES": "H.J.Res.", "SCONRES": "S.Con.Res.", "HCONRES": "H.Con.Res."}

calls = 0


def api(path, **params):
    global calls
    params.setdefault("format", "json")
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    time.sleep(PAUSE)
    calls += 1
    status, body = fetch(f"{API}{path}?{qs}", headers={"X-Api-Key": KEY})
    return json.loads(body) if status == 200 else {}


def current_congress(d=None):
    d = d or date.today()
    y = d.year if not (d.month == 1 and d.day < 3) else d.year - 1
    return (y - 1789) // 2 + 1


def ordinal(n):
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def list_all(kind):
    """kind: 'sponsored' or 'cosponsored'. Returns list of bill stubs."""
    out, offset = [], 0
    key = f"{kind}Legislation"
    while True:
        j = api(f"/member/{MEMBER}/{kind}-legislation", limit=250, offset=offset)
        rows = j.get(key, [])
        out.extend(rows)
        total = j.get("pagination", {}).get("count", 0)
        offset += 250
        if not rows or offset >= total:
            return out, total


def bill_key(c, t, n):
    return f"{c}-{t}-{n}"


def time_left():
    return BUDGET - (time.time() - START)


def main():
    if not KEY:
        sys.exit("CONGRESS_API_KEY is not set")
    cur = current_congress()
    sponsored, n_sp = list_all("sponsored")
    cosponsored, n_co = list_all("cosponsored")
    print(f"listed: sponsored {n_sp}, cosponsored {n_co}", flush=True)

    stubs = {}
    skipped_amendments = 0
    for role, rows in (("Sponsor", sponsored), ("Cosponsor", cosponsored)):
        for r in rows:
            if not r.get("type") or r.get("amendmentNumber"):
                skipped_amendments += 1
                continue
            k = bill_key(r["congress"], r["type"].upper(), r["number"])
            stubs[k] = (role, r)

    # Load what we already have.
    have = {}
    for c in {s[1]["congress"] for s in stubs.values()}:
        for b in load_json(os.path.join(BILLS_DIR, f"{c}.json"), []):
            have[b["key"]] = b

    def needs_fetch(k, stub):
        b = have.get(k)
        if not b or not b.get("complete"):
            return True
        la = (stub.get("latestAction") or {}).get("actionDate")
        if stub["congress"] == cur and la != b.get("latest_action_date"):
            return True
        if not b.get("summary"):
            age = datetime.now(timezone.utc) - datetime.fromisoformat(b["fetched"])
            return age > timedelta(days=7 if stub["congress"] == cur else 60)
        return False

    todo = [k for k, (role, s) in stubs.items() if needs_fetch(k, s)]
    # Newest first so the current Congress is ready soonest.
    todo.sort(key=lambda k: (-stubs[k][1]["congress"], stubs[k][1].get("introducedDate") or ""), reverse=False)
    print(f"bills to fetch/refresh: {len(todo)} of {len(stubs)}", flush=True)

    done = 0
    for k in todo:
        if time_left() < 300:
            print("time budget reached; saving progress for next run", flush=True)
            break
        role, s = stubs[k]
        c, t, n = s["congress"], s["type"].upper(), s["number"]
        base = f"/bill/{c}/{t.lower()}/{n}"
        rec = {
            "key": k, "congress": c, "type": t, "number": str(n),
            "label": f"{TYPE_LABEL.get(t, t)} {n}",
            "role": role, "title": s.get("title") or "",
            "introduced": s.get("introducedDate") or "",
            "latest_action": (s.get("latestAction") or {}).get("text") or "",
            "latest_action_date": (s.get("latestAction") or {}).get("actionDate") or "",
            "policy_area": (s.get("policyArea") or {}).get("name") or "",
            "url": f"https://www.congress.gov/bill/{ordinal(c)}-congress/{TYPE_SLUG.get(t, t.lower())}/{n}",
        }
        # Co-sponsorship details (date, original?, withdrawn?)
        if role == "Cosponsor":
            off, me = 0, None
            while me is None:
                j = api(f"{base}/cosponsors", limit=250, offset=off)
                for cs in j.get("cosponsors", []):
                    if cs.get("bioguideId") == MEMBER:
                        me = cs
                off += 250
                if off >= j.get("pagination", {}).get("count", 0):
                    break
            if me and me.get("sponsorshipWithdrawnDate"):
                rec["withdrawn"] = me["sponsorshipWithdrawnDate"]
            if me:
                rec["cosponsor_date"] = me.get("sponsorshipDate") or ""
                rec["original_cosponsor"] = bool(me.get("isOriginalCosponsor"))
        subj = api(f"{base}/subjects").get("subjects", {})
        rec["subjects"] = [x["name"] for x in subj.get("legislativeSubjects", [])]
        rec["policy_area"] = (subj.get("policyArea") or {}).get("name") or rec["policy_area"]
        sums = api(f"{base}/summaries").get("summaries", [])
        if sums:
            latest = max(sums, key=lambda x: (x.get("actionDate") or "", x.get("updateDate") or ""))
            rec["summary"] = html_to_text(latest.get("text", ""))
            rec["summary_version"] = latest.get("actionDesc") or ""
        else:
            rec["summary"] = ""
        rec["fetched"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec["complete"] = True
        have[k] = rec
        done += 1
        if done % 250 == 0:
            save(have, stubs)
            print(f"  {done}/{len(todo)} fetched, {calls} API calls, {time_left()/60:.0f} min left", flush=True)

    save(have, stubs)
    kept = [b for b in have.values() if b["key"] in stubs and not b.get("withdrawn")]
    meta = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current_congress": cur,
        "api_listed_sponsored": n_sp, "api_listed_cosponsored": n_co,
        "amendments_skipped": skipped_amendments,
        "bills_known": len(stubs),
        "bills_complete": sum(1 for b in have.values() if b.get("complete") and b["key"] in stubs),
        "withdrawn_cosponsorships_excluded": sum(1 for b in have.values() if b.get("withdrawn")),
        "sponsored": sum(1 for b in kept if b["role"] == "Sponsor"),
        "cosponsored": sum(1 for b in kept if b["role"] == "Cosponsor"),
        "with_crs_summary": sum(1 for b in kept if b.get("summary")),
        "fetched_this_run": done, "api_calls_this_run": calls,
        "finished": done == len(todo),
    }
    save_json(os.path.join(DATA, "bills_meta.json"), meta)
    print(meta, flush=True)


def save(have, stubs):
    by_c = {}
    for b in have.values():
        if b["key"] in stubs:
            by_c.setdefault(b["congress"], []).append(b)
    for c, rows in by_c.items():
        rows.sort(key=lambda b: (b["introduced"], b["key"]), reverse=True)
        save_json(os.path.join(BILLS_DIR, f"{c}.json"), rows, compact=True)


if __name__ == "__main__":
    main()
