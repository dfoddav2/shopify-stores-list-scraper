from unittest.mock import AsyncMock, MagicMock, patch

from hu_shopify_scraper.verify.hungarian import (
    HU_CITIES,
    HU_KEYWORDS,
    check_hungarian_content,
    get_redirect_target,
    is_hu_domain,
)


class TestIsHuDomain:
    def test_hu_domain(self):
        assert is_hu_domain("example.hu") is True

    def test_non_hu_domain(self):
        assert is_hu_domain("example.com") is False

    def test_subdomain_hu(self):
        assert is_hu_domain("shop.example.hu") is True

    def test_empty_string(self):
        assert is_hu_domain("") is False


class TestGetRedirectTarget:
    @patch("hu_shopify_scraper.verify.hungarian.http.head", new_callable=AsyncMock)
    async def test_redirect_to_hu(self, mock_head):
        mock_head.return_value = MagicMock(
            headers={"location": "https://example.hu/"}
        )
        result = await get_redirect_target("test.myshopify.com")
        assert result == "example.hu"

    @patch("hu_shopify_scraper.verify.hungarian.http.head", new_callable=AsyncMock)
    async def test_no_redirect(self, mock_head):
        mock_head.return_value = MagicMock(headers={})
        result = await get_redirect_target("test.myshopify.com")
        assert result is None

    @patch("hu_shopify_scraper.verify.hungarian.http.head", new_callable=AsyncMock)
    async def test_timeout_returns_none(self, mock_head):
        mock_head.return_value = None
        result = await get_redirect_target("test.myshopify.com")
        assert result is None


class TestCheckHungarianContent:
    HU_HTML = """
    <html lang="hu">
    <head>
        <meta property="og:locale" content="hu_HU" />
        <title>Magyar Webáruház</title>
    </head>
    <body>
        <p>Kosárba teszem, rendelés leadása, fizetés bankkártyával.
        Kapcsolat: info@example.hu</p>
        <p>Szállítás Budapestre és országosan.</p>
        <p id="currency">HUF</p>
    </body>
    </html>
    """

    NON_HU_HTML = """
    <html lang="en">
    <head>
        <title>English Store</title>
    </head>
    <body>
        <p>Welcome to our store. Free shipping worldwide.</p>
        <p>Contact: info@example.com</p>
    </body>
    </html>
    """

    @patch("hu_shopify_scraper.verify.hungarian.http.get", new_callable=AsyncMock)
    async def test_detects_hungarian(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, text=self.HU_HTML
        )
        result = await check_hungarian_content("example.hu")
        assert result["is_hungarian"] is True
        assert result["confidence"] > 0.5
        assert "locale_hu" in result["signals"]
        assert "currency_huf" in result["signals"]
        assert "hungarian_keywords" in result["signals"]
        assert "hu_email" in result["signals"]

    @patch("hu_shopify_scraper.verify.hungarian.http.get", new_callable=AsyncMock)
    async def test_non_hungarian_returns_false(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, text=self.NON_HU_HTML
        )
        result = await check_hungarian_content("example.com")
        assert result["is_hungarian"] is False

    @patch("hu_shopify_scraper.verify.hungarian.http.get", new_callable=AsyncMock)
    async def test_error_response_returns_empty(self, mock_get):
        mock_get.return_value = None
        result = await check_hungarian_content("error.hu")
        assert result["is_hungarian"] is False
        assert result["confidence"] == 0.0

    def test_hu_cities_contains_budapest(self):
        assert "budapest" in HU_CITIES

    def test_hu_keywords_contains_kosar(self):
        assert "kosár" in HU_KEYWORDS
