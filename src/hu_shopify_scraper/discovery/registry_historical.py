from __future__ import annotations

import asyncio
import json
import random
from typing import List, Optional

import httpx

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.discovery.hu_registry import parse_registry_html
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_ARCHIVE_URL = "https://web.archive.org/web/{timestamp}/https://info.domain.hu/varolista/en/abc.html"
MAX_SNAPSHOTS = 30


async def _fetch_json(url: str) -> Optional[str]:
    headers = {"User-Agent": settings.user_agent}
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(
                timeout=settings.crtsh_timeout, follow_redirects=True
            ) as client:
                response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            if response.status_code in (503, 504) and attempt < 3:
                await asyncio.sleep(2 ** attempt + random.uniform(0, 2))
                continue
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPError):
            if attempt < 3:
                await asyncio.sleep(2 ** attempt + random.uniform(0, 2))
    return None


async def _fetch_archived_page(
    timestamp: str,
) -> Optional[str]:
    url = WAYBACK_ARCHIVE_URL.format(timestamp=timestamp)
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


async def fetch_snapshot_timestamps() -> List[str]:
    url = (
        f"{WAYBACK_CDX_URL}?url=info.domain.hu/varolista/en/abc.html"
        f"&output=json&fl=timestamp&limit={MAX_SNAPSHOTS}"
    )
    raw = await _fetch_json(url)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [row[0] for row in data if isinstance(row, list) and row[0] != "timestamp"]


async def fetch_historical_registry_domains(
    progress_callback=None,
) -> List[str]:
    timestamps = await fetch_snapshot_timestamps()
    if not timestamps:
        return []

    all_domains: set[str] = set()
    total = len(timestamps)

    for idx, ts in enumerate(timestamps):
        html = await _fetch_archived_page(ts)
        if html is None:
            if progress_callback:
                progress_callback(
                    "Fetching snapshots",
                    idx + 1,
                    total,
                    len(all_domains),
                    0,
                )
            continue

        page_domains = parse_registry_html(html)
        all_domains.update(page_domains)

        if progress_callback:
            progress_callback(
                "Fetching snapshots",
                idx + 1,
                total,
                len(all_domains),
                0,
            )

        await asyncio.sleep(0.5)

    return sorted(all_domains)


async def discover_registry_historical(
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("registry_historical")
    new_found = 0
    error_counter = [0]

    domains = await fetch_historical_registry_domains(
        progress_callback=progress_callback,
    )
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
                    source="registry_historical",
                    discovered_by="registry_historical",
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
