from __future__ import annotations

import asyncio
import re
from typing import List, Optional

import httpx
from selectolax.parser import HTMLParser

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.utils.http import http
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

REVIEWS_URL = "https://apps.shopify.com/{slug}/reviews"
MAX_PAGES = 20

SLUGIFY_RE = re.compile(r"[^a-z0-9.]+")
DOMAIN_IN_NAME_RE = re.compile(r"([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z]{2,})", re.IGNORECASE)


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


def _parse_hungarian_merchants(html: str) -> List[str]:
    parser = HTMLParser(html)
    names: List[str] = []
    for review_div in parser.css("div[data-merchant-review]"):
        text = review_div.text() or ""
        if "Hungary" not in text:
            continue
        span = review_div.css_first("span[title]")
        if span:
            name = (span.attributes.get("title") or "").strip()
            if name:
                names.append(name)
    return names


def _merchant_to_candidate_domain(name: str) -> Optional[str]:
    name = name.strip()
    if not name:
        return None

    m = DOMAIN_IN_NAME_RE.search(name)
    if m:
        return m.group(1).lower()

    slug = SLUGIFY_RE.sub("", name.lower())
    if not slug:
        return None
    return f"{slug}.hu"


async def _probe_domain(domain: str) -> Optional[str]:
    url = f"https://{domain}"
    try:
        response = await http.head(url)
        if response is not None and response.status_code < 500:
            return domain
    except Exception:
        pass
    return None


async def discover_from_app_reviews(
    app_slugs: Optional[List[str]] = None,
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if app_slugs is None:
        app_slugs = settings.app_review_slugs
    if not app_slugs:
        return 0

    if repository is None:
        repository = Repository()
    repository.init_db()

    new_found = 0
    error_counter = [0]

    for app_slug in app_slugs:
        merchant_names: List[str] = []
        checked = 0

        if progress_callback:
            progress_callback(f"Fetching {app_slug}", 0, 1, 0, 0)

        for page_num in range(1, MAX_PAGES + 1):
            url = REVIEWS_URL.format(slug=app_slug)
            if page_num > 1:
                url += f"?page={page_num}"
            html = await _fetch_page(url)
            if html is None:
                break

            page_names = _parse_hungarian_merchants(html)
            if not page_names:
                break
            merchant_names.extend(page_names)
            checked += len(page_names)

            if progress_callback:
                progress_callback(
                    f"{app_slug} reviews",
                    page_num,
                    MAX_PAGES,
                    len(merchant_names),
                    0,
                )

            if len(page_names) < 10:
                break
            await asyncio.sleep(0.5)

        if not merchant_names:
            continue

        candidates: List[tuple[str, str]] = []
        seen: set[str] = set()
        for name in merchant_names:
            domain = _merchant_to_candidate_domain(name)
            if domain and domain not in seen:
                seen.add(domain)
                candidates.append((name, domain))

        if progress_callback:
            progress_callback(
                f"{app_slug} probing",
                0,
                len(candidates),
                0,
                0,
            )

        source_tag = f"review-{app_slug}"
        semaphore = asyncio.Semaphore(settings.max_concurrent)

        async def process_candidate(
            name: str, domain: str
        ) -> Optional[Store]:
            try:
                async with semaphore:
                    probed = await _probe_domain(domain)
                    if probed and not repository.store_exists(probed):
                        fp_result = await fingerprint_store(probed)
                        if fp_result.is_shopify:
                            meta = await extract_metadata(probed)
                            return Store(
                                domain=probed,
                                store_name=meta.get("store_name"),
                                currency=meta.get("currency"),
                                locale=meta.get("locale"),
                                email=meta.get("email"),
                                phone=meta.get("phone"),
                                description=meta.get("description"),
                                category=meta.get("category"),
                                myshopify_domain=fp_result.myshopify_domain,
                                is_verified=True,
                                source=source_tag,
                                discovered_by=source_tag,
                            )

                    if not repository.store_exists(
                        f"_lead_{domain}"
                    ):
                        return Store(
                            domain=f"_lead_{domain}",
                            merchant_name=name,
                            store_name=name,
                            is_verified=False,
                            needs_domain_resolution=True,
                            source=source_tag,
                            discovered_by=source_tag,
                        )
                    return None
            except Exception:
                error_counter[0] += 1
                return None

        batch_size = settings.hu_domain_batch_size
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i : i + batch_size]
            tasks = [
                process_candidate(name, domain) for name, domain in batch
            ]
            results = await asyncio.gather(*tasks)
            for store in results:
                if store:
                    repository.upsert_store(store)
                    if store.is_verified:
                        new_found += 1
            if progress_callback:
                progress_callback(
                    f"{app_slug} fingerprinting",
                    min(i + batch_size, len(candidates)),
                    len(candidates),
                    new_found,
                    error_counter[0],
                )

    repository.close()
    return new_found
