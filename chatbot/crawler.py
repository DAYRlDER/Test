"""Phase 1 - Crawler.

Crawls START_URL and every page whose URL begins with it (same domain),
extracts the main text and title, and saves them to data/pages.json.

Usage:
    python crawler.py                 # use settings from config.py
    python crawler.py --max-pages 20  # quick test run
    python crawler.py --start-url https://example.com/docs
"""
import argparse
import json
import re
import time
from collections import Counter, deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import config

# File types we never want to download as "pages".
SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip",
    ".mp3", ".mp4", ".mov", ".css", ".js", ".xml", ".json",
)

# Tags that are never main content.
STRIP_TAGS = ["script", "style", "noscript", "nav", "header", "footer",
              "form", "iframe", "svg", "button", "template"]

# Inline tags that should not break a sentence onto a new line.
INLINE_TAGS = ["a", "span", "strong", "em", "b", "i", "u", "sup", "sub", "small", "abbr"]

# Repeated lines with at least this many words are dropped as boilerplate.
# Shorter repeats (e.g. "12 months" in a table) are kept.
MIN_DEDUPE_WORDS = 5

# id/class names that indicate cookie or consent banners.
BANNER_PATTERN = re.compile(r"cookie|consent|onetrust|gdpr", re.I)


def normalize_url(url: str) -> str:
    """Make URLs comparable: drop #fragment and ?query, lowercase host/path, strip trailing slash."""
    p = urlparse(url)
    path = p.path.lower().rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))


def in_scope(url: str, start: str) -> bool:
    """Same host, and the path is the start path or a sub-page of it."""
    u, s = urlparse(url), urlparse(start)
    if u.scheme not in ("http", "https") or u.netloc != s.netloc:
        return False
    return u.path == s.path or u.path.startswith(s.path.rstrip("/") + "/")


def load_robots(start_url: str) -> RobotFileParser:
    p = urlparse(start_url)
    rp = RobotFileParser()
    rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
    try:
        rp.read()
    except Exception as e:  # if robots.txt can't be read, be safe and stop
        raise SystemExit(f"Could not read robots.txt: {e}")
    return rp


def extract(html: str) -> tuple[str, str, list[str]]:
    """Return (title, main_text, links) from a page's HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Collect links before we delete nav/footer (they hold many useful links).
    links = [a["href"] for a in soup.find_all("a", href=True)]

    # Title: prefer the page's <h1>, fall back to <title>.
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    # Remove clutter.
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    for el in soup.find_all(True):
        if el.decomposed or el.name in ("html", "body", "main"):
            continue
        classes = el.get("class") or []
        attrs = " ".join([el.get("id") or ""] + classes)
        style = (el.get("style") or "").replace(" ", "").lower()
        if (
            BANNER_PATTERN.search(attrs)                      # cookie banners
            or (config.REMOVE_CLASS_PATTERN and re.search(config.REMOVE_CLASS_PATTERN, attrs))
            or "d-none" in classes                            # hidden (Bootstrap)
            or el.has_attr("hidden") or "display:none" in style
        ):
            el.decompose()

    root = soup.find("main") or soup.body or soup
    # Unwrap inline tags so "click <a>here</a> to claim" stays on one line.
    for el in root.find_all(INLINE_TAGS):
        el.unwrap()
    root.smooth()  # merge the now-adjacent text pieces
    # Turn each table row into one line ("Benefit | Waiting period") so values
    # stay next to the label they belong to.
    for table in reversed(root.find_all("table")):  # innermost tables first
        table.replace_with("\n" + "\n".join(table_rows(table)) + "\n")
    lines, seen = [], set()
    for line in root.get_text("\n").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line or (lines and line == lines[-1]):
            continue  # drop blank lines and back-to-back repeats
        # Drop longer repeated lines (repeated banners/blurbs), but keep short
        # ones: values like "12 months" legitimately appear many times.
        if len(line.split()) >= MIN_DEDUPE_WORDS:
            if line in seen:
                continue
            seen.add(line)
        lines.append(line)
    return title, "\n".join(lines), links


def _span(cell, attr: str) -> int:
    try:
        return max(1, min(int(cell.get(attr, 1)), 50))
    except (TypeError, ValueError):
        return 1


def table_rows(table) -> list[str]:
    """Return one "cell | cell" line per table row, filling in rowspan/colspan cells."""
    rows, carry = [], {}  # carry: column -> (text, rows still to fill)
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue  # row of a nested table (already flattened)
        cells, col = [], 0
        tds = iter(tr.find_all(["td", "th"], recursive=False))
        while True:
            if col in carry:  # a cell from a row above spans into this row
                text, left = carry.pop(col)
                if left > 1:
                    carry[col] = (text, left - 1)
                cells.append(text)
                col += 1
                continue
            td = next(tds, None)
            if td is None:
                break
            text = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
            rowspan = _span(td, "rowspan")
            for _ in range(_span(td, "colspan")):
                cells.append(text)
                if rowspan > 1:
                    carry[col] = (text, rowspan - 1)
                col += 1
        for c in sorted(k for k in carry if k >= col):  # spans past the last cell
            text, left = carry.pop(c)
            if left > 1:
                carry[c] = (text, left - 1)
            cells.append(text)
        merged = [c for i, c in enumerate(cells) if c and (i == 0 or c != cells[i - 1])]
        if merged:
            rows.append(" | ".join(merged))
    return rows


def crawl(start_url: str, max_pages: int) -> None:
    start_url = normalize_url(start_url)
    robots = load_robots(start_url)
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT

    queue = deque([start_url])
    seen = {start_url}
    pages, errors = [], []
    skipped = Counter()
    first_request = True

    while queue and len(pages) < max_pages:
        url = queue.popleft()

        if url.endswith(SKIP_EXTENSIONS):
            skipped["not HTML (extension)"] += 1
            continue
        if not robots.can_fetch(config.USER_AGENT, url):
            skipped["blocked by robots.txt"] += 1
            continue

        if not first_request:
            time.sleep(config.REQUEST_DELAY)  # 1 request per second
        first_request = False

        try:
            resp = session.get(url, timeout=config.REQUEST_TIMEOUT)
        except requests.RequestException as e:
            errors.append((url, type(e).__name__))
            continue
        if resp.status_code != 200:
            errors.append((url, f"HTTP {resp.status_code}"))
            continue

        # Redirects may land outside our section.
        final_url = normalize_url(resp.url)
        if not in_scope(final_url, start_url):
            skipped["redirected out of scope"] += 1
            continue
        if final_url != url and final_url in {p["url"] for p in pages}:
            skipped["duplicate (redirect)"] += 1
            continue
        if "text/html" not in resp.headers.get("Content-Type", ""):
            skipped["not HTML (content type)"] += 1
            continue

        seen.add(final_url)
        title, text, links = extract(resp.text)

        for href in links:
            link = normalize_url(urljoin(final_url, href))
            if link in seen:
                continue
            seen.add(link)
            if in_scope(link, start_url):
                queue.append(link)
            else:
                skipped["link out of scope"] += 1

        if len(text.split()) < config.MIN_TEXT_WORDS:
            skipped["too little text"] += 1
            continue

        pages.append({
            "url": final_url,
            "title": title,
            "text": text,
            "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        print(f"[{len(pages):>3}] {final_url}  ({len(text.split())} words)")

    config.DATA_DIR.mkdir(exist_ok=True)
    config.PAGES_FILE.write_text(json.dumps(pages, indent=2, ensure_ascii=False))

    # ---- Summary ----
    print("\n=== Crawl summary ===")
    print(f"Pages saved:   {len(pages)}  ->  {config.PAGES_FILE}")
    if len(pages) >= max_pages and queue:
        print(f"Stopped at max_pages={max_pages}; {len(queue)} URLs left in queue.")
    print(f"Skipped:       {sum(skipped.values())}")
    for reason, n in skipped.most_common():
        print(f"   - {reason}: {n}")
    print(f"Errors:        {len(errors)}")
    for url, why in errors:
        print(f"   - {why}: {url}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Crawl one website section.")
    ap.add_argument("--start-url", default=config.START_URL)
    ap.add_argument("--max-pages", type=int, default=config.MAX_PAGES)
    args = ap.parse_args()
    crawl(args.start_url, args.max_pages)
