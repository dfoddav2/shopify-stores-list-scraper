
import pytest

from hu_shopify_scraper.verify.fingerprint import fingerprint_store
from hu_shopify_scraper.verify.metadata import extract_metadata


@pytest.mark.asyncio
async def test_known_hungarian_shopify_store():
    """Test fingerprinting against a known Hungarian Shopify store."""
    result = await fingerprint_store("shop.biotechusa.hu")
    assert result.is_shopify is True
    assert result.confidence >= 0.4
    assert "products.json" in result.signals


@pytest.mark.asyncio
async def test_non_shopify_store():
    """Test that a non-Shopify site is not detected as Shopify."""
    result = await fingerprint_store("google.com")
    assert result.is_shopify is False
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_metadata_extraction():
    """Test metadata extraction from a known Hungarian Shopify store."""
    meta = await extract_metadata("shop.biotechusa.hu")
    assert meta.get("store_name") is not None
    assert meta.get("locale") == "hu"
    assert meta.get("currency") == "HUF"
    assert meta.get("social") is not None
