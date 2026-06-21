from __future__ import annotations

import asyncio
import random
import re
from typing import Callable, List, Optional
from urllib.parse import quote_plus, unquote

from selectolax.parser import HTMLParser

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.utils.browser import browser
from hu_shopify_scraper.utils.domain import extract_domain
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

SEARCH_QUERY = '"Szolgáltató: Shopify"'
MAX_PAGES = 50

SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "google.hu",
    "bing.com",
    "duckduckgo.com",
    "youtube.com",
    "pinterest.com",
    "facebook.com",
    "microsoft.com",
    "msn.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "wikipedia.org",
    "shopify.com",
    "apps.shopify.com",
    "help.shopify.com",
}

URL_Q_RE = re.compile(r"[?&]q=([^&]+)")


def _build_google_url(query: str, page: int) -> str:
    start = page * 10
    return (
        f"https://www.google.com/search?q={quote_plus(query)}"
        f"&start={start}&num=10&hl=hu&gl=hu"
    )


def _unwrap_google_url(href: str) -> Optional[str]:
    if "/url?" in href or href.startswith("/url"):
        m = URL_Q_RE.search(href)
        if m:
            return unquote(m.group(1))
    if href.startswith("https://www.google.com/url"):
        m = URL_Q_RE.search(href)
        if m:
            return unquote(m.group(1))
    return None


def _extract_result_domains(html: str) -> List[str]:
    parser = HTMLParser(html)
    domains: List[str] = []
    seen: set[str] = set()

    for a in parser.css("a[href]"):
        href = a.attributes.get("href") or ""
        if not href:
            continue

        url: Optional[str] = None

        unwrapped = _unwrap_google_url(href)
        url = unwrapped if unwrapped else href

        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            continue

        domain = extract_domain(url)
        if not domain:
            continue

        if domain in seen:
            continue

        skip = False
        for se_domain in SEARCH_ENGINE_DOMAINS:
            if domain == se_domain or domain.endswith("." + se_domain):
                skip = True
                break
        if skip:
            continue

        seen.add(domain)
        domains.append(domain)

    return domains


async def search_and_collect(
    progress_callback: Optional[Callable] = None,
) -> List[str]:
    all_domains: List[str] = []
    seen: set[str] = set()

    for page in range(MAX_PAGES):
        url = _build_google_url(SEARCH_QUERY, page)

        html = await browser.fetch_page(url, timeout=20, wait_for_captcha=120)
        if html is None:
            if progress_callback:
                progress_callback(
                    f"google page {page+1}", page, page,
                    len(all_domains), 1,
                )
            continue

        page_domains = _extract_result_domains(html)

        if not page_domains:
            if progress_callback:
                progress_callback(
                    f"done ({page+1} pages)",
                    page + 1, page + 1, len(all_domains), 0,
                )
            break

        new_count = 0
        for d in page_domains:
            if d not in seen:
                seen.add(d)
                all_domains.append(d)
                new_count += 1

        if progress_callback:
            progress_callback(
                f"p{page+1} ({new_count} new)",
                page + 1, page + 1, len(all_domains), 0,
            )

        await asyncio.sleep(random.uniform(3.0, 5.0))

    return all_domains


async def discover_direct_search(
    repository: Optional[Repository] = None,
    progress_callback: Optional[Callable] = None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("direct_search")
    new_found = 0
    error_counter = [0]

    candidate_domains: List[str] = []
    seen: set[str] = set()

    engine_domains = await search_and_collect(
        progress_callback=progress_callback
    )
    for d in engine_domains:
        if d not in seen:
            seen.add(d)
            candidate_domains.append(d)

    if not candidate_domains:
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
                    source="direct_search",
                    discovered_by="direct_search",
                )
        except Exception:
            error_counter[0] += 1
            return None

    batch_size = settings.hu_domain_batch_size
    for i in range(0, len(candidate_domains), batch_size):
        batch = candidate_domains[i : i + batch_size]
        tasks = [process_domain(d) for d in batch]
        results = await asyncio.gather(*tasks)
        for store in results:
            if store:
                repository.upsert_store(store)
                new_found += 1
        if progress_callback:
            progress_callback(
                "Fingerprinting",
                min(i + batch_size, len(candidate_domains)),
                len(candidate_domains),
                new_found,
                error_counter[0],
            )

    repository.finish_run(
        run_id=run_id,
        domains_checked=len(candidate_domains),
        new_found=new_found,
        errors=error_counter[0],
    )
    repository.close()
    return new_found
