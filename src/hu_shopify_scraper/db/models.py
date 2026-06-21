from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Store(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain: str
    store_name: Optional[str] = None
    merchant_name: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    myshopify_domain: Optional[str] = None
    is_verified: bool = False
    needs_domain_resolution: bool = False
    discovered_by: Optional[str] = None
    source: Optional[str] = None
    custom_domain: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_verified: Optional[datetime] = None


class ScrapeRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    strategy: str
    started_at: datetime = datetime.now()
    finished_at: Optional[datetime] = None
    domains_checked: int = 0
    new_found: int = 0
    errors: int = 0
