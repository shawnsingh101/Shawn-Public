"""Shared helpers for the harvesters (Python standard library only)."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from html import unescape

UA = "gillibrand-tracker/0.1 (+https://github.com/shawnsingh101/Shawn-Public)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def fetch(url, headers=None, retries=4, timeout=60):
    """GET a URL politely, retrying transient errors with backoff.
    Returns (status, bytes). 404 is returned, not raised."""
    h = {"User-Agent": UA}
    h.update(headers or {})
    delay = 5
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = int(e.headers.get("Retry-After") or delay)
                print(f"  HTTP {e.code} on {url}; waiting {wait}s", flush=True)
                time.sleep(wait)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < retries:
                print(f"  network error {e} on {url}; waiting {delay}s", flush=True)
                time.sleep(delay)
                delay *= 2
                continue
            raise


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|h[1-6]|tr|blockquote)[^>]*>", re.I)


def html_to_text(html):
    if not html:
        return ""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = _BLOCK.sub("\n", t)
    t = unescape(_TAG.sub("", t))
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, obj, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
