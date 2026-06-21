from __future__ import annotations

import asyncio
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from selectolax.parser import HTMLParser

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

SELLERCENTER_URL = (
    "https://sellercenter.io/research/shopify-top-stores-hungary"
)


async def fetch_sellercenter_domains() -> List[str]:
    headers = {"User-Agent": settings.user_agent}
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout, follow_redirects=True
        ) as client:
            response = await client.get(SELLERCENTER_URL, headers=headers)
        if response.status_code != 200:
            return []
    except (httpx.TimeoutException, httpx.HTTPError):
        return []

    parser = HTMLParser(response.text)
    domains: set[str] = set()

    for row in parser.css("div.row-item"):
        link = row.css_first("div.shop-name a[href]")
        if link is None:
            continue
        href = link.attributes.get("href") or ""
        if not href.startswith(("http://", "https://")):
            continue
        domain = urlparse(href).netloc.lower()
        if domain:
            domains.add(domain)

    return sorted(domains)


async def discover_sellercenter(
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("sellercenter")
    new_found = 0
    error_counter = [0]

    domains = await fetch_sellercenter_domains()
    if not domains:
        repository.finish_run(run_id, 0, 0, 0)
        repository.close()
        return 0

    if progress_callback:
        progress_callback(
            "Fingerprinting", 0, len(domains), 0, 0
        )

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
                    source="sellercenter",
                    discovered_by="sellercenter",
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
