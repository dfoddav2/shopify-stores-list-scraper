from hu_shopify_scraper.verify.fingerprint import FingerprintResult


class TestFingerprintResult:
    def test_default_signals_is_empty_list(self):
        result = FingerprintResult(is_shopify=False)
        assert result.signals == []

    def test_signals_preserved(self):
        result = FingerprintResult(is_shopify=True, signals=["products.json"])
        assert result.signals == ["products.json"]

    def test_shopify_store_score(self):
        result = FingerprintResult(
            is_shopify=True,
            confidence=0.8,
            signals=["products.json", "admin_redirect", "meta_json", "html_fingerprint"],
        )
        assert result.is_shopify is True
        assert result.confidence == 0.8
