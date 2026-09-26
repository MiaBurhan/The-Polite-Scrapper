# Polite Scraper

## Target classification

### Target

**Books to Scrape** — https://books.toscrape.com/

### Why this site?

Books to Scrape is part of ToScrape, a web scraping sandbox specifically created for people to practise web scraping and for developers to test scraping technologies. The site describes the Books section as a fictional bookstore that wants to be scraped and as a safe place for beginners learning web scraping.

### Scope

This scraper will collect data from **the first 3 catalogue pages only**.

It will not crawl the entire catalogue or follow links beyond the defined three-page scope.

### Data collected

The scraper will collect the book information required by the internship assignment from those three catalogue pages.

### Robots.txt

I requested:

`https://books.toscrape.com/robots.txt`

The server returned **404 Not Found**.

Therefore, there was **no robots file found**.

A missing robots.txt file is not treated as permission to scrape other websites. The target is appropriate here because Books to Scrape is explicitly provided as a scraping sandbox for learning and testing.

I will not reuse this code on another site without checking its rules and terms first.
