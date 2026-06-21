from hu_shopify_scraper.utils.domain import (
    domain_from_url,
    extract_domain,
    is_myshopify_domain,
    is_valid_domain,
    normalize_url,
)


class TestExtractDomain:
    def test_extracts_from_url(self):
        assert extract_domain("https://shop.example.com/products") == "shop.example.com"

    def test_extracts_from_bare_domain(self):
        assert extract_domain("example.com") == "example.com"

    def test_extracts_from_url_without_scheme(self):
        assert extract_domain("www.example.com/page") == "example.com"

    def test_returns_none_for_invalid(self):
        assert extract_domain("") is None


class TestNormalizeURL:
    def test_adds_https(self):
        assert normalize_url("example.com") == "https://example.com"

    def test_preserves_scheme(self):
        assert normalize_url("http://example.com") == "http://example.com"


class TestDomainFromURL:
    def test_extracts_netloc(self):
        assert domain_from_url("https://shop.example.com/path") == "shop.example.com"

    def test_adds_scheme(self):
        assert domain_from_url("example.com") == "example.com"


class TestIsValidDomain:
    def test_valid_domain(self):
        assert is_valid_domain("example.com") is True
        assert is_valid_domain("shop.example.co.hu") is True

    def test_invalid_domain(self):
        assert is_valid_domain("") is False
        assert is_valid_domain("not a domain") is False


class TestIsMyshopifyDomain:
    def test_myshopify(self):
        assert is_myshopify_domain("store.myshopify.com") is True

    def test_not_myshopify(self):
        assert is_myshopify_domain("example.com") is False
