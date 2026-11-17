"""Phase 4 offline tests - no API key needed (Claude is stubbed). Run: python test_server.py"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

fails = 0


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else info)
    fails += not cond


class FakeClient:
    def __init__(self, text):
        self.beta = NS(messages=NS(create=lambda **kw: NS(
            stop_reason="end_turn", content=[NS(type="text", text=text)])))


c = server.app.test_client()

r = c.get("/")
check("chat page served", r.status_code == 200 and b"api/chat" in r.data)
r = c.get("/api/health")
check("health", r.status_code == 200 and r.json["chunks"] > 0, r.json)

server._client = FakeClient("You can claim on the spot [1].")
r = c.post("/api/chat", json={"question": "How do I claim for dental?"})
check("answer ok", r.status_code == 200 and r.json["answer"] == "You can claim on the spot [1]."
      and len(r.json["sources"]) == 1 and not r.json["not_found"], r.json)
check("no chunks leaked", "chunks" not in r.json)

for body, name in [({}, "missing"), ({"question": "   "}, "blank"), ({"question": 5}, "non-string"),
                   ({"question": "x" * 501}, "too long")]:
    r = c.post("/api/chat", json=body)
    check(f"rejects {name} question", r.status_code == 400 and "error" in r.json, r.json)
# Follow-up history
calls = []
orig_answer = server.answer
server.answer = lambda q, ix, cl, h: calls.append(h) or orig_answer(q, ix, cl, h)
hist = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(5)]
r = c.post("/api/chat", json={"question": "And optical?", "history": hist})
check("history accepted", r.status_code == 200, r.json)
check("history trimmed to last 3", calls and [t["question"] for t in calls[-1]] == ["q2", "q3", "q4"], calls)
r = c.post("/api/chat", json={"question": "x", "history": [{"question": " ", "answer": "a"}]})
check("blank history turns dropped", r.status_code == 200 and calls[-1] == [], calls[-1])
r = c.post("/api/chat", json={"question": "x", "history": [{"question": "q", "answer": "y" * 9000}]})
check("long answers cut", r.status_code == 200 and len(calls[-1][0]["answer"]) == 3000)
for bad, name in [("text", "string"), ([{"question": 1, "answer": "a"}], "non-string turn"),
                  (["x"], "non-dict turn"), ({"question": "q"}, "dict")]:
    r = c.post("/api/chat", json={"question": "x", "history": bad})
    check(f"rejects {name} history", r.status_code == 400 and "history" in r.json["error"], r.json)
r = c.post("/api/chat", json={"question": "x"})
check("no history ok", r.status_code == 200 and calls[-1] == [])
server.answer = orig_answer

r = c.post("/api/chat", data="not json", content_type="text/plain")
check("rejects non-JSON", r.status_code == 400)

# No API key -> friendly 503, not a crash.
server._client = None
orig = server.get_client
server.get_client = lambda: (_ for _ in ()).throw(SystemExit("no key"))
r = c.post("/api/chat", json={"question": "dental"})
check("no key -> 503", r.status_code == 503 and "API key" in r.json["error"], r.json)
server.get_client = orig

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
