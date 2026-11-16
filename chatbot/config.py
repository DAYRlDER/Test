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

# --- Files ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PAGES_FILE = DATA_DIR / "pages.json"
