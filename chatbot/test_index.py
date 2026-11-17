"""Phase 2 offline tests for search - no network. Run: python test_index.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index import SearchIndex  # noqa: E402

fails = 0


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else info)
    fails += not cond


BASE = "https://www.australianunity.com.au/health-insurance"
FAMILY = "Family cover includes dental claims for kids and extras for the whole family."
pages = [
    {"url": BASE + "/families", "title": "Families", "text": FAMILY},
    {"url": BASE + "/kids", "title": "Families", "text": FAMILY},  # same text, other URL
    {"url": BASE + "/corporate-affiliate/acme/families", "title": "Families", "text": FAMILY + " Acme"},
    {"url": BASE + "/how-to-claim", "title": "How to claim",
     "text": "To make a dental claim, swipe your card or claim in the app."},
    {"url": BASE + "/optical", "title": "Optical", "text": "Glasses and contact lenses."},
]
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "pages.json"
    f.write_text(json.dumps(pages))
    ix = SearchIndex(f)

check("excluded pages not indexed", ix.page_count == 4
      and not any("corporate-affiliate" in c["url"] for c in ix.chunks), ix.page_count)
res = ix.search("dental claim family", k=5)
texts = [" ".join(r["text"].split()) for r in res]
check("identical chunks returned once", len(texts) == len(set(texts)), [r["url"] for r in res])
check("dedupe makes room for other pages", any(r["url"].endswith("/how-to-claim") for r in res),
      [r["url"] for r in res])
check("k still respected", len(ix.search("dental claim family glasses", k=2)) == 2)
check("zero-score chunks dropped", ix.search("zzzz") == [])

# Real data: the claim page must be retrieved for the dental claim question.
real = SearchIndex()
res = real.search("How do I make a dental claim?")
check("real: how-to-claim retrieved",
      any(r["url"].endswith("/health-insurance/how-to-claim") for r in res), [r["url"] for r in res])
check("real: no corporate-affiliate chunks", not any("corporate-affiliate" in c["url"] for c in real.chunks))

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
