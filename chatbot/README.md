# Website chatbot (proof of concept)

A chatbot that answers visitors' questions using **only** the pages of one website,
with a link to the page each fact came from. It is set up for the Australian Unity
health insurance section (`https://www.australianunity.com.au/health-insurance`).

If the answer isn't on the website, it says *"I couldn't find that on the website"*
instead of guessing.

## How it works

```
crawler.py  ->  data/pages.json  ->  index.py  ->  answer.py  ->  server.py + static/chat.html
 (crawl)        (saved pages)       (search)      (Claude)        (chat page)
```

1. **Crawl** (`crawler.py`): visits every page under the start URL, keeps the main
   text (no menus, footers or cookie banners) and saves it to `data/pages.json`.
   Tables are saved one row per line, e.g. `Pregnancy and related services | 12 months`.
2. **Search** (`index.py`): splits pages into ~500-word chunks (tables are never split)
   and finds the best chunks for a question with keyword search (BM25). Each match also
   brings the next chunk of its page, so text cut at a chunk boundary isn't lost.
3. **Answer** (`answer.py`): sends the question and the top chunks to Claude, with rules
   to use only those sources, cite them as `[1]`, `[2]`, and never invent prices or
   waiting periods. Citations are turned into real links.
4. **Chat page** (`server.py`, `static/chat.html`): a small web page. It remembers the
   last 3 questions and answers so follow-ups like *"What about pregnancy?"* work.

## Setup

Needs Python 3.10 or newer and an Anthropic API key.

```bash
cd chatbot
pip install -r requirements.txt
cp .env.example .env        # then edit .env and paste your key
```

`.env` is git-ignored. Never commit your key.

## Use it

Ask one question from the terminal:

```bash
python answer.py "How do I make a dental claim?"
python answer.py "How do I make a dental claim?" --show-chunks   # also show what was retrieved
```

Run the chat page, then open http://localhost:5000:

```bash
python server.py
```

See which chunks a question retrieves (no API key needed):

```bash
python index.py "What is the waiting period for extras cover?"
```

## Refresh the website data

The saved pages go out of date as the website changes (offers end, prices change).
Re-crawl to refresh them. It takes about 10 minutes, waiting 1 second between pages:

```bash
python crawler.py
python crawler.py --max-pages 20     # quick test run
```

Then run `python test_retrieval.py` to check the search still finds the right pages,
and restart the server so it loads the new data.

## Tests

All run offline with no API key (Claude is replaced by a stub):

| File | What it checks |
|---|---|
| `test_crawler.py` | Text extraction: tables, repeated values, excluded URLs |
| `test_index.py` | Chunking, search, duplicate removal, follow-up searches |
| `test_retrieval.py` | 25 real questions (incl. follow-ups) find the right page and answer text in `data/pages.json` |
| `test_answer.py` | Prompt, citations, "not found", refusals, conversation history |
| `test_server.py` | The web API: input checks, history, errors |

```bash
python test_crawler.py
python test_index.py
python test_retrieval.py
python test_answer.py
python test_server.py
```

`test_retrieval.py` is the one to run after a re-crawl or any search change. When you
find a question the bot answers badly because it never saw the right page, add it there.
Questions keyword search is known to miss are listed in `KNOWN_GAPS`: they are still
reported but don't fail the check.

## Settings (`config.py`)

| Setting | What it does |
|---|---|
| `START_URL`, `MAX_PAGES`, `REQUEST_DELAY` | What to crawl and how politely |
| `REMOVE_CLASS_PATTERN` | Page widgets to strip (site-specific) |
| `EXCLUDE_URL_PATTERN` | URLs to leave out; here, the near-copy pages under `/corporate-affiliate/` |
| `CHUNK_WORDS`, `CHUNK_OVERLAP` | Chunk size |
| `TOP_K` | Chunks sent to Claude per question |
| `ADD_NEXT_CHUNK` | Also send the chunk after each match (about a third more text per question) |
| `MAX_HISTORY_TURNS`, `FOLLOW_UP_EXTRA` | How follow-up questions are handled |
| `COMPANY_NAME`, `MODEL`, `EFFORT`, `MAX_TOKENS` | Who the bot speaks for, and the Claude model settings |

To point the bot at another website, change `START_URL`, `COMPANY_NAME`,
`REMOVE_CLASS_PATTERN` and `EXCLUDE_URL_PATTERN`, re-crawl, and replace the questions in
`test_retrieval.py` with ones for the new site.

## Known limits

- **Keyword search** matches words, not meaning. *"How do I contact Australian Unity?"*
  doesn't find the contact page, because "contact" appears more often on other pages.
- **Saved data goes stale.** Answers are only as current as the last crawl.
- **Pages behind a login** (member account pages) can't be crawled.
- **General information only.** The bot is told not to give personal advice, but its
  answers should still be checked against the website.
