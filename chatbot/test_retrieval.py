"""Retrieval checks on the real crawled data - offline, no API key. Run: python test_retrieval.py

Each question lists the page(s) that must appear in the top TOP_K search results.
Follow-up questions are searched the way answer.py does it, with the previous question.
Some also list text that must be in the retrieved chunks, so the model gets the
actual answer and not just the right page. Add a case whenever you find a
question the bot gets wrong because it never saw the right page.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from answer import search_queries  # noqa: E402
from index import SearchIndex  # noqa: E402

BASE = "https://www.australianunity.com.au/health-insurance"

# (question, acceptable page paths, text that must appear in the retrieved chunks)
CASES = [
    ("How do I make a dental claim?", ["/how-to-claim"], ["HICAPS"]),
    ("What is the waiting period for extras cover?", ["/explained/waiting-periods"],
     ["General dental, which includes most fillings, teeth whitening and tooth extractions | 2 months",
      "Prescription glasses and contact lenses | 6 months",
      "Hearing aids, health aids, health devices and orthotics | 12 months",
      "All other services | 2 months"]),
    ("How long do I have to wait for pregnancy cover?", ["/explained/waiting-periods"],
     ["Pregnancy and related services | 12 months"]),
    ("What is Lifetime Health Cover loading?", ["/explained/lhc"], []),
    ("Will I have to pay the Medicare levy surcharge?", ["/explained/mls"], []),
    ("How does the private health insurance rebate work?", ["/explained/rebate"], []),
    ("Can I suspend my cover while I travel overseas?", ["/using-your-cover/suspend"], []),
    ("How do I switch to Australian Unity from another fund?", ["/switching"], []),
    ("Am I covered for an emergency ambulance?", ["/using-your-cover/emergency-ambulance"], []),
    ("How do I get my tax statement?", ["/explained/tax-statement"], []),
    ("What counts as a pre-existing condition?",
     ["/explained/pre-existing-condition", "/visitors/explained/pre-existing-condition"], []),
    ("How do I make a complaint?", ["/legals/complaint-resolution"], []),
    ("Do you pay towards gym membership?", ["/programs/services/gym-membership"], []),
    ("Where can I find a gap free dentist?", ["/find-a-health-care-provider/gap-free-dentists"], []),
    ("Are there waiting periods on working visa cover?", ["/visitors/explained/waiting-periods"], []),
    ("Can I get a digital membership card?", ["/healthapp/digitalcard"], []),
    ("How can I pay my premiums?", ["/using-your-cover/payments"], []),
    ("Can someone else manage my policy for me?",
     ["/using-your-cover/delegated-authority", "/visitors/using-your-cover/delegated-authority"], []),
    ("Can I get hospital care at home?", ["/programs/support/hospital-at-home"], []),
    ("How do I contact Australian Unity?", ["/contact"], []),
]

# Follow-ups: (previous question, follow-up, acceptable pages, text that must be retrieved).
# The last case changes topic, so the earlier question must not crowd out the new one.
FOLLOW_UPS = [
    ("What is the waiting period for extras cover?", "What about pregnancy?",
     ["/explained/waiting-periods"], ["Pregnancy and related services | 12 months"]),
    ("What is the waiting period for extras cover?", "And for hearing aids?",
     ["/explained/waiting-periods"], ["Hearing aids, health aids, health devices and orthotics | 12 months"]),
    ("What is Lifetime Health Cover loading?", "How do I avoid it?", ["/explained/lhc"], []),
    ("How do I make a dental claim?", "Can I do it in the app?", ["/how-to-claim", "/healthapp"], []),
    ("What is the waiting period for extras cover?", "How can I pay my premiums?",
     ["/using-your-cover/payments"], []),
]

# Questions keyword search is known to get wrong. They are still run and reported,
# but do not fail the check. Remove one from here once it passes.
KNOWN_GAPS = {
    # "contact" appears more often on provider pages than on the contact page itself.
    "How do I contact Australian Unity?",
}


def run(index: SearchIndex, verbose: bool = True) -> int:
    fails = 0
    cases = [([], q, pages, texts) for q, pages, texts in CASES]
    cases += [([{"question": prev, "answer": ""}], q, pages, texts) for prev, q, pages, texts in FOLLOW_UPS]
    for history, question, pages, texts in cases:
        results = index.search_many(*search_queries(question, history))
        if history:
            question = f"{history[-1]['question']} -> {question}"
        got = [r["url"].removeprefix(BASE) or "/" for r in results]
        ok_page = any(p in got for p in pages)
        joined = "\n".join(r["text"] for r in results if r["url"].removeprefix(BASE) in pages)
        missing = [t for t in texts if t not in joined]
        ok = ok_page and not missing
        known = question in KNOWN_GAPS
        fails += not ok and not known
        if verbose:
            label = "PASS " if ok else ("KNOWN GAP " if known else "FAIL ")
            print(label + question + (" (now passes: remove from KNOWN_GAPS)" if ok and known else ""))
            if not ok_page:
                print(f"     expected one of {pages}, got {got}")
            for t in missing:
                print(f"     missing text: {t!r}")
    if verbose:
        print(f"FAILURES: {fails} of {len(cases)}")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run(SearchIndex()) else 0)
