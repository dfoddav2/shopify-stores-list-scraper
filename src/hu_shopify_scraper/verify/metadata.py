import json
import re
from typing import Optional

from selectolax.parser import HTMLParser

from hu_shopify_scraper.utils.http import http


def extract_meta_content(parser: HTMLParser, name: str) -> Optional[str]:
    node = parser.css_first(f'meta[name="{name}"], meta[property="og:{name}"]')
    if node:
        content = node.attributes.get("content")
        if content:
            return content.strip()
    return None


def extract_json_ld(html: str) -> Optional[dict]:
    pattern = re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
            if isinstance(data, list) and data:
                return data[0]
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def extract_social_links(parser: HTMLParser) -> dict[str, str]:
    social = {}
    for link in parser.css("a[href]"):
        href = (link.attributes.get("href") or "").lower()
        if "facebook.com/" in href and "facebook.com/sharer" not in href:
            social["facebook"] = href
        elif "instagram.com/" in href:
            social["instagram"] = href
        elif "tiktok.com/@" in href:
            social["tiktok"] = href
        elif "youtube.com/@" in href or "youtube.com/channel/" in href:
            social["youtube"] = href
    return social


def extract_email(parser: HTMLParser) -> Optional[str]:
    for link in parser.css("a[href^='mailto:']"):
        href = link.attributes.get("href") or ""
        email = href.replace("mailto:", "").split("?")[0].strip()
        if email and "@" in email:
            return email
    return None


def extract_phone(parser: HTMLParser) -> Optional[str]:
    phone_pattern = re.compile(
        r"(\+?[\d\s\-().]{7,20})", re.IGNORECASE
    )
    for link in parser.css("a[href^='tel:']"):
        href = link.attributes.get("href") or ""
        phone = href.replace("tel:", "").strip()
        if phone:
            return phone
    for tag in parser.css("body"):
        text = tag.text(separator=" ")
        matches = phone_pattern.findall(text)
        for m in matches:
            digits = re.sub(r"\D", "", m)
            if 7 <= len(digits) <= 15:
                return m.strip()
    return None


async def extract_metadata(domain: str) -> dict:
    url = f"https://{domain}"
    response = await http.get(url)
    if not response or response.status_code != 200:
        return {}

    html = response.text
    parser = HTMLParser(html)

    store_name = extract_meta_content(parser, "title")
    if not store_name:
        title_tag = parser.css_first("title")
        if title_tag:
            store_name = title_tag.text(strip=True)

    description = extract_meta_content(parser, "description")
    locale = extract_meta_content(parser, "locale")
    if not locale:
        html_tag = parser.css_first("html")
        if html_tag:
            locale = html_tag.attributes.get("lang")

    email = extract_email(parser)
    phone = extract_phone(parser)
    social = extract_social_links(parser)

    json_ld = extract_json_ld(html)
    currency = _extract_currency(json_ld, html)
    category = _extract_category(json_ld, parser)

    return {
        "store_name": store_name,
        "description": description,
        "locale": locale,
        "currency": currency,
        "email": email,
        "phone": phone,
        "category": category,
        "social": social,
    }


def _extract_currency(
    json_ld: Optional[dict], html: str
) -> Optional[str]:
    if json_ld:
        for key in ("priceCurrency", "currency"):
            if key in json_ld:
                return json_ld[key]

    match = re.search(
        r'"currency"\s*:\s*"(\w{3})"', html
    )
    if match:
        return match.group(1)

    match = re.search(
        r'"Shopify\.currency\.active"\s*:\s*"(\w{3})"', html
    )
    if match:
        return match.group(1)

    return None


def _extract_category(
    json_ld: Optional[dict], parser: HTMLParser
) -> Optional[str]:
    if json_ld:
        for key in ("@type", "category"):
            val = json_ld.get(key)
            if val and isinstance(val, str):
                return val

    meta_category = extract_meta_content(parser, "category")
    if meta_category:
        return meta_category

    keywords = extract_meta_content(parser, "keywords")
    if keywords:
        parts = [k.strip() for k in keywords.split(",")]
        for p in parts:
            if len(p) < 50:
                return p

    return None
