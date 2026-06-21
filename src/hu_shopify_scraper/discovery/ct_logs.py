import asyncio
import json
import random
from pathlib import Path
from typing import Optional

import httpx

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.utils.domain import is_myshopify_domain
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.hungarian import (
    check_hungarian_content,
    get_redirect_target,
    is_hu_domain,
)
from hu_shopify_scraper.verify.metadata import extract_metadata

CRTSH_URL = "https://crt.sh"

CACHE_FILE = settings.cache_dir / "crtsh_myshopify.json"


async def _fetch_crtsh_raw() -> str:
    url = f"{CRTSH_URL}/?q=%.myshopify.com&output=json&exclude=expired"
    retries = 3
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            headers = {"User-Agent": settings.user_agent}
            async with httpx.AsyncClient(
                timeout=settings.crtsh_timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
            if response.status_code == 503 and attempt < retries:
                delay = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            last_error = exc
            if attempt < retries:
                delay = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
    raise RuntimeError(
        f"Failed to fetch crt.sh after {retries} attempts: {last_error}"
    )


async def fetch_myshopify_domains(refresh: bool = False) -> list[str]:
    cache_file = Path(CACHE_FILE)
    if not refresh and cache_file.exists():
        raw = cache_file.read_text()
    else:
        raw = await _fetch_crtsh_raw()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(raw)

    records = json.loads(raw)
    domains: set[str] = set()
    for record in records:
        name_value = record.get("name_value", "")
        for name in name_value.split("\n"):
            name = name.strip().lower()
            if name and is_myshopify_domain(name):
                domains.add(name)
    return sorted(domains)


async def _probe_hu_redirect(
    myshopify_domain: str,
) -> Optional[str]:
    target = await get_redirect_target(myshopify_domain)
    if target and is_hu_domain(target):
        return target
    return None


async def _check_content_hu(myshopify_domain: str) -> dict:
    return await check_hungarian_content(myshopify_domain)


async def process_candidate(domain: str, source: str) -> Optional[Store]:
    fp_result = await fingerprint_store(domain)
    if not fp_result.is_shopify:
        return None

    meta = await extract_metadata(domain)
    myshopify = fp_result.myshopify_domain
    if not myshopify:
        myshopify = (
            domain
            if is_myshopify_domain(domain)
            else None
        )

    custom_domain = None
    store_domain = domain
    if not is_hu_domain(domain) and is_myshopify_domain(domain):
        redirect = await get_redirect_target(domain)
        if redirect and is_hu_domain(redirect):
            custom_domain = redirect
            store_domain = redirect

    return Store(
        domain=store_domain,
        store_name=meta.get("store_name"),
        currency=meta.get("currency"),
        locale=meta.get("locale"),
        email=meta.get("email"),
        phone=meta.get("phone"),
        description=meta.get("description"),
        category=meta.get("category"),
        myshopify_domain=myshopify,
        is_verified=True,
        source=source,
        custom_domain=custom_domain,
        discovered_by=source,
    )


async def discover_ct(
    refresh: bool = False,
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("ct_logs")
    checked = 0
    new_found = 0
    errors = 0

    myshopify_domains = await fetch_myshopify_domains(refresh=refresh)

    if progress_callback:
        progress_callback("Redirect probe", 0, len(myshopify_domains), 0, 0)

    semaphore = asyncio.Semaphore(settings.ct_probe_concurrency)

    async def rate_limited_probe(domain: str) -> Optional[tuple[str, str]]:
        try:
            async with semaphore:
                custom = await asyncio.wait_for(
                    _probe_hu_redirect(domain), timeout=5
                )
                if custom:
                    return (domain, custom)
                return None
        except (asyncio.TimeoutError, Exception):
            return None

    hu_redirects: dict[str, str] = {}
    batch_size = settings.hu_domain_batch_size
    for i in range(0, len(myshopify_domains), batch_size):
        batch = myshopify_domains[i : i + batch_size]
        tasks = [rate_limited_probe(d) for d in batch]
        batch_results = await asyncio.gather(*tasks)
        for r in batch_results:
            if r:
                md, custom_domain = r
                hu_redirects[md] = custom_domain
        if progress_callback:
            progress_callback(
                "Redirect probe",
                min(i + batch_size, len(myshopify_domains)),
                len(myshopify_domains),
                len(hu_redirects),
                0,
            )
    checked += len(myshopify_domains)

    needs_content_check = [
        d for d in myshopify_domains if d not in hu_redirects
    ]

    content_hu: set[str] = set()
    semaphore_content = asyncio.Semaphore(settings.max_concurrent)

    async def rate_limited_content(domain: str) -> Optional[str]:
        try:
            async with semaphore_content:
                result = await asyncio.wait_for(
                    _check_content_hu(domain), timeout=10
                )
                if result.get("is_hungarian"):
                    return domain
                return None
        except (asyncio.TimeoutError, Exception):
            return None

    if settings.ct_content_check and needs_content_check:
        for i in range(0, len(needs_content_check), batch_size):
            batch = needs_content_check[i : i + batch_size]
            tasks = [rate_limited_content(d) for d in batch]
            batch_results = await asyncio.gather(*tasks)
            for r in batch_results:
                if r:
                    content_hu.add(r)
            if progress_callback:
                progress_callback(
                    "Content check",
                    min(i + batch_size, len(needs_content_check)),
                    len(needs_content_check),
                    len(content_hu),
                    0,
                )

    candidates = set(hu_redirects.keys()) | content_hu

    for idx, myshopify_domain in enumerate(sorted(candidates)):
        store: Optional[Store] = None
        verify_domain = myshopify_domain
        try:
            custom_domain = hu_redirects.get(myshopify_domain)
            verify_domain = custom_domain or myshopify_domain

            if repository.store_exists(verify_domain):
                continue

            store = await process_candidate(verify_domain, "ct_logs")
            if store:
                repository.upsert_store(store)
                new_found += 1
        except Exception:
            errors += 1

        if progress_callback:
            progress_callback(
                "Verifying",
                idx + 1,
                len(candidates),
                new_found,
                errors,
            )

    repository.finish_run(
        run_id=run_id,
        domains_checked=checked,
        new_found=new_found,
        errors=errors,
    )
    repository.close()
    return new_found
