"""Phase 3 offline tests - no API key needed (Claude is stubbed). Run: python test_answer.py"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from types import SimpleNamespace as NS
import answer as A
from index import SearchIndex

class FakeIndex:
    def __init__(self, chunks): self.chunks = chunks
    def search(self, q, k): return self.chunks[:k]

def ch(i, url): return {"title": f"T{i}", "url": url, "text": f"text {i}", "chunk_id": f"{url}#{i}", "score": 1.0}

class FakeClient:
    def __init__(self, text, stop="end_turn"):
        self.text, self.stop, self.kwargs = text, stop, None
        self.beta = NS(messages=NS(create=self.create))
    def create(self, **kw):
        self.kwargs = kw
        return NS(stop_reason=self.stop, content=[NS(type="thinking", thinking=""), NS(type="text", text=self.text)])

chunks = [ch(1, "u/a"), ch(2, "u/b"), ch(3, "u/a"), ch(4, "u/c"), ch(5, "u/d")]
fails = 0
def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else info); fails += not cond

# 1. remap: [4] -> first-cited url u/c becomes [1]; [1] and [3] same url u/a -> [2]; [1][3] dedupe
r = A.answer("q", FakeIndex(chunks), FakeClient("Dental is covered [4]. Waiting periods apply [1][3]."))
check("remap+dedupe", r["answer"] == "Dental is covered [1]. Waiting periods apply [2].", r["answer"])
check("sources order", [s["url"] for s in r["sources"]] == ["u/c", "u/a"], r["sources"])
# 2. invalid citation dropped & spacing tidied
r = A.answer("q", FakeIndex(chunks), FakeClient("Fact [9]. Other [2]."))
check("invalid dropped", r["answer"] == "Fact. Other [1].", r["answer"])
# 3. not found (curly apostrophe)
r = A.answer("q", FakeIndex(chunks), FakeClient("I couldn’t find that on the website. Please contact Australian Unity."))
check("not_found", r["not_found"] and r["sources"] == [], r)
# 4. refusal
r = A.answer("q", FakeIndex(chunks), FakeClient("", stop="refusal"))
check("refusal", r["not_found"] and "can't help" in r["answer"], r)
# 5. no chunks -> no API call
fc = FakeClient("x"); r = A.answer("", FakeIndex([]), fc)
check("empty retrieval skips API", r["not_found"] and fc.kwargs is None)
# 6. request shape
fc = FakeClient("ok [1]"); A.answer("q", FakeIndex(chunks), fc); kw = fc.kwargs
check("request params", kw["model"] == "claude-sonnet-5-5" and kw["fallbacks"] == "default"
      and kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["output_config"] == {"effort": "low"}, kw)
check("prompt has 5 sources", kw["messages"][0]["content"].count("<source id=") == 5)
# 7. [0] citation
r = A.answer("q", FakeIndex(chunks), FakeClient("Bad [0]. Good [2]."))
check("[0] dropped", r["answer"] == "Bad. Good [1].", r["answer"])
# 8. real index search with TOP_K
real = SearchIndex(); res = real.search("How do I claim for dental?", 5)
check("real index returns 5", len(res) == 5)
# 9. title with quote breaks the XML attribute?
p = A.build_prompt("q", [{"title": 'Say "hi"', "url": "u", "text": "t"}])
check("title quotes escaped", 'title="Say "hi""' not in p, p[:80])
print("FAILURES:", fails)
sys.exit(1 if fails else 0)
