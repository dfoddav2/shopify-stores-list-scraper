import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    db_path: Path = Path(
        os.getenv("HU_SHOPIFY_DB_PATH", "data/shopify_stores.db")
    )
    request_timeout: int = int(os.getenv("HU_SHOPIFY_TIMEOUT", "15"))
    max_concurrent: int = int(os.getenv("HU_SHOPIFY_CONCURRENCY", "10"))
    rate_limit_delay: float = float(os.getenv("HU_SHOPIFY_RATE_LIMIT", "0.5"))
    user_agent: str = os.getenv(
        "HU_SHOPIFY_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
    )
    proxy_url: Optional[str] = os.getenv("HU_SHOPIFY_PROXY_URL")
    google_dork_pages: int = int(os.getenv("HU_SHOPIFY_DORK_PAGES", "3"))
    hu_domain_batch_size: int = int(
        os.getenv("HU_SHOPIFY_HU_BATCH", "50")
    )

    # CT Logs
    crtsh_timeout: int = int(os.getenv("CTRSH_TIMEOUT", "120"))
    ct_probe_concurrency: int = int(
        os.getenv("CT_PROBE_CONCURRENCY", "50")
    )
    ct_content_check: bool = os.getenv(
        "CT_CONTENT_CHECK", "true"
    ).lower() in ("true", "1", "yes")

    # Tranco
    tranco_max_domains: int = int(os.getenv("TRANCO_MAX_DOMAINS", "0"))
    tranco_list_url: str = os.getenv(
        "TRANCO_LIST_URL",
        "https://tranco-list.eu/top-1m.csv.zip",
    )

    # .hu Registry
    hu_registry_url: str = os.getenv(
        "HU_REGISTRY_URL",
        "https://info.domain.hu/varolista/en/abc.html",
    )
    hu_registry_skip_private: bool = os.getenv(
        "HU_REGISTRY_SKIP_PRIVATE", "true"
    ).lower() in ("true", "1", "yes")

    # Caching
    cache_dir: Path = Path(os.getenv("HU_SHOPIFY_CACHE_DIR", "data/cache"))

    # Chrome remote debugging port for real browser profile
    chrome_debug_port: int = int(
        os.getenv("HU_SHOPIFY_CHROME_DEBUG_PORT", "0")
    )

    # Google Custom Search API
    google_api_key: Optional[str] = os.getenv("HU_SHOPIFY_GOOGLE_API_KEY")
    google_cse_id: Optional[str] = os.getenv("HU_SHOPIFY_GOOGLE_CSE_ID")

    # App Store Reviews
    app_review_slugs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        raw = os.getenv("HU_SHOPIFY_APP_SLUGS", "")
        if raw:
            self.app_review_slugs = [
                s.strip() for s in raw.split(",") if s.strip()
            ]


settings = Settings()
