import re
from typing import Optional
from urllib.parse import urlparse

DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\."
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z]{2,})?)",
    re.IGNORECASE,
)


def extract_domain(text: str) -> Optional[str]:
    match = DOMAIN_RE.search(text)
    if match:
        return match.group(1).lower()
    return None


def normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def domain_from_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return urlparse(url).netloc.lower()


def is_valid_domain(domain: str) -> bool:
    pattern = re.compile(
        r"^([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
        r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
        re.IGNORECASE,
    )
    return bool(pattern.match(domain))


def is_myshopify_domain(domain: str) -> bool:
    return domain.endswith(".myshopify.com")
