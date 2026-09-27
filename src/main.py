from datetime import datetime, timezone
import json
from pathlib import Path
import re
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from pydantic import BaseModel, HttpUrl, ValidationError


BASE_URL = "https://books.toscrape.com/"
TIMEOUT = 5
REQUEST_DELAY = 0.5
USER_AGENT = "FlyRankInternship-A9/1.0 (+https://github.com/MiaBurhan/The-Polite-Scrapper)"

PROJECT_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_DIR / "cache"
OUTPUT_DIR = PROJECT_DIR / "output"

FETCH_TIMES_FILE = CACHE_DIR / "detail-fetch-times.json"
BOOKS_FILE = OUTPUT_DIR / "books.json"
ERRORS_FILE = OUTPUT_DIR / "errors.json"


class BookRecord(BaseModel):
    """Schema for a validated normalized book record."""

    title: str
    product_url: HttpUrl
    price_text: str
    price_gbp: float
    availability_text: str
    rating_text: str
    description: str | None
    source_page: HttpUrl
    fetched_at: datetime


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

    return json.loads(
        FETCH_TIMES_FILE.read_text(encoding="utf-8")
    )


def save_fetch_times(fetch_times: dict[str, str]) -> None:
    """Persist detail-page fetch timestamps."""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    FETCH_TIMES_FILE.write_text(
        json.dumps(
            fetch_times,
            indent=2,
            sort_keys=True,
        ),
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


def load_catalogue_page(
    url: str,
    page_number: int,
) -> bytes:
    """Load a catalogue page from cache or fetch it."""

    path = cache_path(page_number)

    if path.exists():
        content = path.read_bytes()

        print(
            f"CACHE HIT catalogue_page={page_number} "
            f"bytes={len(content)}"
        )

        return content

    content = fetch_page(url)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    print(
        f"FETCH catalogue_page={page_number} "
        f"bytes={len(content)}"
    )

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
    """Discover books from the first three catalogue pages."""

    current_url = BASE_URL
    discovered: list[tuple[str, str]] = []

    for page_number in range(1, 4):
        html = load_catalogue_page(
            current_url,
            page_number,
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for article in soup.select(
            "article.product_pod"
        ):
            link = article.select_one(
                "h3 a"
            )

            if link is None:
                continue

            href = link.get("href")

            if href:
                product_url = urljoin(
                    current_url,
                    href,
                )

                discovered.append(
                    (
                        product_url,
                        current_url,
                    )
                )

        if page_number == 3:
            break

        next_link = soup.select_one(
            "li.next a"
        )

        if next_link is None:
            raise RuntimeError(
                f"Catalogue page {page_number} "
                "has no next link."
            )

        href = next_link.get("href")

        if not href:
            raise RuntimeError(
                f"Catalogue page {page_number} "
                "has an empty next link."
            )

        current_url = urljoin(
            current_url,
            href,
        )

    return discovered


def extract_raw_record(
    html: bytes,
    product_url: str,
    source_page: str,
    fetched_at: str,
) -> dict:
    """Extract the required raw fields."""

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    product = soup.select_one(
        "div.product_main"
    )

    if product is None:
        raise RuntimeError(
            f"Could not find product area: {product_url}"
        )

    title_element = product.select_one("h1")
    price_element = product.select_one(".price_color")
    availability_element = product.select_one(".availability")
    rating_element = product.select_one(".star-rating")

    if title_element is None:
        raise RuntimeError(
            f"Missing title: {product_url}"
        )

    if price_element is None:
        raise RuntimeError(
            f"Missing price: {product_url}"
        )

    if availability_element is None:
        raise RuntimeError(
            f"Missing availability: {product_url}"
        )

    if rating_element is None:
        raise RuntimeError(
            f"Missing rating: {product_url}"
        )

    description_element = soup.select_one(
        "#product_description + p"
    )

    description = (
        description_element.get_text(
            strip=True
        )
        if description_element is not None
        else None
    )

    rating_classes = rating_element.get(
        "class",
        [],
    )

    rating_text = next(
        (
            class_name
            for class_name in rating_classes
            if class_name != "star-rating"
        ),
        None,
    )

    return {
        "title": title_element.get_text(
            strip=True
        ),
        "product_url": product_url,
        "price_text": price_element.get_text(
            strip=True
        ),
        "availability_text": availability_element.get_text(
            " ",
            strip=True,
        ),
        "rating_text": rating_text,
        "description": description,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


def extract_all_records(
    discovered_books: list[tuple[str, str]],
) -> list[dict]:
    """Fetch, cache, and extract every unique book."""

    fetch_times = load_fetch_times()
    records = []

    unique_books: dict[str, str] = {}

    for product_url, source_page in discovered_books:
        unique_books.setdefault(
            product_url,
            source_page,
        )

    for product_url, source_page in unique_books.items():
        html, fetched_at = load_detail_page(
            product_url,
            fetch_times,
        )

        record = extract_raw_record(
            html,
            product_url,
            source_page,
            fetched_at,
        )

        records.append(record)

    return records


def parse_price(price_text: str) -> float:
    """Convert a pound price such as £51.77 into a float."""

    match = re.search(
        r"£\s*([0-9]+(?:\.[0-9]+)?)",
        price_text,
    )

    if match is None:
        raise ValueError(
            f"Could not parse price: {price_text!r}"
        )

    return float(match.group(1))


def normalize_record(raw_record: dict) -> dict:
    """Add normalized fields while preserving raw values."""

    normalized = dict(raw_record)

    normalized["price_gbp"] = parse_price(
        raw_record["price_text"]
    )

    return normalized


def validate_record(
    normalized_record: dict,
) -> BookRecord:
    """Validate a normalized record against the schema."""

    return BookRecord.model_validate(
        normalized_record
    )


def write_json(
    path: Path,
    data: object,
) -> None:
    """Write deterministic JSON output."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )


def process_records(
    raw_records: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Normalize and validate all raw records."""

    valid_records: dict[str, dict] = {}
    errors = []

    for raw_record in raw_records:
        product_url = raw_record.get(
            "product_url",
            "unknown",
        )

        try:
            normalized = normalize_record(
                raw_record
            )

            validated = validate_record(
                normalized
            )

            canonical_url = str(
                validated.product_url
            )

            valid_records.setdefault(
                canonical_url,
                validated.model_dump(mode="json"),
            )

        except (ValueError, ValidationError) as error:
            errors.append(
                {
                    "product_url": product_url,
                    "reason": str(error),
                }
            )

    return list(valid_records.values()), errors


def main() -> None:
    """Run the complete extraction and validation pipeline."""

    discovered_books = discover_catalogue()

    raw_records = extract_all_records(
        discovered_books
    )

    valid_records, errors = process_records(
        raw_records
    )

    write_json(
        BOOKS_FILE,
        valid_records,
    )

    write_json(
        ERRORS_FILE,
        errors,
    )

    if valid_records:
        print(
            json.dumps(
                valid_records[0],
                indent=2,
                ensure_ascii=False,
            )
        )

    print(f"valid_records={len(valid_records)}")
    print(f"errors={len(errors)}")


if __name__ == "__main__":
    main()

