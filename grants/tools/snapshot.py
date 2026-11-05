"""Save dated text copies of the official pages a grant guide relies on.

Usage: python grants/tools/snapshot.py grants/sources/<guide>.txt
Writes grants/snapshots/<guide>/<n>-<slug>.md and a link report
grants/snapshots/<guide>/_links.csv (status, final URL) for every source.
One polite request per page with an honest user agent; no retries around blocks.
"""
import csv, html, os, re, sys, time, urllib.error, urllib.request
from datetime import date

UA = "gillibrand-grant-guides/0.1 (+https://github.com/shawnsingh101/Shawn-Public)"


def text_of(raw, ctype):
    s = raw.decode("utf-8", "replace")
    if "html" not in ctype and "<html" not in s[:2000].lower():
        return s
    s = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    m = re.search(r"<main[^>]*>(.*?)</main>", s, re.S | re.I)
    body = m.group(1) if m else s
    title = re.search(r"<title[^>]*>(.*?)</title>", s, re.S | re.I)
    # keep link targets so contact pages / deeper links can be followed
    body = re.sub(r'<a[^>]+href="([^"#][^"]*)"[^>]*>(.*?)</a>', lambda m: f"{m.group(2)} <{m.group(1)}>", body, flags=re.S | re.I)
    body = re.sub(r"</?(p|div|br|li|h[1-6]|tr|td|section|article)[^>]*>", "\n", body, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", body))
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    return (("# " + html.unescape(title.group(1)).strip() + "\n\n") if title else "") + t


def main(src):
    guide = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join("grants", "snapshots", guide)
    os.makedirs(out, exist_ok=True)
    rows = []
    lines = [l for l in open(src) if l.strip() and not l.startswith("#")]
    for i, line in enumerate(lines, 1):
        label, url = [x.strip() for x in line.rsplit("|", 1)]
        status, final, note = "", url, ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*"})
            with urllib.request.urlopen(req, timeout=45) as r:
                status, final = r.status, r.geturl()
                body = text_of(r.read(), r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
        except Exception as e:  # DNS, TLS, timeout
            status, body, note = "error", "", str(e)[:120]
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:60]
        if body:
            with open(os.path.join(out, f"{i:02d}-{slug}.md"), "w") as f:
                f.write(f"<!-- source: {url}\nfinal: {final}\nstatus: {status}\nfetched: {date.today()} -->\n\n{body}\n")
        rows.append([label, url, status, final, note])
        print(status, label, final if final != url else "", note, flush=True)
        time.sleep(2)
    with open(os.path.join(out, "_links.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["label", "url", "status", "final_url", "note"]); w.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1])
