from unittest.mock import MagicMock, patch

from hu_shopify_scraper.discovery.hu_registry import (
    PRIVATE_PERSON_TAGS,
    fetch_registry_domains,
)


class TestHuRegistryParsing:
    SAMPLE_HTML = """
    <html><body>
    <table>
        <tr>
            <th>Domain</th>
            <th>Applicant</th>
            <th>Date</th>
        </tr>
        <tr>
            <td>example.hu</td>
            <td>ACME Kft.</td>
            <td>2024-01-15</td>
        </tr>
        <tr>
            <td>private-site.hu</td>
            <td>Private Person</td>
            <td>2024-01-16</td>
        </tr>
        <tr>
            <td>webshop.hu</td>
            <td>Webshop Zrt.</td>
            <td>2024-01-17</td>
        </tr>
    </table>
    </body></html>
    """

    NON_REGISTRY_HTML = """
    <html><body>
    <h1>Welcome</h1>
    <p>No table here</p>
    </body></html>
    """

    @patch("hu_shopify_scraper.discovery.hu_registry.http.get")
    async def test_fetches_domains_skipping_private(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, text=self.SAMPLE_HTML
        )

        domains = await fetch_registry_domains()
        assert domains == ["example.hu", "webshop.hu"]

    @patch("hu_shopify_scraper.discovery.hu_registry.http.get")
    async def test_no_table_returns_empty(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200, text=self.NON_REGISTRY_HTML
        )

        domains = await fetch_registry_domains()
        assert domains == []

    @patch("hu_shopify_scraper.discovery.hu_registry.http.get")
    async def test_error_returns_empty(self, mock_get):
        mock_get.return_value = None

        domains = await fetch_registry_domains()
        assert domains == []

    def test_private_person_tags(self):
        assert "private person" in PRIVATE_PERSON_TAGS
        assert "magánszemély" in PRIVATE_PERSON_TAGS
