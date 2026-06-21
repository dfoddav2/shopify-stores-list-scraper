import json


class TestCrtShParsing:
    SAMPLE_RESPONSE = json.dumps([
        {
            "id": 12345,
            "name_value": "shop1.myshopify.com\nwww.shop1.myshopify.com",
            "not_before": "2024-01-01T00:00:00",
        },
        {
            "id": 12346,
            "name_value": "shop2.myshopify.com",
            "not_before": "2024-01-02T00:00:00",
        },
        {
            "id": 12347,
            "name_value": "shop1.myshopify.com\nexample.com",
            "not_before": "2024-01-03T00:00:00",
        },
        {
            "id": 12348,
            "name_value": "shop3.myshopify.com\nadmin.shop3.myshopify.com",
            "not_before": "2024-01-04T00:00:00",
        },
    ])

    async def test_parse_unique_myshopify_domains(self, tmp_path):
        cache_file = tmp_path / "crtsh_myshopify.json"
        cache_file.write_text(self.SAMPLE_RESPONSE)

        import hu_shopify_scraper.discovery.ct_logs as ct_logs
        original = ct_logs.CACHE_FILE
        ct_logs.CACHE_FILE = cache_file

        try:
            domains = await ct_logs.fetch_myshopify_domains(refresh=False)
        finally:
            ct_logs.CACHE_FILE = original

        assert len(domains) == 5
        assert "shop1.myshopify.com" in domains
        assert "shop2.myshopify.com" in domains
        assert "shop3.myshopify.com" in domains
        assert "admin.shop3.myshopify.com" in domains
        assert "www.shop1.myshopify.com" in domains
        assert "example.com" not in domains

    async def test_excludes_non_myshopify(self, tmp_path):
        data = json.dumps([
            {
                "id": 1,
                "name_value": "example.com\nexample.org",
                "not_before": "2024-01-01T00:00:00",
            },
        ])
        cache_file = tmp_path / "crtsh_myshopify.json"
        cache_file.write_text(data)

        import hu_shopify_scraper.discovery.ct_logs as ct_logs
        original = ct_logs.CACHE_FILE
        ct_logs.CACHE_FILE = cache_file

        try:
            domains = await ct_logs.fetch_myshopify_domains(refresh=False)
        finally:
            ct_logs.CACHE_FILE = original

        assert domains == []

    async def test_empty_response(self, tmp_path):
        cache_file = tmp_path / "crtsh_myshopify.json"
        cache_file.write_text("[]")

        import hu_shopify_scraper.discovery.ct_logs as ct_logs
        original = ct_logs.CACHE_FILE
        ct_logs.CACHE_FILE = cache_file

        try:
            domains = await ct_logs.fetch_myshopify_domains(refresh=False)
        finally:
            ct_logs.CACHE_FILE = original

        assert domains == []
