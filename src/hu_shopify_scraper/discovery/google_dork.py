import re
from urllib.parse import quote_plus

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.utils.domain import extract_domain
from hu_shopify_scraper.utils.http import http

SHARED_QUERIES = [
    'site:myshopify.com Hungary',
    'site:myshopify.com Budapest',
    'site:.hu "Powered by Shopify"',
    'site:.hu "Shopify" "kosár"',
    'site:.hu "rendelés" Shopify',
    'site:.hu "/products.json"',
    '"myshopify.com" "Budapest"',
    '"myshopify.com" "Magyarország"',
    'inurl:"myshopify.com" Hungary',
    '"powered by Shopify" "forint"',
    '"powered by Shopify" "Ft"',
    'site:.hu "theme.scss" Shopify',
    'inurl:"/collections/all" site:.hu',
    'site:.hu "window.Shopify"',
]

BING_QUERIES = [
    'site:myshopify.com Hungary',
    'site:myshopify.com Budapest',
    'site:.hu Shopify store',
    'site:.hu "add to cart" Shopify',
    'site:.hu "/cart" Shopify',
    '"myshopify.com" "Debrecen"',
    '"myshopify.com" "Szeged"',
    'inurl:"myshopify.com" "Magyar"',
    'site:.hu "shopify" "webáruház"',
    'site:.hu "myshopify.com"',
    'site:.hu "cdn.shopify.com"',
    'site:.hu "/admin" Shopify',
    '"powered by Shopify" "Budapest"',
]


def _build_google_url(query: str, page: int) -> str:
    start = page * 10
    return (
        f"https://www.google.com/search?q={quote_plus(query)}"
        f"&start={start}&num=10&hl=en"
    )


def _build_bing_url(query: str, page: int) -> str:
    first = page * 10 + 1
    return (
        f"https://www.bing.com/search?q={quote_plus(query)}"
        f"&first={first}"
    )


def _extract_urls_from_html(html: str) -> list[str]:
    urls: list[str] = []
    pattern = re.compile(r'<a[^"]*href="(https?://[^"]+)"')
    for match in pattern.finditer(html):
        url = match.group(1)
        if (
            "google.com" not in url
            and "bing.com" not in url
            and "youtube.com" not in url
            and "pinterest" not in url
            and "facebook.com" not in url
            and "microsoft.com" not in url
        ):
            urls.append(url)
    return urls


async def search_google(query: str, pages: int) -> list[str]:
    domains: list[str] = []
    for page in range(pages):
        url = _build_google_url(query, page)
        response = await http.get(url)
        if response and response.status_code == 200:
            found_urls = _extract_urls_from_html(response.text)
            for found_url in found_urls:
                domain = extract_domain(found_url)
                if domain and domain not in domains:
                    domains.append(domain)
    return domains


async def search_bing(query: str, pages: int) -> list[str]:
    domains: list[str] = []
    headers = {
        "User-Agent": settings.user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    for page in range(pages):
        url = _build_bing_url(query, page)
        try:
            response = await http.client.get(url, headers=headers)
            if response and response.status_code == 200:
                found_urls = _extract_urls_from_html(response.text)
                for found_url in found_urls:
                    domain = extract_domain(found_url)
                    if domain and domain not in domains:
                        domains.append(domain)
        except Exception:
            continue
    return domains


async def discover_via_google() -> list[str]:
    all_domains: list[str] = []
    for query in SHARED_QUERIES:
        domains = await search_google(query, settings.google_dork_pages)
        all_domains.extend(domains)
    return list(dict.fromkeys(all_domains))


async def discover_via_bing() -> list[str]:
    all_domains: list[str] = []
    for query in BING_QUERIES:
        domains = await search_bing(query, settings.google_dork_pages)
        all_domains.extend(domains)
    return list(dict.fromkeys(all_domains))
