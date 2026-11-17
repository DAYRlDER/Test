"""Phase 2 - Chunking + BM25 keyword search.

Test which chunks a question retrieves:
    python index.py "Does extras cover dental?"
    python index.py "How do I claim?" --k 3 --full
"""
import argparse
import json
import re
from pathlib import Path

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


def _words(lines: list[str]) -> int:
    return sum(len(line.split()) for line in lines)


def _is_row(line: str) -> bool:
    return " | " in line  # the crawler writes table rows as "cell | cell"


def page_units(text: str, size: int) -> list[list[str]]:
    """Group a page's lines into units that should not be split across chunks.

    A table (its rows, short sub-headings between rows such as "Other extras",
    and a short caption line just above it such as "Dental") is one unit, so a
    row is never separated from the rest of its table. A table longer than
    `size` is split into row groups, each repeating the header row. Every other
    line is its own unit; very long lines are cut into `size`-word pieces.
    """
    lines = text.splitlines()
    units, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not _is_row(line):
            words = line.split()
            units.extend([" ".join(words[j:j + size])] for j in range(0, len(words), size))
            i += 1
            continue
        table = [line]
        i += 1
        while i < len(lines):
            if _is_row(lines[i]):
                table.append(lines[i])
            elif len(lines[i].split()) <= 4 and i + 1 < len(lines) and _is_row(lines[i + 1]):
                table.append(lines[i])  # sub-heading inside the table
            else:
                break
            i += 1
        if units and len(units[-1]) == 1 and len(units[-1][0].split()) <= 4:
            table.insert(0, units.pop()[0])  # caption just above the table
        if _words(table) <= size:
            units.append(table)
            continue
        header = next(r for r in table if _is_row(r))
        group = []
        for row in table:
            if group and _words(group) + len(row.split()) > size:
                units.append(group)
                group = [header]
            group.append(row)
        units.append(group)
    return units


def chunk_page(page: dict, size: int, overlap: int) -> list[dict]:
    """Split one page into ~`size`-word chunks built from whole lines, with ~`overlap` words repeated.

    Tables are kept whole (see page_units), so a chunk can run a little over `size`.
    """
    chunks, current, count = [], [], 0
    for unit in page_units(page["text"], size):
        n = _words(unit)
        if current and count + n > size:
            chunks.append(current)
            # Start the next chunk with the tail of this one (the overlap).
            tail, tail_count = [], 0
            for prev in reversed(current):
                tail_count += len(prev.split())
                if tail_count > overlap:
                    break
                tail.insert(0, prev)
            current, count = tail, _words(tail)
        current.extend(unit)
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
        pages = json.loads(Path(pages_file).read_text())
        if config.EXCLUDE_URL_PATTERN:  # also applies to data crawled before the rule existed
            pages = [p for p in pages if not re.search(config.EXCLUDE_URL_PATTERN, p["url"])]
        self.chunks = [c for p in pages
                       for c in chunk_page(p, config.CHUNK_WORDS, config.CHUNK_OVERLAP)]
        # Title is included so words in the page title help matching.
        self.bm25 = BM25Okapi([tokenize(c["title"] + " " + c["text"]) for c in self.chunks])
        self.page_count = len(pages)
        self.by_id = {c["chunk_id"]: c for c in self.chunks}

    def next_lines(self, chunk: dict) -> list[str]:
        """Lines of the chunk after `chunk` on the same page, minus the overlap they share."""
        url, _, n = chunk["chunk_id"].rpartition("#")
        nxt = self.by_id.get(f"{url}#{int(n) + 1}")
        if not nxt:
            return []
        cur, new = chunk["text"].splitlines(), nxt["text"].splitlines()
        shared = next((j for j in range(min(len(cur), len(new)), 0, -1) if cur[-j:] == new[:j]), 0)
        return new[shared:]

    def search(self, question: str, k: int = config.TOP_K,
               add_next: bool = config.ADD_NEXT_CHUNK) -> list[dict]:
        """Top `k` chunks for the question. With `add_next`, each result's text also
        includes the next chunk of its page, unless that chunk is itself a result."""
        return self.search_many([question], [k], add_next)

    def search_many(self, queries: list[str], counts: list[int],
                    add_next: bool = config.ADD_NEXT_CHUNK) -> list[dict]:
        """The top counts[0] chunks for queries[0], then up to counts[1] more for
        queries[1] (skipping chunks already picked), and so on."""
        results, seen = [], set()
        for query, count in zip(queries, counts):
            added = 0
            for r in self._search(query, len(results) + count):
                text = " ".join(r["text"].split())
                if added < count and r["chunk_id"] not in seen and text not in seen:
                    seen.update((r["chunk_id"], text))
                    results.append(r)
                    added += 1
        if add_next:
            picked = {r["chunk_id"] for r in results}
            for r in results:
                url, _, n = r["chunk_id"].rpartition("#")
                if f"{url}#{int(n) + 1}" not in picked:
                    extra = self.next_lines(r)
                    if extra:
                        r["text"] += "\n" + "\n".join(extra)
        return results

    def _search(self, question: str, k: int) -> list[dict]:
        tokens = tokenize(question)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        results, seen = [], set()
        for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True):
            if len(results) == k or scores[i] <= 0:
                break
            text = " ".join(self.chunks[i]["text"].split())
            if text in seen:  # same text on another page: keep only the best-ranked copy
                continue
            seen.add(text)
            results.append({**self.chunks[i], "score": float(scores[i])})
        return results


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
