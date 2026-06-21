import re
from typing import Optional
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

from hu_shopify_scraper.utils.http import http

HU_CITIES = {
    "budapest", "debrecen", "szeged", "miskolc", "pecs", "győr",
    "nyíregyháza", "kecskemét", "székesfehérvár", "szombathely",
    "veszprém", "zalaegerszeg", "sopron", "eger", "nagykanizsa",
    "dunaújváros", "baja", "mosonmagyaróvár", "esztergom",
    "hatvan", "komárom", "kaposvár", "salgótarján", "szekszárd",
    "ajka", "gödöllő", "szentendre", "pápa", "gyöngyös",
    "tatabánya", "békéscsaba", "váci", "jászberény",
    "kazincbarcika", "balatonfüred", "siófok",
    "hajdúszoboszló", "dunaföldvár", "karcag",
    "szigetszentmiklós", "budakalász", "budakeszi",
    "pilisvörösvár", "veresegyház", "gyál",
    "szigethalom", "vecsés", "dabas",
    "törökbálint", "biatorbágy", "solymár",
    "százhalombatta", "üllo",
}

HU_KEYWORDS = {
    "kosár", "rendelés", "szállítás", "vásárlás", "akció",
    "webáruház", "forint", "árfolyam", "kedvezmény",
    "házhoz szállítás", "utánvét", "bankkártya",
    "magyarország", "magyarországi", "rendelésed",
    "vásárló", "bejelentkezés", "regisztráció",
    "kapcsolat", "rólunk", "adatvédelem", "sütik",
    "gyakori kérdések", "vélemények", "értékelések",
}

REDIRECT_DOMAIN_PATTERN = re.compile(
    r"https?://([^\s/\"'<>]+)"
)


async def get_redirect_target(domain: str) -> Optional[str]:
    url = f"https://{domain}"
    response = await http.head(url)
    if response is None:
        return None
    location = response.headers.get("location", "")
    if location:
        target = urlparse(location).netloc.lower()
        if target:
            return target
    return None


def is_hu_domain(domain: str) -> bool:
    return domain.endswith(".hu")


async def check_hungarian_content(domain: str) -> dict:
    result = {
        "is_hungarian": False,
        "confidence": 0.0,
        "signals": [],
    }
    url = f"https://{domain}"
    response = await http.get(url)
    if response is None or response.status_code != 200:
        return result

    html = response.text
    parser = HTMLParser(html)

    signals_found = []

    # 1. Check locale/lang
    locale = None
    html_tag = parser.css_first("html")
    if html_tag:
        locale = html_tag.attributes.get("lang", "")
    if locale and locale.lower().startswith("hu"):
        signals_found.append("locale_hu")

    meta_locale = _meta_content(parser, "locale")
    if meta_locale and meta_locale.lower().startswith("hu"):
        if "locale_hu" not in signals_found:
            signals_found.append("locale_hu")

    # 2. Check for HUF currency
    huf_pattern = re.compile(r'\bHUF\b')
    ft_pattern = re.compile(r'\b(\d[\d\s.,]*\s*Ft|Ft\s*\d)\b')
    if huf_pattern.search(html) or ft_pattern.search(html):
        signals_found.append("currency_huf")

    # 3. Check for Hungarian cities
    html_lower = html.lower()
    found_cities = []
    for city in HU_CITIES:
        if city in html_lower:
            found_cities.append(city)
    if found_cities:
        signals_found.append("hungarian_cities")

    # 4. Check for Hungarian keywords
    found_keywords = []
    for kw in HU_KEYWORDS:
        if kw in html_lower:
            found_keywords.append(kw)
    if found_keywords:
        signals_found.append("hungarian_keywords")

    # 5. Check for .hu email addresses
    email_pattern = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.hu\b'
    )
    if email_pattern.search(html):
        signals_found.append("hu_email")

    result["signals"] = signals_found
    total_checks = 5
    result["confidence"] = len(signals_found) / total_checks
    has_core = "locale_hu" in signals_found or "currency_huf" in signals_found
    result["is_hungarian"] = has_core and len(signals_found) >= 2

    return result


def _meta_content(parser: HTMLParser, name: str) -> Optional[str]:
    node = parser.css_first(
        f'meta[name="{name}"], meta[property="og:{name}"]'
    )
    if node:
        content = node.attributes.get("content")
        if content:
            return content.strip()
    return None
