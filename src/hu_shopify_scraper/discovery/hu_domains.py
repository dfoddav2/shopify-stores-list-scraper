import asyncio
from typing import Optional

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.verify.fingerprint import fingerprint_store

HUNGARIAN_KEYWORDS = [
    "Budapest", "Debrecen", "Szeged", "Pécs", "Győr",
    "Magyarország", "magyar", "forint", "HUF",
    "rendelés", "házhozszállítás", "kosár", "bolt",
    "webshop", "áruház", "vásárlás",
]

SEED_DOMAINS: list[str] = [
    "shop.biotechusa.hu",
    "peppi.hu",
    "lelosi.hu",
    "happykoala.hu",
    "showme.hu",
    "bio-barat.hu",
    "jateksziget.hu",
    "euro-markt.hu",
    "sneakcenter.com",
    "thevrshop.hu",
    "huppanjbele.hu",
    "hairbursthu.myshopify.com",
    "mobilfox.hu",
    "remootio.com",
    "grasshoppergeography.com",
    "true-to-sole.com",
    "fashionrerun.com",
]


async def probe_domain(domain: str) -> tuple[str, bool]:
    result = await fingerprint_store(domain)
    return domain, result.is_shopify


async def discover_from_seed_list() -> list[str]:
    semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def rate_limited_probe(domain: str) -> tuple[str, bool]:
        async with semaphore:
            return await probe_domain(domain)

    found: list[str] = []
    tasks = [rate_limited_probe(d) for d in SEED_DOMAINS]
    results = await asyncio.gather(*tasks)
    for domain, is_shopify in results:
        if is_shopify and domain not in found:
            found.append(domain)
    return found


async def discover_hu_with_hungarian_content() -> list[str]:
    found: list[str] = []
    semaphore = asyncio.Semaphore(settings.max_concurrent)

    async def check_domain(domain: str) -> Optional[str]:
        async with semaphore:
            result = await fingerprint_store(domain)
            if result.is_shopify:
                return domain
            return None

    from hu_shopify_scraper.discovery.google_dork import discover_via_google

    candidates = await discover_via_google()
    tasks = [check_domain(d) for d in candidates]
    results = await asyncio.gather(*tasks)
    for r in results:
        if r and r not in found:
            found.append(r)
    return found
