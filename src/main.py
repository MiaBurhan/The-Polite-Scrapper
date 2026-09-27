from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl


# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

BASE_URL = "https://books.toscrape.com/catalogue/page-1.html"
SITE_ROOT = "https://books.toscrape.com/"
CATALOGUE_ROOT = "https://books.toscrape.com/catalogue/"

TIMEOUT = 5
REQUEST_DELAY = 0.5
RETRY_DELAY = 1.0

USER_AGENT = (
    "FlyRankInternship-A9/1.0 "
    "(+https://github.com/MiaBurhan/The-Polite-Scrapper)"
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "cache"
CATALOGUE_CACHE_DIR = CACHE_DIR / "catalogue"
DETAIL_CACHE_DIR = CACHE_DIR / "details"

OUTPUT_DIR = PROJECT_ROOT / "output"

BOOKS_FILE = OUTPUT_DIR / "books.json"
ERRORS_FILE = OUTPUT_DIR / "errors.json"
RUN_REPORT_FILE = OUTPUT_DIR / "run-report.json"

FETCH_TIMES_FILE = CACHE_DIR / "detail-fetch-times.json"


# ------------------------------------------------------------
# Data model
# ------------------------------------------------------------

class BookRecord(BaseModel):
    title: str
    product_url: HttpUrl
    price_text: str
    price_gbp: float
    availability_text: str
    rating_text: str
    description: str | None
    source_page: HttpUrl
    fetched_at: datetime


# ------------------------------------------------------------
# Run statistics
# ------------------------------------------------------------

@dataclass
class RunStats:
    pages_fetched: int = 0
    cache_hits: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    failed_pages: int = 0


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_directories() -> None:
    CATALOGUE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def cache_key_from_url(url: str) -> str:
    """
    Create a safe deterministic cache filename from a URL.
    """
    key = re.sub(r"[^A-Za-z0-9._-]", "_", url)
    return key


def catalogue_cache_path(page_number: int) -> Path:
    return CATALOGUE_CACHE_DIR / f"page-{page_number}.html"


def detail_cache_path(url: str) -> Path:
    """
    Extract the book slug from a URL such as:

    https://books.toscrape.com/catalogue/
    a-light-in-the-attic_1000/index.html

    and use:

    details/a-light-in-the-attic_1000.html
    """
    clean_url = url.rstrip("/")
    parts = clean_url.split("/")

    if len(parts) >= 2 and parts[-1] == "index.html":
        slug = parts[-2]
    else:
        slug = parts[-1]

    return DETAIL_CACHE_DIR / f"{slug}.html"


def load_fetch_times() -> dict[str, str]:
    if not FETCH_TIMES_FILE.exists():
        return {}

    try:
        return json.loads(FETCH_TIMES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_fetch_time(url: str, fetched_at: str) -> None:
    FETCH_TIMES_FILE.parent.mkdir(parents=True, exist_ok=True)

    fetch_times = load_fetch_times()
    fetch_times[url] = fetched_at

    FETCH_TIMES_FILE.write_text(
        json.dumps(fetch_times, indent=2, sort_keys=True),
        encoding="utf-8",
    )


# ------------------------------------------------------------
# Network fetching
# ------------------------------------------------------------

def fetch_network(
    url: str,
    stats: RunStats,
    retry: bool = True,
) -> tuple[str, str]:
    """
    Fetch a URL from the network.

    Retries exactly once for:
      - HTTP 5xx
      - timeout/network errors

    Does NOT retry:
      - 403
      - 404
    """

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            status = response.status

            if status != 200:
                raise RuntimeError(
                    f"Unexpected HTTP status {status} for {url}"
                )

            body = response.read()
            html = body.decode("utf-8", errors="replace")

            fetched_at = utc_now()

            stats.pages_fetched += 1

            print(f"FETCH {url} bytes={len(body)}")

            return html, fetched_at

    except HTTPError as exc:
        if exc.code in (403, 404):
            raise RuntimeError(
                f"HTTP {exc.code} for {url}"
            ) from exc

        if 500 <= exc.code <= 599 and retry:
            print(
                f"RETRY HTTP {exc.code} after {RETRY_DELAY}s: {url}"
            )
            time.sleep(RETRY_DELAY)
            return fetch_network(url, stats, retry=False)

        raise RuntimeError(
            f"HTTP {exc.code} for {url}"
        ) from exc

    except (TimeoutError, URLError) as exc:
        if retry:
            print(
                f"RETRY network error after {RETRY_DELAY}s: {url}"
            )
            time.sleep(RETRY_DELAY)
            return fetch_network(url, stats, retry=False)

        raise RuntimeError(
            f"Network error for {url}: {exc}"
        ) from exc


def load_catalogue_page(
    page_number: int,
    url: str,
    stats: RunStats,
) -> str:
    """
    Load catalogue page from cache when available.
    Otherwise fetch it.
    """

    cache_path = catalogue_cache_path(page_number)

    if cache_path.exists():
        stats.cache_hits += 1

        html = cache_path.read_text(encoding="utf-8")

        print(
            f"CACHE HIT catalogue_page={page_number} "
            f"bytes={len(html.encode('utf-8'))}"
        )

        return html

    html, _ = fetch_network(url, stats)

    cache_path.write_text(
        html,
        encoding="utf-8",
    )

    return html


def load_detail_page(
    url: str,
    stats: RunStats,
) -> tuple[str, str]:
    """
    Load a book detail page.

    If the cache exists AND has a trustworthy recorded fetch
    timestamp, use the cache.

    If the HTML exists but the timestamp is missing, treat the
    cache as stale and refetch rather than inventing a timestamp.
    """

    cache_path = detail_cache_path(url)

    if cache_path.exists():
        fetch_times = load_fetch_times()

        if url in fetch_times:
            stats.cache_hits += 1

            html = cache_path.read_text(
                encoding="utf-8"
            )

            return html, fetch_times[url]

        print(
            f"STALE CACHE detail={url} "
            f"reason=missing fetch timestamp"
        )

    # Respect the request delay for real network requests.
    time.sleep(REQUEST_DELAY)

    html, fetched_at = fetch_network(url, stats)

    cache_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache_path.write_text(
        html,
        encoding="utf-8",
    )

    save_fetch_time(
        url,
        fetched_at,
    )

    return html, fetched_at


# ------------------------------------------------------------
# Catalogue discovery
# ------------------------------------------------------------

def discover_books_and_next(
    html: str,
    page_url: str,
) -> tuple[list[str], str | None]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    book_urls: list[str] = []

    for link in soup.select(
        "article.product_pod h3 a"
    ):
        href = link.get("href")

        if not href:
            continue

        # Books to Scrape uses links such as:
        #
        # ../../../catalogue/a-light-in-the-attic_1000/index.html
        #
        # Strip the leading ../../../ and join against the
        # catalogue root. This prevents:
        #
        # /catalogue/catalogue/...
        #
        # from being generated.

        href = href.replace(
            "../../../",
            "",
            1,
        )

        book_url = CATALOGUE_ROOT + href

        book_urls.append(book_url)

    next_link = soup.select_one(
        "li.next a"
    )

    next_url = None

    if next_link:
        href = next_link.get("href")

        if href:
            next_url = urljoin_catalogue(
                page_url,
                href,
            )

    return book_urls, next_url


def urljoin_catalogue(
    current_url: str,
    href: str,
) -> str:
    """
    Small local URL joiner for catalogue pagination.

    Page URLs look like:

    /catalogue/page-1.html
    /catalogue/page-2.html
    /catalogue/page-3.html
    """

    if href.startswith("http://") or href.startswith("https://"):
        return href

    if href.startswith("/"):
        return SITE_ROOT.rstrip("/") + href

    # The site's next link is normally simply page-2.html.
    base = current_url.rsplit("/", 1)[0] + "/"

    return base + href


# ------------------------------------------------------------
# Detail extraction
# ------------------------------------------------------------

def extract_book(
    html: str,
    product_url: str,
    source_page: str,
    fetched_at: str,
) -> dict:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    product = soup.select_one(
        "div.product_main"
    )

    if product is None:
        raise ValueError(
            "Could not find product_main section"
        )

    title_element = product.select_one("h1")

    price_element = product.select_one(
        ".price_color"
    )

    availability_element = product.select_one(
        ".availability"
    )

    rating_element = product.select_one(
        ".star-rating"
    )

    if title_element is None:
        raise ValueError("Missing title")

    if price_element is None:
        raise ValueError("Missing price")

    if availability_element is None:
        raise ValueError("Missing availability")

    title = title_element.get_text(
        " ",
        strip=True,
    )

    price_text = price_element.get_text(
        " ",
        strip=True,
    )

    availability_text = availability_element.get_text(
        " ",
        strip=True,
    )

    rating_text = ""

    if rating_element is not None:
        classes = rating_element.get(
            "class",
            [],
        )

        rating_classes = [
            value
            for value in classes
            if value != "star-rating"
        ]

        rating_text = " ".join(
            rating_classes
        )

    description = None

    description_heading = soup.select_one(
        "#product_description"
    )

    if description_heading is not None:
        description_element = (
            description_heading.find_next_sibling("p")
        )

        if description_element is not None:
            description = description_element.get_text(
                " ",
                strip=True,
            )

    return {
        "title": title,
        "product_url": product_url,
        "price_text": price_text,
        "availability_text": availability_text,
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


# ------------------------------------------------------------
# Normalization
# ------------------------------------------------------------

def parse_price(price_text: str) -> float:
    """
    Convert:
        £51.77
    into:
        51.77
    """

    match = re.search(
        r"£\s*([0-9]+(?:\.[0-9]{1,2})?)",
        price_text,
    )

    if not match:
        raise ValueError(
            f"Could not parse GBP price: {price_text}"
        )

    return float(match.group(1))


def normalize_record(
    raw_record: dict,
) -> BookRecord:

    raw_record = dict(raw_record)

    raw_record["price_gbp"] = parse_price(
        raw_record["price_text"]
    )

    validated = BookRecord.model_validate(
        raw_record
    )

    return validated


# ------------------------------------------------------------
# Book processing
# ------------------------------------------------------------

def process_book(
    product_url: str,
    source_page: str,
    stats: RunStats,
    errors: list[dict],
) -> BookRecord | None:

    try:
        html, fetched_at = load_detail_page(
            product_url,
            stats,
        )

        raw_record = extract_book(
            html=html,
            product_url=product_url,
            source_page=source_page,
            fetched_at=fetched_at,
        )

        record = normalize_record(
            raw_record
        )

        stats.valid_records += 1

        return record

    except Exception as exc:
        stats.failed_pages += 1

        error_message = str(exc)

        print(
            f"ERROR: {product_url} - {error_message}"
        )

        errors.append(
            {
                "url": product_url,
                "error": error_message,
            }
        )

        return None


# ------------------------------------------------------------
# Fake failure test
# ------------------------------------------------------------

def add_test_failure(
    urls: list[tuple[str, str]]
) -> list[tuple[str, str]]:

    fake_url = (
        "https://books.toscrape.com/catalogue/"
        "this-book-does-not-exist_999999/index.html"
    )

    urls.append(
        (
            fake_url,
            "https://books.toscrape.com/catalogue/page-1.html",
        )
    )

    return urls


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

def write_json(
    path: Path,
    data,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_run_report(
    stats: RunStats,
    start_time: str,
    started_monotonic: float,
) -> None:

    duration = round(
        monotonic() - started_monotonic,
        3,
    )

    report = {
        "start_time": start_time,
        "duration_seconds": duration,
        "pages_fetched": stats.pages_fetched,
        "cache_hits": stats.cache_hits,
        "valid_records": stats.valid_records,
        "invalid_records": stats.invalid_records,
        "failed_pages": stats.failed_pages,
    }

    write_json(
        RUN_REPORT_FILE,
        report,
    )

    print("run-report.json written")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--test-failure",
        action="store_true",
        help="Add one fake URL to verify failure handling.",
    )

    args = parser.parse_args()

    ensure_directories()

    stats = RunStats()
    errors: list[dict] = []
    records: list[BookRecord] = []

    start_time = utc_now()
    started_monotonic = monotonic()

    try:

        # ----------------------------------------------------
        # Discover first three catalogue pages
        # ----------------------------------------------------

        catalogue_urls = [
            BASE_URL
        ]

        discovered_books: list[
            tuple[str, str]
        ] = []

        seen_catalogue_pages: set[str] = set()

        for page_number in range(1, 4):

            if not catalogue_urls:
                break

            page_url = catalogue_urls.pop(0)

            if page_url in seen_catalogue_pages:
                continue

            seen_catalogue_pages.add(
                page_url
            )

            html = load_catalogue_page(
                page_number=page_number,
                url=page_url,
                stats=stats,
            )

            book_urls, next_url = (
                discover_books_and_next(
                    html,
                    page_url,
                )
            )

            for product_url in book_urls:
                discovered_books.append(
                    (
                        product_url,
                        page_url,
                    )
                )

            if next_url and page_number < 3:
                catalogue_urls.append(
                    next_url
                )

        # ----------------------------------------------------
        # Deduplicate books by product URL
        # ----------------------------------------------------

        unique_books: list[
            tuple[str, str]
        ] = []

        seen_urls: set[str] = set()

        for product_url, source_page in discovered_books:

            if product_url in seen_urls:
                continue

            seen_urls.add(
                product_url
            )

            unique_books.append(
                (
                    product_url,
                    source_page,
                )
            )

        print(
            f"catalogue_pages={len(seen_catalogue_pages)}"
        )

        print(
            f"discovered={len(discovered_books)}"
        )

        print(
            f"unique_urls={len(unique_books)}"
        )

        # ----------------------------------------------------
        # Optional fake failure
        # ----------------------------------------------------

        if args.test_failure:
            unique_books = add_test_failure(
                unique_books
            )

        # ----------------------------------------------------
        # Process every book independently
        # ----------------------------------------------------

        for product_url, source_page in unique_books:

            record = process_book(
                product_url=product_url,
                source_page=source_page,
                stats=stats,
                errors=errors,
            )

            if record is not None:
                records.append(
                    record
                )

        # ----------------------------------------------------
        # Write successful records
        # ----------------------------------------------------

        books_json = [
            record.model_dump(
                mode="json"
            )
            for record in records
        ]

        write_json(
            BOOKS_FILE,
            books_json,
        )

        # ----------------------------------------------------
        # Write errors
        # ----------------------------------------------------

        write_json(
            ERRORS_FILE,
            errors,
        )

        # ----------------------------------------------------
        # Final counts
        # ----------------------------------------------------

        print(
            f"valid_records={stats.valid_records}"
        )

        print(
            f"invalid_records={stats.invalid_records}"
        )

        print(
            f"failed_pages={stats.failed_pages}"
        )

    finally:

        write_run_report(
            stats=stats,
            start_time=start_time,
            started_monotonic=started_monotonic,
        )


if __name__ == "__main__":
    main()