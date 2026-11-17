"""Phase 2 - Chunking + BM25 keyword search.

Test which chunks a question retrieves:
    python index.py "Does extras cover dental?"
    python index.py "How do I claim?" --k 3 --full
"""
import argparse
import json
import re

from rank_bm25 import BM25Okapi

import config

# Common words that carry no meaning for search.
STOPWORDS = set("""
a about above after again all am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from
further had has have having he her here hers him his how i if in into is it its itself
just me more most my no nor not now of off on once only or other our ours out over own
same she should so some such than that the their theirs them then there these they this
those through to too under until up very was we were what when where which while who
whom why will with would you your yours
""".split())


def tokenize(text: str) -> list[str]:
    """Lowercase words, minus stopwords, with a light plural strip (claims -> claim)."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    out = []
    for w in words:
        if w in STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def chunk_page(page: dict, size: int, overlap: int) -> list[dict]:
    """Split one page into ~`size`-word chunks built from whole lines, with ~`overlap` words repeated."""
    # Break very long lines into word groups so no single line exceeds `size`.
    lines = []
    for line in page["text"].splitlines():
        words = line.split()
        for i in range(0, len(words), size):
            lines.append(" ".join(words[i:i + size]))

    chunks, current, count = [], [], 0
    for line in lines:
        n = len(line.split())
        if current and count + n > size:
            chunks.append(current)
            # Start the next chunk with the tail of this one (the overlap).
            tail, tail_count = [], 0
            for prev in reversed(current):
                tail_count += len(prev.split())
                if tail_count > overlap:
                    break
                tail.insert(0, prev)
            current, count = tail, sum(len(t.split()) for t in tail)
        current.append(line)
        count += n
    if current:
        chunks.append(current)

    return [
        {"url": page["url"], "title": page["title"], "chunk_id": f"{page['url']}#{i}",
         "text": "\n".join(c)}
        for i, c in enumerate(chunks)
    ]


class SearchIndex:
    def __init__(self, pages_file=config.PAGES_FILE):
        pages = json.loads(pages_file.read_text())
        self.chunks = [c for p in pages
                       for c in chunk_page(p, config.CHUNK_WORDS, config.CHUNK_OVERLAP)]
        # Title is included so words in the page title help matching.
        self.bm25 = BM25Okapi([tokenize(c["title"] + " " + c["text"]) for c in self.chunks])
        self.page_count = len(pages)

    def search(self, question: str, k: int = config.TOP_K) -> list[dict]:
        tokens = tokenize(question)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        best = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in best if scores[i] > 0]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Show which chunks a question retrieves.")
    ap.add_argument("question")
    ap.add_argument("--k", type=int, default=config.TOP_K)
    ap.add_argument("--full", action="store_true", help="print the whole chunk text")
    args = ap.parse_args()

    index = SearchIndex()
    print(f"Index: {index.page_count} pages -> {len(index.chunks)} chunks")
    print(f"Question tokens: {tokenize(args.question)}\n")
    results = index.search(args.question, args.k)
    if not results:
        print("No matching chunks.")
    for rank, r in enumerate(results, 1):
        print(f"#{rank}  score={r['score']:.2f}  {r['title']}")
        print(f"    {r['chunk_id']}")
        body = r["text"] if args.full else r["text"][:300].replace("\n", " | ") + " ..."
        print(f"    {body}\n")
