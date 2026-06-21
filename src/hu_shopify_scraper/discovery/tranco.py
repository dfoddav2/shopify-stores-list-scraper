import asyncio
import csv
import io
import zipfile
from pathlib import Path
from typing import Optional

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

CACHE_FILE = settings.cache_dir / "tranco_top1m.csv.zip"


async def download_tranco_list(refresh: bool = False) -> list[str]:
    cache_path = Path(CACHE_FILE)
    if not refresh and cache_path.exists():
        raw = cache_path.read_bytes()
    else:
        import httpx
        headers = {"User-Agent": settings.user_agent}
        async with httpx.AsyncClient(
            timeout=settings.request_timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                settings.tranco_list_url, headers=headers
            )
            response.raise_for_status()
            raw = response.content
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(raw)

    hu_domains: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            with zf.open(name) as f:
                text = f.read().decode("utf-8", errors="replace")
                reader = csv.reader(io.StringIO(text))
                for row in reader:
                    if len(row) >= 2:
                        domain = row[1].strip().lower()
                        if domain.endswith(".hu"):
                            hu_domains.append(domain)

    if settings.tranco_max_domains > 0:
        hu_domains = hu_domains[: settings.tranco_max_domains]

    return hu_domains


async def discover_tranco(
    refresh: bool = False,
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("tranco")
    new_found = 0
    errors = 0

    hu_domains = await download_tranco_list(refresh=refresh)
    semaphore = asyncio.Semaphore(settings.max_concurrent)
    error_counter = [0]

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
                    source="tranco",
                    discovered_by="tranco",
                )
        except Exception:
            error_counter[0] += 1
            return None

    batch_size = settings.hu_domain_batch_size
    for i in range(0, len(hu_domains), batch_size):
        batch = hu_domains[i : i + batch_size]
        tasks = [process_domain(d) for d in batch]
        results = await asyncio.gather(*tasks)
        for store in results:
            if store:
                repository.upsert_store(store)
                new_found += 1

        if progress_callback:
            progress_callback(
                "Fingerprinting",
                min(i + batch_size, len(hu_domains)),
                len(hu_domains),
                new_found,
                error_counter[0],
            )

    errors = error_counter[0]

    repository.finish_run(
        run_id=run_id,
        domains_checked=len(hu_domains),
        new_found=new_found,
        errors=errors,
    )
    repository.close()
    return new_found
