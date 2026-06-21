from __future__ import annotations

import asyncio
import re
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

BASE_URL = "https://onshopify.com"
COUNTRY_URL = f"{BASE_URL}/country-websites/HU"
MAX_PAGES = 10

H1_DOMAIN_RE = re.compile(r"Shopify store:\s*(\S+)", re.IGNORECASE)
SITE_HREF_RE = re.compile(r"^/website/shopify-site-\d+$")


async def _fetch_page(url: str) -> Optional[str]:
    headers = {"User-Agent": settings.user_agent}
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout, follow_redirects=True
        ) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
    except (httpx.TimeoutException, httpx.HTTPError):
        pass
    return None


def _extract_detail_hrefs(html: str) -> List[str]:
    parser = HTMLParser(html)
    hrefs: List[str] = []
    for a in parser.css("a[href]"):
        href = a.attributes.get("href") or ""
        if SITE_HREF_RE.match(href):
            full = urljoin(BASE_URL, href)
            if full not in hrefs:
                hrefs.append(full)
    return hrefs


def _extract_domain_from_detail(html: str) -> Optional[str]:
    parser = HTMLParser(html)
    h1 = parser.css_first("h1")
    if h1:
        m = H1_DOMAIN_RE.search(h1.text(strip=True))
        if m:
            return m.group(1).lower().rstrip("/")
    return None


async def fetch_onshopify_domains(
    progress_callback=None,
) -> List[str]:
    seen_hrefs: set[str] = set()
    detail_pages: List[str] = []

    for page_num in range(1, MAX_PAGES + 1):
        url = COUNTRY_URL if page_num == 1 else f"{COUNTRY_URL}/{page_num}"
        html = await _fetch_page(url)
        if html is None:
            break

        hrefs = _extract_detail_hrefs(html)
        new_hrefs = [h for h in hrefs if h not in seen_hrefs]
        if not new_hrefs:
            break
        seen_hrefs.update(new_hrefs)
        detail_pages.extend(new_hrefs)

        if progress_callback:
            progress_callback(
                "Fetching list",
                page_num,
                MAX_PAGES,
                len(seen_hrefs),
                0,
            )

    if not detail_pages:
        return []

    if progress_callback:
        progress_callback(
            "Extracting domains",
            0,
            len(detail_pages),
            0,
            0,
        )

    domains: list[str] = []
    semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def fetch_detail(url: str) -> Optional[str]:
        try:
            async with semaphore:
                html = await _fetch_page(url)
                if html:
                    return _extract_domain_from_detail(html)
        except Exception:
            pass
        return None

    batch_size = settings.hu_domain_batch_size
    for i in range(0, len(detail_pages), batch_size):
        batch = detail_pages[i : i + batch_size]
        tasks = [fetch_detail(url) for url in batch]
        results = await asyncio.gather(*tasks)
        for d in results:
            if d:
                domains.append(d)
        if progress_callback:
            progress_callback(
                "Extracting domains",
                min(i + batch_size, len(detail_pages)),
                len(detail_pages),
                len(domains),
                0,
            )

    return sorted(set(domains))


async def discover_onshopify(
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("onshopify")
    new_found = 0
    error_counter = [0]

    domains = await fetch_onshopify_domains(
        progress_callback=progress_callback,
    )
    if not domains:
        repository.finish_run(run_id, 0, 0, 0)
        repository.close()
        return 0

    semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def process_domain(domain: str) -> Optional[Store]:
        try:
            async with semaphore:
                if repository.store_exists(domain):
                    return None
                fp_result = await fingerprint_store(domain)
                if not fp_result.is_shopify:
                    return None
                meta = await extract_metadata(domain)
                return Store(
                    domain=domain,
                    store_name=meta.get("store_name"),
                    currency=meta.get("currency"),
                    locale=meta.get("locale"),
                    email=meta.get("email"),
                    phone=meta.get("phone"),
                    description=meta.get("description"),
                    category=meta.get("category"),
                    myshopify_domain=fp_result.myshopify_domain,
                    is_verified=True,
                    source="onshopify",
                    discovered_by="onshopify",
                )
        except Exception:
            error_counter[0] += 1
            return None

    batch_size = settings.hu_domain_batch_size
    for i in range(0, len(domains), batch_size):
        batch = domains[i : i + batch_size]
        tasks = [process_domain(d) for d in batch]
        results = await asyncio.gather(*tasks)
        for store in results:
            if store:
                repository.upsert_store(store)
                new_found += 1
        if progress_callback:
            progress_callback(
                "Fingerprinting",
                min(i + batch_size, len(domains)),
                len(domains),
                new_found,
                error_counter[0],
            )

    repository.finish_run(
        run_id=run_id,
        domains_checked=len(domains),
        new_found=new_found,
        errors=error_counter[0],
    )
    repository.close()
    return new_found
