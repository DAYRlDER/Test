"""All settings in one place. Change START_URL to point the bot at a different site section."""
from pathlib import Path

# --- Crawl settings ---
START_URL = "https://www.australianunity.com.au/health-insurance"
MAX_PAGES = 200            # stop after saving this many pages
REQUEST_DELAY = 1.0        # seconds between requests (be polite)
REQUEST_TIMEOUT = 15       # seconds
USER_AGENT = "WebsiteChatbotPOC/0.1 (learning project; polite crawler)"
MIN_TEXT_WORDS = 30        # pages with less text than this are skipped as "empty"
# Site-specific widgets to strip (regex on element id/class). These are the
# quote-calculator boxes on Australian Unity product pages. Set to "" for other sites.
REMOVE_CLASS_PATTERN = r"lhc-form|price-box"
# URLs to leave out (regex on the URL), used by the crawler and the index.
# Australian Unity has near-copies of its pages for each employer scheme under
# /corporate-affiliate/; they crowd out the original pages in search results.
# Set to "" for other sites.
EXCLUDE_URL_PATTERN = r"/corporate-affiliate(/|$)"

# --- Files ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PAGES_FILE = DATA_DIR / "pages.json"

# --- Index / retrieval ---
CHUNK_WORDS = 500          # target words per chunk
CHUNK_OVERLAP = 100        # words repeated between neighbouring chunks
TOP_K = 5                  # chunks returned per question

# --- Answering with Claude ---
COMPANY_NAME = "Australian Unity"
MODEL = "claude-sonnet-5-5"   # latest Sonnet (checked against the Claude API docs, Nov 2026)
EFFORT = "low"                # how hard the model thinks: low is fast/cheap and fine for short answers
MAX_TOKENS = 2000

# --- Web server (Phase 4) ---
MAX_QUESTION_CHARS = 500   # longer questions are rejected
