from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import Browser, Page, async_playwright
from playwright_stealth import Stealth

from hu_shopify_scraper.config import settings


class BrowserManager:
    def __init__(self) -> None:
        self._browser: Optional[Browser] = None
        self._pw_ctx = None
        self._stealth = Stealth(
            navigator_languages_override=("hu-HU", "hu", "en-US", "en"),
        )
        self._loop_id: Optional[int] = None
        self._is_realtime: bool = False

    async def _ensure_browser(self) -> Browser:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if self._browser is None or self._loop_id != loop_id:
            await self.cleanup()
            pw = async_playwright()
            self._pw_ctx = await pw.start()

            port = settings.chrome_debug_port
            if port > 0:
                try:
                    self._browser = await self._pw_ctx.chromium.connect_over_cdp(
                        f"http://127.0.0.1:{port}"
                    )
                    self._is_realtime = True
                except Exception:
                    self._is_realtime = False

            if self._browser is None:
                stealth_ctx = await self._stealth.use_async(pw).__aenter__()
                self._browser = await stealth_ctx.chromium.launch(
                    headless=True,
                )
                self._is_realtime = False

            self._loop_id = loop_id
        return self._browser

    async def fetch_page(
        self,
        url: str,
        timeout: int = 15,
        wait_for_captcha: int = 0,
    ) -> Optional[str]:
        browser = await self._ensure_browser()

        if self._is_realtime:
            context = browser.contexts[0]
        else:
            context = await browser.new_context(
                locale="hu-HU",
                timezone_id="Europe/Budapest",
                viewport={"width": 1920, "height": 1080},
            )

        page: Optional[Page] = None
        close_page = True
        try:
            page = await context.new_page()
            response = await page.goto(
                url, timeout=timeout * 1000, wait_until="load"
            )
            await asyncio.sleep(3)

            status = response.status if response else 0
            body_text = await page.inner_text("body")

            has_captcha = "sorry" in page.url.lower() or "unusual traffic" in body_text.lower()
            is_hard_block = status in (403, 429) and not has_captcha

            if is_hard_block:
                print(
                    "\n[!] Google returned a hard block (403). "
                    "No CAPTCHA to solve."
                )
                print(
                    "    Try: sign out of your Google profile, "
                    "or switch VPN to get a fresh IP."
                )
                return None

            if has_captcha and wait_for_captcha and self._is_realtime:
                close_page = False
                print(
                    "\n[!] Google CAPTCHA detected. Please solve it "
                    "in the opened Chrome tab."
                )
                print(f"    Waiting up to {wait_for_captcha}s...")
                waited = 0
                while waited < wait_for_captcha:
                    await asyncio.sleep(2)
                    waited += 2
                    cur_body = await page.inner_text("body")
                    if "sorry" not in page.url and "unusual traffic" not in cur_body.lower():
                        print("    CAPTCHA solved! Continuing.")
                        await asyncio.sleep(2)
                        break
                else:
                    print("    CAPTCHA wait timed out.")
                    return None

            html = await page.content()
            return html
        except Exception:
            return None
        finally:
            if page is not None and close_page:
                try:
                    await page.close()
                except Exception:
                    pass
            if not self._is_realtime and context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def cleanup(self) -> None:
        if self._browser is not None:
            try:
                if not self._is_realtime:
                    await self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._loop_id = None
        if self._pw_ctx is not None:
            try:
                await self._pw_ctx.stop()
            except Exception:
                pass
            self._pw_ctx = None


browser = BrowserManager()
