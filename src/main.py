from datetime import datetime, timezone
import json
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


BASE_URL = "https://books.toscrape.com/"
TIMEOUT = 5
REQUEST_DELAY = 0.5
USER_AGENT = "FlyRankInternship-A9/1.0 (+https://github.com/MiaBurhan/The-Polite-Scrapper)"

PROJECT_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_DIR / "cache"
FETCH_TIMES_FILE = CACHE_DIR / "detail-fetch-times.json"


def cache_path(page_number: int) -> Path:
    """Return the cache path for a catalogue page."""
    return CACHE_DIR / f"catalogue-page-{page_number}.html"


def detail_cache_path(product_url: str) -> Path:
    """Create a stable cache filename from the product URL."""
    filename = product_url.rstrip("/").split("/")[-2]
    return CACHE_DIR / "details" / f"{filename}.html"


def load_fetch_times() -> dict[str, str]:
    """Load persisted detail-page fetch timestamps."""
    if not FETCH_TIMES_FILE.exists():
        return {}

    return json.loads(FETCH_TIMES_FILE.read_text(encoding="utf-8"))


def save_fetch_times(fetch_times: dict[str, str]) -> None:
    """Persist detail-page fetch timestamps."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    FETCH_TIMES_FILE.write_text(
        json.dumps(fetch_times, indent=2),
        encoding="utf-8",
    )


def fetch_page(url: str) -> bytes:
    """Fetch a page from the site with the required politeness."""

    sleep(REQUEST_DELAY)

    request = Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            status_code = response.status

            if status_code != 200:
                raise RuntimeError(
                    f"Fetch failed: HTTP status {status_code}"
                )

            return response.read()

    except HTTPError as error:
        raise RuntimeError(
            f"Fetch failed: HTTP status {error.code}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Fetch failed: {error.reason}"
        ) from error


def load_catalogue_page(url: str, page_number: int) -> bytes:
    """Load a catalogue page from cache or fetch it."""

    path = cache_path(page_number)

    if path.exists():
        content = path.read_bytes()
        print(f"CACHE HIT catalogue_page={page_number} bytes={len(content)}")
        return content

    content = fetch_page(url)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    print(f"FETCH catalogue_page={page_number} bytes={len(content)}")

    return content


def load_detail_page(
    product_url: str,
    fetch_times: dict[str, str],
) -> tuple[bytes, str]:
    """Load a book detail page from cache or fetch it."""

    path = detail_cache_path(product_url)

    if path.exists():
        content = path.read_bytes()

        fetched_at = fetch_times.get(product_url)

        if fetched_at is None:
            raise RuntimeError(
                f"Missing fetch timestamp for cached page: {product_url}"
            )

        return content, fetched_at

    content = fetch_page(product_url)

    fetched_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    fetch_times[product_url] = fetched_at
    save_fetch_times(fetch_times)

    return content, fetched_at


def discover_catalogue() -> list[tuple[str, str]]:
    """
    Discover books from the first three catalogue pages.

    Returns:
        A list of (product_url, source_page) tuples.
    """

    current_url = BASE_URL
    discovered: list[tuple[str, str]] = []

    for page_number in range(1, 4):
        html = load_catalogue_page(current_url, page_number)
        soup = BeautifulSoup(html, "html.parser")

        for article in soup.select("article.product_pod"):
            link = article.select_one("h3 a")

            if link is None:
                continue

            href = link.get("href")

            if href:
                product_url = urljoin(current_url, href)
                discovered.append((product_url, current_url))

        if page_number == 3:
            break

        next_link = soup.select_one("li.next a")

        if next_link is None:
            raise RuntimeError(
                f"Catalogue page {page_number} has no next link."
            )

        href = next_link.get("href")

        if not href:
            raise RuntimeError(
                f"Catalogue page {page_number} has an empty next link."
            )

        current_url = urljoin(current_url, href)

    return discovered


def extract_raw_record(
    html: bytes,
    product_url: str,
    source_page: str,
    fetched_at: str,
) -> dict:
    """Extract the required raw fields from a book detail page."""

    soup = BeautifulSoup(html, "html.parser")

    # Restrict selectors to the product area.
    product = soup.select_one("div.product_main")

    if product is None:
        raise RuntimeError(
            f"Could not find product area: {product_url}"
        )

    title_element = product.select_one("h1")
    price_element = product.select_one(".price_color")
    availability_element = product.select_one(".availability")
    rating_element = product.select_one(".star-rating")

    if title_element is None:
        raise RuntimeError(f"Missing title: {product_url}")

    if price_element is None:
        raise RuntimeError(f"Missing price: {product_url}")

    if availability_element is None:
        raise RuntimeError(f"Missing availability: {product_url}")

    if rating_element is None:
        raise RuntimeError(f"Missing rating: {product_url}")

    # Product description is outside product_main, but is still targeted
    # specifically through its Product Description heading.
    description_element = soup.select_one("#product_description + p")

    description = (
        description_element.get_text(strip=True)
        if description_element is not None
        else None
    )

    rating_classes = rating_element.get("class", [])
    rating_text = next(
        (
            class_name
            for class_name in rating_classes
            if class_name != "star-rating"
        ),
        None,
    )

    return {
        "title": title_element.get_text(strip=True),
        "product_url": product_url,
        "price_text": price_element.get_text(strip=True),
        "availability_text": availability_element.get_text(" ", strip=True),
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


def extract_all_records(
    discovered_books: list[tuple[str, str]],
) -> list[dict]:
    """Fetch, cache, and extract every discovered book."""

    fetch_times = load_fetch_times()
    records = []

    unique_urls = list(dict.fromkeys(
        product_url for product_url, _ in discovered_books
    ))

    source_pages = {}

    for product_url, source_page in discovered_books:
        source_pages.setdefault(product_url, source_page)

    for product_url in unique_urls:
        html, fetched_at = load_detail_page(
            product_url,
            fetch_times,
        )

        record = extract_raw_record(
            html,
            product_url,
            source_pages[product_url],
            fetched_at,
        )

        records.append(record)

    return records


def main() -> None:
    """Discover and extract all book detail records."""

    discovered_books = discover_catalogue()

    records = extract_all_records(discovered_books)

    if records:
        print(json.dumps(records[0], indent=2, ensure_ascii=False))

    print(f"detail_pages={len(records)}")


if __name__ == "__main__":
    main()

