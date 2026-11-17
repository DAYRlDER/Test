"""Phase 1 offline tests for text extraction - no network. Run: python test_crawler.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawler import extract  # noqa: E402

fails = 0


def check(name, cond, info=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else info)
    fails += not cond


HTML = """<html><body><main>
<h1>What is a waiting period?</h1>
<p>Get a quote today from <a href="/q">our team</a> online now.</p>
<table>
  <tr><th>Hospital cover benefit</th><th>Waiting periods</th></tr>
  <tr><td>Accidents and ambulance</td><td>No waiting period</td></tr>
  <tr><td>Pre-existing conditions</td><td rowspan="2">12 months</td></tr>
  <tr><td>Pregnancy and related services</td></tr>
</table>
<table>
  <tr><th colspan="2">Dental</th></tr>
  <tr><td>Preventative treatments</td><td>2 months</td></tr>
  <tr><td>General dental</td><td>2 months</td></tr>
  <tr><td>Major dental</td><td>12 months</td></tr>
</table>
<p>Get a quote today from <a href="/q">our team</a> online now.</p>
<p>Done</p><p>Done</p>
</main></body></html>"""

title, text, _ = extract(HTML)
lines = text.splitlines()
check("title", title == "What is a waiting period?", title)
check("table header row", "Hospital cover benefit | Waiting periods" in lines, lines)
check("row keeps its value", "Accidents and ambulance | No waiting period" in lines, lines)
check("rowspan filled", "Pre-existing conditions | 12 months" in lines
      and "Pregnancy and related services | 12 months" in lines, lines)
check("colspan merged", "Dental" in lines, lines)
check("repeated values kept", "Preventative treatments | 2 months" in lines
      and "General dental | 2 months" in lines and "Major dental | 12 months" in lines, lines)
check("long repeated line dropped", lines.count("Get a quote today from our team online now.") == 1, lines)
check("back-to-back repeat dropped", lines.count("Done") == 1, lines)

# Short values repeated outside tables (e.g. div-based grids) are kept too.
_, text, _ = extract("<main><div>Optical</div><div>6 months</div>"
                     "<div>Dental</div><div>6 months</div></main>")
check("short repeats kept outside tables", text.splitlines().count("6 months") == 2, text)

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
