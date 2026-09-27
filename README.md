# FlyRank Internship Polite Books The-Polite-Scrapper

## Project

This project is a small, polite Python The-Polite-Scrapper built for the FlyRank internship assignment.

### Target classification

**Target:** Books to Scrape : https://books.toscrape.com/

Books to Scrape is a sandbox website specifically intended for practicing web scraping. It provides book catalogue and product-detail pages in ordinary HTML, making it appropriate for this controlled scraping exercise.

The The-Polite-Scrapper only processes the first three catalogue pages.

I will not reuse this code on another site without checking its rules and terms first.

## What the The-Polite-Scrapper collects

For each book:

- title
- product URL
- raw price text
- normalized price in GBP
- availability text
- rating text
- description
- source catalogue page
- detail-page fetch timestamp

The final validated record schema is:

```
title: str
product_url: absolute URL
price_text: str
price_gbp: float
availability_text: str
rating_text: str
description: str | null
source_page: absolute URL
fetched_at: ISO-8601 timestamp
```

## Lane

**Python**

The The-Polite-Scrapper uses:

* Python standard library
* `requests`-style HTTP behavior through Python's standard `urllib`
* Beautiful Soup for HTML parsing
* Pydantic for record validation

## Installation

From the repository root:

```bash
python -m venv .venv
```

Activate the virtual environment.

### Windows

```bash
.venv\Scripts\activate
```

### macOS/Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install beautifulsoup4 pydantic
```

## Run

From the repository root, copy and paste:

```bash
python The-Polite-Scrapper/src/main.py
```

The The-Polite-Scrapper writes:

```
The-Polite-Scrapper/output/books.json
The-Polite-Scrapper/output/errors.json
The-Polite-Scrapper/output/run-report.json
```

The The-Polite-Scrapper is idempotent: rerunning it uses cached pages where available and does not append duplicate book records.

## Politeness rules

The The-Polite-Scrapper follows these rules:

* It identifies itself with an honest User-Agent.
* Network requests use a 5-second timeout.
* Real requests are separated by at least 0.5 seconds.
* Catalogue and detail pages are cached locally.
* Cached pages do not cause another network request.
* HTTP 5xx and network/timeout failures are retried once after a delay.
* HTTP 403 and 404 responses are not retried.
* Only the first three catalogue pages are followed.
* Book links are discovered from the site's catalogue pages rather than hardcoded.
* A failure on one book page does not stop the entire run.

## Evidence

A sample run is included in:

```text
The-Polite-Scrapper/output/books.json
The-Polite-Scrapper/output/run-report.json
```

The run report records the start time, duration, pages fetched, cache hits, valid records, invalid records, and failed pages.

### Sample run report

```json
  "start_time": "2026-09-27T01:14:07.005876Z",
  "duration_seconds": 7.603,
  "pages_fetched": 3,
  "cache_hits": 60,
  "valid_records": 60,
  "invalid_records": 0,
  "failed_pages": 0
```

The expected successful evidence is 60 valid book records discovered across three catalogue pages.

## Why no browser was needed

The data is already in the HTML the server sends, so a browser would only add cost.

## Honest limitation

This The-Polite-Scrapper intentionally covers only the first three catalogue pages and is designed for this assignment's controlled target; it is not a general-purpose The-Polite-Scrapper for arbitrary websites.

## Ethics

Use an official API when one exists. Never bypass logins, paywalls, or blocks. Collect only what you need for the stated purpose.

## Project structure

```text
The-Polite-Scrapper/
├── cache/
├── output/
│   ├── books.json
│   ├── errors.json
│   └── run-report.json
├── src/
│   └── main.py
├── .gitignore
├── README.md
└── requirements.txt
```


### 3. Get your real run report

Run:

```bash
python The-Polite-Scrapper/src/main.py
````

Then display it:

```bash
cat The-Polite-Scrapper/output/run-report.json
```

On Windows PowerShell:

```powershell
Get-Content The-Polite-Scrapper/output/run-report.json
```

Copy that JSON and replace:

```text
PASTE YOUR REAL run-report.json HERE
```

with the **actual output from your run**. Don't fabricate the numbers.

### 4. Check that cache isn't going to GitHub

Run:

```bash
git status --short
```

You should **not** see hundreds of `.html` files.

If `cache/` is already tracked from an earlier commit, `.gitignore` alone won't remove it from Git tracking. In that case:

```bash
git rm -r --cached The-Polite-Scrapper/cache
```

Then:

```bash
git status --short
```

The cache should disappear from the staged/tracked files while remaining on your computer.

### 5. Check the important evidence

Run:

```bash
python -c "import json; print('books:', len(json.load(open('The-Polite-Scrapper/output/books.json'))))"
```

Expected:

```text
books: 60
```

And:

```bash
python -c "import json; print(json.load(open('The-Polite-Scrapper/output/run-report.json')))"
```

You want the report to show your real run's values.

