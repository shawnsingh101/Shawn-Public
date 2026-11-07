"""Build the data file for the Funding Finder website (grants/site/data.json).

Combines:
  1. Entries from the office's reviewed guides (grants/guides/*.json), which
     carry their own topic, level, audience and source tags.
  2. Every active federal program in the SAM.gov Assistance Listings catalog
     (grants/data/assistance_listings.json), sorted into topics by rules.
  3. Currently open and upcoming funding notices from the Grants.gov API
     (no key needed), attached to the federal programs they belong to.

Usage: python grants/tools/build_site_data.py
"""
import glob
import json
import os
import re
import time
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
G = os.path.join(ROOT, "grants")
OUT = os.path.join(G, "site", "data.json")

# Topics: the office's 12 guides first, then a few more people search for.
TOPICS = [
    ("agriculture", "Agriculture & Rural Development", True),
    ("broadband", "Broadband", True),
    ("health", "Community & Public Health", True),
    ("safety", "Community Safety", True),
    ("infrastructure", "Infrastructure & Transportation", True),
    ("workforce", "Workforce Development", True),
    ("nutrition", "Nutrition & Obesity Prevention", True),
    ("education", "PreK-12 Education", True),
    ("business", "Small, Women- & Minority-Owned Business", True),
    ("rural", "Rural Economic Development", True),
    ("disaster", "Disaster Relief", True),
    ("tribal", "Tribal Communities", True),
    ("housing", "Housing", False),
    ("environment", "Environment, Energy & Water", False),
    ("arts", "Arts, Culture & Libraries", False),
    ("veterans", "Veterans", False),
    ("higher_ed", "Higher Education & Research", False),
]

# (topic, regex on title + objective + categories, optional department regex)
RULES = [
    ("agriculture", r"\b(farm\w*|agricultur\w*|ranch\w*|crop\w*|livestock|forest\w*|conservation reserve|specialty crop)", None),
    ("broadband", r"\b(broadband|internet|digital equity|telecommunicat\w*|distance learning)", None),
    ("health", r"\b(public health|health (care|center|workforce|professions)|hospital\w*|mental health|substance|opioid|behavioral health|medicaid|maternal|immuniz\w*|disease)", None),
    ("safety", r"\b(crime|violence|law enforcement|police|justice|victim\w*|firefight\w*|fire (prevention|protection)|homeland security|gang)", None),
    ("infrastructure", r"\b(highway\w*|bridge\w*|transit|rail\w*|airport\w*|port\w*|infrastructure|transportation|roads?)\b", None),
    ("workforce", r"\b(workforce|job training|apprentice\w*|employment and training|dislocated worker|vocational|career and technical|unemploy\w*)", None),
    ("nutrition", r"\b(nutrition|food|meals?|obesity|physical activity|snap|wic)\b", None),
    ("education", r"\b(elementary|secondary|k-12|school\w*|early childhood|head start|pre-?k|special education|title i)\b", None),
    ("business", r"\b(small business\w*|minority|women-owned|women owned|entrepreneur\w*|disadvantaged business|microloan|8\(a\))", None),
    ("rural", r"\b(rural)\b", None),
    ("disaster", r"\b(disasters?|hazard mitigation|flood (insurance|mitigation|control|prevention)|hurricanes?|wildfires?|emergency (management|preparedness|relief|loans?|conservation|watershed|food|shelter)|catastroph\w*|economic injury)", None),
    ("tribal", r"\b(tribal|tribes?|indian|native american|alaska native|native hawaiian)\b", None),
    ("housing", r"\b(housing|homeless\w*|rent\w*|mortgage|homeown\w*|home repair)", None),
    ("environment", r"\b(water|wastewater|drinking water|energy|environment\w*|pollution|brownfield\w*|climate|wildlife|clean air|solid waste)", None),
    ("arts", r"\b(arts?|humanities|museum\w*|librar\w*|historic preservation|cultural)\b", None),
    ("veterans", r"\b(veteran\w*)\b", None),
    ("higher_ed", r"\b(research|higher education|universit\w*|college\w*|fellowship\w*|graduate)\b", None),
]

AUDIENCE = [
    ("individuals", "Individuals & families", r"individual|family|homeowner|veteran|student|unrestricted by individual|senior|disab|reservist|active-duty|renter"),
    ("business", "Businesses", r"for-profit|small business|profit organization"),
    ("nonprofits", "Nonprofits", r"nonprofit|not-for-profit|non-profit"),
    ("local", "Local governments", r"\blocal\b|county|municipal|township|special district|housing authority|transit authority|water|port authority|consorti"),
    ("state", "State agencies", r"\bstate\b"),
    ("tribes", "Tribes", r"tribal|indian|native"),
    ("schools", "Schools & colleges", r"school|higher education|college|universit"),
    ("farmers", "Farmers & landowners", r"farm|rancher|agricultur|land/property owner|producer"),
]

HELP = [
    ("grant", "Grant", r"grant|cooperative agreement"),
    ("loan", "Loan or loan guarantee", r"loan"),
    ("insurance", "Insurance", r"insurance"),
    ("payment", "Direct payment", r"direct payment"),
    ("services", "Services & technical help", r"advisory|technical|training|counseling|information|provision of specialized|use of property|sale, exchange|dissemination|investigation"),
]


def clean(s, n=None):
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n:
        s = s[:n].rsplit(" ", 1)[0] + "…"
    return s


def title_case_agency(s):
    s = clean(s)
    if not s:
        return ""
    m = re.match(r"(.*), (DEPARTMENT OF( THE)?)$", s)
    if m:
        s = "Department of " + ("the " if m.group(3) else "") + m.group(1)
    small = {"of", "the", "and", "for", "on"}
    words = [w if (w.lower() in small and i) else (w if w.isupper() and len(w) <= 4 and w not in {"DEPT", "THE"} else w.capitalize()) for i, w in enumerate(s.lower().split())]
    out = " ".join(words)
    return re.sub(r"\bDept\b", "Department", out)


def tags_from(text, table):
    return [k for k, _label, rx in table if re.search(rx, text, re.I)]


def topics_for(text):
    return [t for t, rx, _ in RULES if re.search(rx, text, re.I)]


def amount_range(fin):
    rows = (fin or {}).get("rangeAndAverageAssistance") or []
    rows = [r for r in rows if isinstance(r, dict) and r.get("maximumAwardAmount")]
    if not rows:
        return None
    r = max(rows, key=lambda r: r.get("fiscalYear") or 0)
    return {"min": r.get("minimumAwardAmount"), "max": r.get("maximumAwardAmount"),
            "avg": r.get("averageAwardAmount"), "fy": r.get("fiscalYear")}


def federal_programs():
    path = os.path.join(G, "data", "assistance_listings.json")
    if not os.path.exists(path):
        return []
    out = []
    for r in json.load(open(path)):
        if (r.get("status") or "").lower() != "active":
            continue
        ov = r.get("overview") or {}
        cfa = r.get("criteriaForApplying") or {}
        app = cfa.get("applicant") or {}
        types = [t.get("name", "") if isinstance(t, dict) else str(t) for t in (app.get("types") or [])]
        if types and all(re.search(r"foreign|international", t, re.I) for t in types):
            continue  # programs only for foreign applicants
        cats = ov.get("missionSubCategories") or {}
        catnames = [((cats.get("primary") or {}).get("name") or "")] + [c.get("name", "") for c in (cats.get("other") or []) if isinstance(c, dict)]
        org = r.get("federalOrganization") or {}
        obj = clean(ov.get("objective"))
        hay = " ".join([r.get("title") or "", r.get("popularLongName") or "", obj, " ".join(catnames)])
        helps = []
        for ob in (r.get("financialInformation") or {}).get("obligations") or []:
            name = ((ob or {}).get("assistanceType") or {}).get("name") or ""
            helps += tags_from(name, HELP)
        contacts = []
        for c in ((r.get("contacts") or {}).get("headquarters") or [])[:2]:
            contacts.append(clean(" · ".join(x for x in [c.get("fullName"), c.get("title"), c.get("phone"), c.get("email")] if x)))
        local = clean(((r.get("contacts") or {}).get("local") or {}).get("officeLocationURL"))
        topics = topics_for(hay)
        dept = (org.get("department") or "")
        if re.search(r"AGRICULTURE", dept) and "agriculture" not in topics and "nutrition" not in topics:
            topics.append("agriculture")
        if re.search(r"HOMELAND SECURITY", dept) and re.search(r"FEMA|EMERGENCY MANAGEMENT", org.get("agency") or "", re.I) and "disaster" not in topics:
            topics.append("disaster")
        out.append({
            "id": "al-" + r["assistanceListingId"],
            "aln": r["assistanceListingId"],
            "title": clean(r.get("title")),
            "popular": clean(r.get("popularLongName"), 120) if clean(r.get("popularLongName")) != clean(r.get("title")) else "",
            "agency": title_case_agency(org.get("agency") or org.get("department")),
            "department": title_case_agency(dept),
            "level": "federal",
            "summary": clean(obj, 420),
            "description": clean(ov.get("assistanceListingDescription"), 1200),
            "who": clean(app.get("description"), 700),
            "uses": clean((cfa.get("assistanceUsage") or {}).get("description"), 900),
            "audience": sorted(set(tags_from(" ".join(types) + " " + (app.get("description") or "")[:300], AUDIENCE))),
            "help": sorted(set(helps)) or ["services"],
            "topics": topics or ["other"],
            "amount": amount_range(r.get("financialInformation")),
            "funded": bool((r.get("financialInformation") or {}).get("isFundedCurrentFY")),
            "url": clean(r.get("programWebPage")),
            "listing_url": f"https://sam.gov/fal/{r.get('programId', '')}/view" if r.get("programId") else "",
            "contacts": contacts,
            "local_contacts": local,
            "source": f"SAM.gov Assistance Listing {r['assistanceListingId']}",
            "updated": (r.get("publishedDate") or "")[:10],
            "reviewed": False,
        })
    return out


def blocks_to_html(blocks):
    def inline(t):
        t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
        return t
    html = []
    for b in blocks:
        if b["type"] == "p":
            html.append(f"<p>{inline(b['text'])}</p>")
        elif b["type"] == "bullets":
            html.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in b["items"]) + "</ul>")
    return "".join(html)


def first_link(blocks):
    for b in blocks:
        for t in [b.get("text", "")] + b.get("items", []):
            for label, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", t):
                if not url.startswith("mailto"):
                    return url
    return ""


def guide_entries():
    out, guides = [], []
    for path in sorted(glob.glob(os.path.join(G, "guides", "*.json"))):
        c = json.load(open(path))
        slug = os.path.splitext(os.path.basename(path))[0]
        topic = c.get("topic", slug)
        pdf = f"../output/{c['file_name']}.pdf"
        guides.append({"topic": topic, "title": " ".join(c["title_lines"]).strip(), "pdf": pdf,
                       "checked": c.get("checked"), "intro": c.get("site_intro", "")})
        for sec in c["sections"]:
            for e in sec["entries"]:
                if e.get("status") == "Removed":
                    continue
                tags = e.get("tags", {})
                plain = clean(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", " ".join(
                    b.get("text", "") + " " + " ".join(b.get("items", [])) for b in e["blocks"])).replace("**", ""))
                out.append({
                    "id": f"{slug}-{re.sub(r'[^a-z0-9]+', '-', e['title'].lower()).strip('-')[:50]}",
                    "title": e["title"],
                    "agency": tags.get("agency", ""),
                    "level": tags.get("level", "federal"),
                    "summary": clean(plain, 300),
                    "html": blocks_to_html(e["blocks"]),
                    "audience": tags.get("audience", []),
                    "help": tags.get("help", ["services"]),
                    "topics": [topic] + [t for t in tags.get("topics", []) if t != topic],
                    "aln": tags.get("aln", []),
                    "url": first_link(e["blocks"]),
                    "source": "; ".join(e.get("sources", [])[:2]),
                    "updated": c.get("checked", ""),
                    "reviewed": True,
                    "section": sec["title"],
                    "guide": slug,
                    "needs_check": bool(e.get("verify")),
                    "funded": True,
                })
    return out, guides


def grants_gov_open():
    """All posted and forecasted opportunities, grouped by Assistance Listing number."""
    by_aln, start, total = {}, 0, None
    while total is None or start < total:
        body = json.dumps({"oppStatuses": "forecasted|posted", "rows": 1000, "startRecordNum": start}).encode()
        req = urllib.request.Request("https://api.grants.gov/v1/api/search2", data=body,
                                     headers={"Content-Type": "application/json", "User-Agent": "gillibrand-grant-guides/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                j = json.load(r)["data"]
        except Exception as e:
            print("Grants.gov unavailable:", e)
            break
        total = j.get("hitCount", 0)
        hits = j.get("oppHits", [])
        for h in hits:
            item = {"id": h.get("id"), "number": h.get("number"), "title": clean(h.get("title")),
                    "status": h.get("oppStatus"), "open": h.get("openDate"), "close": h.get("closeDate"),
                    "url": f"https://www.grants.gov/search-results-detail/{h.get('id')}"}
            for aln in h.get("cfdaList") or []:
                by_aln.setdefault(aln, []).append(item)
        if not hits:
            break
        start += len(hits)
        time.sleep(1)
    print(f"Grants.gov: {sum(len(v) for v in by_aln.values())} notices across {len(by_aln)} programs")
    return by_aln


def main():
    reviewed, guides = guide_entries()
    federal = federal_programs()
    opps = grants_gov_open()
    for p in federal:
        p["opportunities"] = opps.get(p["aln"], [])
    reviewed_alns = {a for e in reviewed for a in e["aln"]}
    for e in reviewed:
        e["opportunities"] = [o for a in e["aln"] for o in opps.get(a, [])]
    for p in federal:
        p["in_guide"] = p["aln"] in reviewed_alns
    data = {
        "built": date.today().isoformat(),
        "topics": [{"id": t, "label": l, "guide": g} for t, l, g in TOPICS] + [{"id": "other", "label": "Other federal programs", "guide": False}],
        "audiences": [{"id": k, "label": l} for k, l, _ in AUDIENCE],
        "help": [{"id": k, "label": l} for k, l, _ in HELP],
        "levels": [{"id": "federal", "label": "Federal"}, {"id": "state", "label": "New York State"},
                   {"id": "local", "label": "Local"}, {"id": "private", "label": "Private & nonprofit"}],
        "guides": guides,
        "items": reviewed + federal,
        "catalog": json.load(open(os.path.join(G, "data", "_catalog_state.json"))) if os.path.exists(os.path.join(G, "data", "_catalog_state.json")) else {},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(reviewed)} reviewed entries, {len(federal)} federal programs -> {OUT} ({os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()
