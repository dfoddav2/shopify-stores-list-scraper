# Hungarian Shopify Store Scraper

Discover and verify Shopify stores in Hungary.

## Quick Start

```bash
# Install dependencies
uv sync

# Run all discovery strategies (crt.sh, Tranco, registry, seed, Google)
uv run hu-shopify discover --all --refresh

# Verify candidates and extract metadata
uv run hu-shopify verify

# List verified stores
uv run hu-shopify list

# Export to CSV/JSON
uv run hu-shopify export stores.csv
```

For direct search you may need to expose chrome debugger: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug`

## Commands

| Command    | Description                                                |
| ---------- | ---------------------------------------------------------- |
| `discover` | Find candidates via multiple strategies (see below)        |
| `verify`   | Check candidates for Shopify fingerprint, extract metadata |
| `list`     | Display stored stores (`--all` for unverified)             |
| `export`   | Export verified stores to CSV or JSON                      |
| `stats`    | Show database statistics                                   |

### Discover Options

| Flag            | Description                                          |
| --------------- | ---------------------------------------------------- |
| `--seed`        | Check 18 known Hungarian seed domains (default: on)  |
| `--google`      | Google dorking with 14 search queries (default: on)  |
| `--ct`          | **P0** — crt.sh certificate transparency logs        |
| `--tranco`      | **P1a** — Tranco top-1M `.hu` domains                |
| `--registry`    | **P1b** — `.hu` registry announcement list           |
| `--all`         | Run all five strategies                              |
| `--refresh`     | Re-download cached data (crt.sh JSON, Tranco zip)    |

## Discovery Strategies

### P0 — Certificate Transparency Logs (`--ct`)
Queries [crt.sh](https://crt.sh) for `%.myshopify.com` certificates. Returns ~30k–100k unique myshopify domains. Each is HEAD-probed for `.hu` redirects; remaining domains get a Hungarian content check (locale, HUF, keywords, cities, `.hu` emails). Response is cached to `data/cache/crtsh_myshopify.json`.

### P1a — Tranco Top Sites (`--tranco`)
Downloads the [Tranco](https://tranco-list.eu) top-1M list, filters for `.hu`-suffix domains, and fingerprints each one. Results are cached to `data/cache/tranco_top1m.csv.zip`.

### P1b — .hu Registry (`--registry`)
Scrapes the [.hu registry announcement page](https://info.domain.hu/varolista/en/abc.html) for newly registered `.hu` domains, skips "Private person" entries, and fingerprints the remainder.

### Seed List (`--seed`)
18 hardcoded domains known or suspected to be Hungarian Shopify stores.

### Google Dorking (`--google`)
14 search operators targeting `myshopify.com` subdomains and `.hu` domains.

## Hungarian Filtering (Signal Detection)

When probing domains from crt.sh, a Hungarian content check runs on domains that don't redirect to `.hu`:

- **Locale/HTML lang**: `hu` or `hu_HU`
- **Currency**: `HUF` or `Ft` in the page
- **Cities**: Budapest, Debrecen, Szeged, etc. in the text
- **Keywords**: kosár, rendelés, webáruház, forint, etc.
- **Email**: `@*.hu` addresses in the HTML

## Shopify Detection

A multi-signal fingerprint system checks for:

- `/products.json` endpoint (strongest single signal)
- `/admin` login redirect
- `/admin` login page content
- `meta.json` Shopify-specific fields
- HTML patterns: `window.Shopify`, `cdn.shopify.com`, `myshopify.com`

Two or more signals (or just `products.json`) = confirmed Shopify store.

## Project Structure

```
src/hu_shopify_scraper/
├── cli.py              # Click commands
├── config.py           # Env-based configuration
├── db/
│   ├── models.py       # Pydantic models (Store, ScrapeRun)
│   └── repository.py   # SQLite persistence with migration support
├── discovery/
│   ├── ct_logs.py      # P0 — crt.sh certificate transparency pipeline
│   ├── google_dork.py  # Google search operator queries
│   ├── hu_domains.py   # Seed domain probing
│   ├── hu_registry.py  # P1b — .hu registry announcement scraper
│   └── tranco.py       # P1a — Tranco top-1M .hu filter
├── verify/
│   ├── fingerprint.py  # 5-signal Shopify detection
│   ├── hungarian.py    # Hungarian content signal detection
│   └── metadata.py     # Store info extraction (name, currency, contact)
└── utils/
    ├── domain.py       # Domain extraction, normalization, validation
    └── http.py         # Async HTTP client with auto-loop-rebuild
```

## Configuration

Copy `.env.example` to `.env` and customize. Key options:

| Variable                  | Default                              | Description                        |
| ------------------------- | ------------------------------------ | ---------------------------------- |
| `HU_SHOPIFY_CONCURRENCY`  | `10`                                 | Max concurrent HTTP requests       |
| `HU_SHOPIFY_TIMEOUT`      | `15`                                 | Request timeout (seconds)          |
| `HU_SHOPIFY_PROXY_URL`    | —                                    | Optional HTTP proxy                |
| `CTRSH_TIMEOUT`           | `120`                                | crt.sh download timeout            |
| `CT_PROBE_CONCURRENCY`    | `50`                                 | Concurrent myshopify HEAD probes   |
| `TRANCO_MAX_DOMAINS`      | `0` (unlimited)                      | Limit Tranco `.hu` domains         |
| `HU_REGISTRY_SKIP_PRIVATE`| `true`                               | Skip private person entries        |
| `HU_SHOPIFY_CACHE_DIR`    | `data/cache`                         | Disk cache for downloads           |
