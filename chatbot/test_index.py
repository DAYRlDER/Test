"""Phase 2 offline tests for search - no network. Run: python test_index.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index import SearchIndex, chunk_page, page_units  # noqa: E402

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

# --- Table-aware chunking ---
TABLE = ["Dental", "Benefit | Waiting period", "General dental | 2 months", "Major dental | 12 months",
         "Other extras", "Glasses | 6 months", "Hearing aids | 12 months"]
filler = ["word " * 20] * 6  # 120 words of plain text
text = "\n".join(filler + TABLE + ["After the table."])
units = page_units(text, 500)
check("table is one unit with caption and sub-heading", TABLE in units, units)
chunks = chunk_page({"url": "u", "title": "t", "text": text}, size=130, overlap=0)
holding = [c for c in chunks if "Hearing aids | 12 months" in c["text"]]
check("table not split across chunks",
      len(holding) == 1 and all(row in holding[0]["text"] for row in TABLE), [c["text"] for c in chunks])

big = "\n".join(["Benefit | Wait"] + [f"Service number {i} with a long name | {i} months" for i in range(40)])
groups = page_units(big, 60)
check("long table split into groups", len(groups) > 1, len(groups))
check("each group repeats header", all(g[0] == "Benefit | Wait" for g in groups), [g[0] for g in groups])
check("no rows lost", sum(len(g) - 1 for g in groups) == 40)
check("short line not followed by a row is not table", page_units("A | b\nShort\nPlain text here.", 500)
      == [["A | b"], ["Short"], ["Plain text here."]])

# --- Next-chunk expansion ---
long_page = {"url": BASE + "/long", "title": "Long",
             "text": "\n".join([f"Line {i} about waiting periods." for i in range(5)]
                               + [f"Line {i} filler words here." for i in range(5, 200)]
                               + ["Hearing aids | 12 months"])}
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "pages.json"
    f.write_text(json.dumps([long_page]))
    ix = SearchIndex(f)
first = [r for r in ix.search("waiting periods", k=1)]
plain = ix.search("waiting periods", k=1, add_next=False)
check("page has several chunks", len(ix.chunks) >= 2, len(ix.chunks))
check("next chunk added to result", first and first[0]["chunk_id"].endswith("#0")
      and len(first[0]["text"]) > len(plain[0]["text"]), first)
lines = first[0]["text"].splitlines()
check("overlap not repeated", len(lines) == len(set(lines)), len(lines) - len(set(lines)))
check("chunks in index not modified", ix.chunks[0]["text"] == plain[0]["text"])

# --- Several queries (follow-ups) ---
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "pages.json"
    f.write_text(json.dumps(pages))
    ix = SearchIndex(f)
res = ix.search_many(["glasses", "dental claim"], [1, 2], add_next=False)
urls = [r["url"].rsplit("/", 1)[1] for r in res]
check("counts taken from each query in order", urls[0] == "optical" and "how-to-claim" in urls[1:]
      and len(res) == 3, urls)
ids = [r["chunk_id"] for r in ix.search_many(["dental claim", "dental claim"], [2, 2])]
check("no repeats across queries", len(ids) == len(set(ids)), ids)
check("repeats not counted", len(ids) == 2, ids)  # only 2 distinct texts match "dental claim"
check("one query same as search", [r["chunk_id"] for r in ix.search_many(["dental claim"], [3])]
      == [r["chunk_id"] for r in ix.search("dental claim", k=3)])

# Real data: the claim page must be retrieved for the dental claim question.
real = SearchIndex()
res = real.search("How do I make a dental claim?")
check("real: how-to-claim retrieved",
      any(r["url"].endswith("/health-insurance/how-to-claim") for r in res), [r["url"] for r in res])
check("real: no corporate-affiliate chunks", not any("corporate-affiliate" in c["url"] for c in real.chunks))

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
