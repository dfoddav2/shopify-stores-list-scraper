import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional

from hu_shopify_scraper.utils.http import http

SHOPIFY_JS_PATTERNS = [
    re.compile(r"window\.Shopify\s*="),
    re.compile(r"Shopify\.shop\s*="),
    re.compile(r"Shopify\.locale\s*="),
    re.compile(r"cdn\.shopify\.com"),
    re.compile(r"/cdn/shop/"),
    re.compile(r'myshopify\.com'),
]

SHOPIFY_ADMIN_PATH = "/admin"
SHOPIFY_PRODUCTS_JSON_PATH = "/products.json"
SHOPIFY_META_JSON_PATH = "/meta.json"
SHOPIFY_COLLECTIONS_JSON_PATH = "/collections.json"


@dataclass
class FingerprintResult:
    is_shopify: bool
    confidence: float = 0.0
    signals: list[str] = None
    myshopify_domain: Optional[str] = None
    status_code: Optional[int] = None

    def __post_init__(self):
        if self.signals is None:
            self.signals = []


async def check_products_json(domain: str) -> Optional[str]:
    url = f"https://{domain}/products.json"
    response = await http.get(url)
    if response and response.status_code == 200:
        try:
            data = response.json()
            if "products" in data:
                return "products.json"
        except (json.JSONDecodeError, ValueError):
            pass
    return None


async def check_admin_redirect(domain: str) -> Optional[str]:
    url = f"https://{domain}/admin"
    response = await http.head(url)
    if response:
        location = response.headers.get("location", "")
        if "/admin" in location and ("login" in location or "auth" in location):
            return "admin_redirect"
        if response.status_code in (301, 302, 303, 307, 308):
            return "admin_redirect"
    return None


async def check_admin_page(domain: str) -> Optional[str]:
    url = f"https://{domain}/admin"
    response = await http.get(url)
    if response and response.status_code == 200:
        html = response.text
        if "Shopify" in html and ("Login" in html or "log in" in html.lower()):
            return "admin_page"
    return None


async def check_meta_json(domain: str) -> Optional[str]:
    url = f"https://{domain}/meta.json"
    response = await http.get(url)
    if response and response.status_code == 200:
        try:
            data = response.json()
            if any(k in data for k in ("password", "currency", "locale", "myshopify_domain")):
                return "meta_json"
        except (json.JSONDecodeError, ValueError):
            pass
    return None


async def check_html_fingerprint(domain: str) -> Optional[str]:
    url = f"https://{domain}"
    response = await http.get(url)
    if response and response.status_code == 200:
        html = response.text
        signals_found = []
        for pattern in SHOPIFY_JS_PATTERNS:
            if pattern.search(html):
                signals_found.append(pattern.pattern)

        if signals_found:
            return "|".join(signals_found)

    return None


async def fingerprint_store(domain: str) -> FingerprintResult:
    names = [
        "products.json",
        "admin_redirect",
        "admin_page",
        "meta_json",
        "html_fingerprint",
    ]
    coros = [
        check_products_json(domain),
        check_admin_redirect(domain),
        check_admin_page(domain),
        check_meta_json(domain),
        check_html_fingerprint(domain),
    ]

    results = await asyncio.gather(*coros, return_exceptions=True)

    signals: list[str] = []
    myshopify_domain: Optional[str] = None
    status_code: Optional[int] = None

    for name, result in zip(names, results):
        if isinstance(result, Exception) or not result:
            continue
        signals.append(name)
        if name == "html_fingerprint" and result != name:
            myshopify_match = re.search(
                r"([^|]+\.myshopify\.com)", result
            )
            if myshopify_match:
                myshopify_domain = myshopify_match.group(1)

    confidence = len(signals) / len(names)

    return FingerprintResult(
        is_shopify=len(signals) >= 2 or "products.json" in signals,
        confidence=confidence,
        signals=signals,
        myshopify_domain=myshopify_domain,
        status_code=status_code,
    )
