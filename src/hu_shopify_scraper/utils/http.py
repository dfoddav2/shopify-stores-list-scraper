import asyncio
from typing import Optional

import httpx

from hu_shopify_scraper.config import settings


class HttpClient:
    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._loop_id: Optional[int] = None

    @property
    def client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if self._client is None or self._loop_id != loop_id:
            self._client = None  # discard old client (gc will close it)
            limits = httpx.Limits(
                max_connections=settings.max_concurrent,
                max_keepalive_connections=settings.max_concurrent,
            )
            kwargs = {
                "limits": limits,
                "timeout": settings.request_timeout,
                "follow_redirects": True,
            }
            if settings.proxy_url:
                kwargs["proxies"] = settings.proxy_url
            self._client = httpx.AsyncClient(**kwargs)
            self._loop_id = loop_id
        return self._client

    async def get(self, url: str) -> Optional[httpx.Response]:
        headers = {"User-Agent": settings.user_agent}
        try:
            response = await self.client.get(url, headers=headers)
            return response
        except (httpx.TimeoutException, httpx.HTTPError):
            return None

    async def head(self, url: str) -> Optional[httpx.Response]:
        headers = {"User-Agent": settings.user_agent}
        try:
            response = await self.client.head(
                url, headers=headers, follow_redirects=False
            )
            return response
        except (httpx.TimeoutException, httpx.HTTPError):
            return None

    async def close(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except RuntimeError:
                pass
            self._client = None
            self._loop_id = None


http = HttpClient()
