from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://books.toscrape.com/"
TIMEOUT = 5
USER_AGENT = "FlyRankInternship-A9/1.0 (+https://github.com/MiaBurhan/The-Polite-Scrapper)"

PROJECT_DIR = Path(__file__).resolve().parents[1]
CACHE_FILE = PROJECT_DIR / "cache" / "catalogue-page-1.html"


def fetch_and_cache() -> bytes:
    """Fetch the catalogue page once and save it to the local cache."""

    request = Request(
        URL,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            status_code = response.status

            # Check the status before processing the response body.
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

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_bytes(content)

    print(f"FETCH: {len(content)} bytes")
    return content


def load_page() -> bytes:
    """Load the catalogue page from cache, fetching only when necessary."""

    if CACHE_FILE.exists():
        content = CACHE_FILE.read_bytes()
        print(f"CACHE HIT: {len(content)} bytes")
        return content

    return fetch_and_cache()


def main() -> None:
    """Load catalogue page 1 from cache or fetch it once."""
    load_page()


if __name__ == "__main__":
    main()
