import asyncio
from typing import Optional

from selectolax.parser import HTMLParser

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository
from hu_shopify_scraper.utils.http import http
from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata

PRIVATE_PERSON_TAGS = {
    "private person",
    "magánszemély",
    "privatperson",
    "personne physique",
    "persona física",
    "persona fisica",
}


async def fetch_registry_domains() -> list[str]:
    response = await http.get(settings.hu_registry_url)
    if response is None or response.status_code != 200:
        return []
    return parse_registry_html(response.text)


def parse_registry_html(html: str) -> list[str]:
    parser = HTMLParser(html)
    domains: list[str] = []

    for table in parser.css("table"):
        rows = table.css("tr")
        headers = [
            th.text(strip=True).lower() for th in rows[0].css("th")
        ] if rows else []

        if not headers:
            continue

        domain_idx = _find_column_index(headers, "domain")
        applicant_idx = _find_column_index(headers, "applicant")

        if domain_idx is None:
            continue

        for row in rows[1:]:
            cells = row.css("td")
            if domain_idx >= len(cells):
                continue

            domain = cells[domain_idx].text(strip=True).lower()
            if not domain.endswith(".hu"):
                continue

            if settings.hu_registry_skip_private and applicant_idx is not None:
                if applicant_idx < len(cells):
                    applicant = cells[applicant_idx].text(strip=True).lower()
                    if applicant in PRIVATE_PERSON_TAGS:
                        continue

            domains.append(domain)

    return domains


def _find_column_index(
    headers: list[str], target: str
) -> Optional[int]:
    for i, h in enumerate(headers):
        if target in h:
            return i
    return None


async def discover_registry(
    repository: Optional[Repository] = None,
    progress_callback=None,
) -> int:
    if repository is None:
        repository = Repository()
    repository.init_db()

    run_id = repository.start_run("registry")
    new_found = 0
    errors = 0

    domains = await fetch_registry_domains()
    if not domains:
        repository.finish_run(run_id, 0, 0, 0)
        repository.close()
        return 0

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
                    source="registry",
                    discovered_by="registry",
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

    errors = error_counter[0]
    repository.finish_run(
        run_id=run_id,
        domains_checked=len(domains),
        new_found=new_found,
        errors=errors,
    )
    repository.close()
    return new_found
