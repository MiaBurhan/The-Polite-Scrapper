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


def cache_path(page_number: int) -> Path:
    """Return the cache path for a catalogue page."""
    return CACHE_DIR / f"catalogue-page-{page_number}.html"


def fetch_page(url: str, page_number: int) -> bytes:
    """Fetch a page from the site and cache its HTML."""

    # This delay applies only to real network requests.
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

            content = response.read()

    except HTTPError as error:
        raise RuntimeError(
            f"Fetch failed: HTTP status {error.code}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"Fetch failed: {error.reason}"
        ) from error

    path = cache_path(page_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    print(f"FETCH page={page_number} bytes={len(content)}")
    return content


def load_page(url: str, page_number: int) -> bytes:
    """Load a catalogue page from cache or fetch it if necessary."""

    path = cache_path(page_number)

    if path.exists():
        content = path.read_bytes()
        print(f"CACHE HIT page={page_number} bytes={len(content)}")
        return content

    return fetch_page(url, page_number)


def discover_books_and_next(
    html: bytes,
    page_url: str,
) -> tuple[list[str], str | None]:
    """Extract book URLs and the catalogue's next-page URL."""

    soup = BeautifulSoup(html, "html.parser")

    book_urls = []

    for article in soup.select("article.product_pod"):
        link = article.select_one("h3 a")

        if link is None:
            continue

        href = link.get("href")

        if href:
            absolute_url = urljoin(page_url, href)
            book_urls.append(absolute_url)

    next_link = soup.select_one("li.next a")

    if next_link is None:
        next_url = None
    else:
        href = next_link.get("href")
        next_url = urljoin(page_url, href) if href else None

    return book_urls, next_url


def discover_catalogue() -> list[str]:
    """Discover books from the first three catalogue pages."""

    current_url = BASE_URL
    all_book_urls = []
    catalogue_pages = 0

    while catalogue_pages < 3:
        page_number = catalogue_pages + 1

        html = load_page(current_url, page_number)

        book_urls, next_url = discover_books_and_next(
            html,
            current_url,
        )

        all_book_urls.extend(book_urls)
        catalogue_pages += 1

        if catalogue_pages == 3:
            break

        if next_url is None:
            raise RuntimeError(
                f"Catalogue page {page_number} has no next link."
            )

        current_url = next_url

    unique_urls = list(dict.fromkeys(all_book_urls))

    print(f"catalogue_pages={catalogue_pages}")
    print(f"discovered={len(all_book_urls)}")
    print(f"unique_urls={len(unique_urls)}")

    return unique_urls


def main() -> None:
    """Discover book URLs from the first three catalogue pages."""
    discover_catalogue()


if __name__ == "__main__":
    main()

