from datetime import datetime
from pathlib import Path

from hu_shopify_scraper.db.models import Store
from hu_shopify_scraper.db.repository import Repository


class TestRepository:
    def setup_method(self):
        self.repo = Repository(db_path=Path("/tmp/test_shopify.db"))
        self.repo.init_db()

    def teardown_method(self):
        self.repo.close()
        Path("/tmp/test_shopify.db").unlink(missing_ok=True)

    def test_store_upsert_and_retrieve(self):
        store = Store(
            domain="test.hu",
            store_name="Test Store",
            currency="HUF",
            locale="hu",
            is_verified=True,
            first_seen=datetime.now(),
            last_verified=datetime.now(),
        )
        self.repo.upsert_store(store)

        retrieved = self.repo.get_store_by_domain("test.hu")
        assert retrieved is not None
        assert retrieved.domain == "test.hu"
        assert retrieved.store_name == "Test Store"
        assert retrieved.currency == "HUF"

    def test_store_exists(self):
        store = Store(domain="exists.hu")
        self.repo.upsert_store(store)
        assert self.repo.store_exists("exists.hu") is True
        assert self.repo.store_exists("nope.hu") is False

    def test_unverified_stores(self):
        s1 = Store(domain="v1.hu", is_verified=True)
        s2 = Store(domain="v2.hu", is_verified=False)
        self.repo.upsert_store(s1)
        self.repo.upsert_store(s2)

        unverified = self.repo.get_unverified_stores()
        domains = {s.domain for s in unverified}
        assert "v2.hu" in domains
        assert "v1.hu" not in domains

    def test_get_count(self):
        for d in ["a.hu", "b.hu", "c.hu"]:
            self.repo.upsert_store(Store(domain=d, is_verified=(d == "a.hu")))
        assert self.repo.get_count(verified_only=True) == 1
        assert self.repo.get_count(verified_only=False) == 3
