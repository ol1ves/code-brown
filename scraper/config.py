"""Static config for the Grailed scraper."""

from __future__ import annotations

import os

LIVE_CAP = 40
SOLD_CAP_PER_LIVE = 40
MAX_CONCURRENCY = 2
REQUEST_DELAY_RANGE = (1.0, 2.0)  # seconds, uniform jitter
REQUEST_TIMEOUT_SEC = 20.0

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.grailed.com/",
}

GRAILED_BASE_URL = "https://www.grailed.com/"

BROWSER_HEADERS_HTML = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

BROWSER_HEADERS_JSON = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": "https://www.grailed.com/",
}

ALGOLIA_APP_ID = "MNRWEFSS2Q"
ALGOLIA_SEARCH_URL = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/*/queries"
ALGOLIA_LIVE_INDEX = "Listing_production"
ALGOLIA_SOLD_INDEX = "Listing_sold_production"


def get_algolia_api_key() -> str:
    """Read the Algolia key from the current process environment."""
    return os.environ.get("ALGOLIA_API_KEY", "").strip()


def get_algolia_headers() -> dict[str, str]:
    """Build Algolia headers at call time to avoid import-order issues."""
    return {
        "Content-Type": "application/json",
        "X-Algolia-API-Key": get_algolia_api_key(),
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
    }
ALGOLIA_FACETS = [
    "badges",
    "category",
    "category_path",
    "category_size",
    "condition",
    "department",
    "designers.name",
    "location",
    "price_i",
    "strata",
]

DEPARTMENT_VALUES = ["menswear", "womenswear"]
CATEGORY_VALUES = [
    "tops",
    "bottoms",
    "outerwear",
    "footwear",
    "accessories",
    "tailoring",
    "womens_tops",
    "womens_bottoms",
    "womens_outerwear",
    "womens_footwear",
    "womens_dresses",
    "womens_accessories",
    "womens_bags_luggage",
    "womens_jewelry",
]
CONDITION_VALUES = [
    "is_new",
    "is_gently_used",
    "is_used",
    "is_worn",
    "is_not_specified",
]
LOCATION_VALUES = [
    "United States",
    "Europe",
    "Asia",
    "Canada",
    "United Kingdom",
    "Australia/NZ",
    "Other",
]
STRATA_VALUES = ["basic", "grailed", "hype", "sartorial"]
