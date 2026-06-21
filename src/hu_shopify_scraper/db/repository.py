import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from hu_shopify_scraper.config import settings
from hu_shopify_scraper.db.models import Store


class Repository:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or settings.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def init_db(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS stores (
                domain TEXT PRIMARY KEY,
                store_name TEXT,
                merchant_name TEXT,
                currency TEXT,
                locale TEXT,
                email TEXT,
                phone TEXT,
                description TEXT,
                category TEXT,
                myshopify_domain TEXT,
                is_verified INTEGER DEFAULT 0,
                needs_domain_resolution INTEGER DEFAULT 0,
                source TEXT,
                custom_domain TEXT,
                discovered_by TEXT,
                first_seen TEXT,
                last_verified TEXT
            );

            CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                domains_checked INTEGER DEFAULT 0,
                new_found INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0
            );
        """)
        self._migrate()

    def _migrate(self) -> None:
        existing = {
            row[1]
            for row in self.conn.execute(
                "PRAGMA table_info(stores)"
            ).fetchall()
        }
        migrations = [
            ("source", "TEXT"),
            ("custom_domain", "TEXT"),
            ("merchant_name", "TEXT"),
            ("needs_domain_resolution", "INTEGER DEFAULT 0"),
        ]
        for col, coltype in migrations:
            if col not in existing:
                self.conn.execute(
                    f"ALTER TABLE stores ADD COLUMN {col} {coltype}"
                )
        self.conn.commit()

    def upsert_store(self, store: Store) -> None:
        now = datetime.now().isoformat()
        existing = self.conn.execute(
            "SELECT first_seen FROM stores WHERE domain = ?",
            (store.domain,),
        ).fetchone()

        first_seen = existing["first_seen"] if existing else now

        self.conn.execute(
            """INSERT OR REPLACE INTO stores
               (domain, store_name, merchant_name, currency, locale, email, phone,
                description, category, myshopify_domain, is_verified,
                needs_domain_resolution, source, custom_domain, discovered_by,
                first_seen, last_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                store.domain,
                store.store_name,
                store.merchant_name,
                store.currency,
                store.locale,
                store.email,
                store.phone,
                store.description,
                store.category,
                store.myshopify_domain,
                1 if store.is_verified else 0,
                1 if store.needs_domain_resolution else 0,
                store.source,
                store.custom_domain,
                store.discovered_by,
                first_seen,
                now,
            ),
        )
        self.conn.commit()

    def store_exists(self, domain: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM stores WHERE domain = ?", (domain,)
        ).fetchone()
        return row is not None

    def get_all_stores(self, verified_only: bool = True) -> list[Store]:
        query = "SELECT * FROM stores"
        params: tuple = ()
        if verified_only:
            query += " WHERE is_verified = 1"
        query += " ORDER BY domain"

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_store(r) for r in rows]

    def get_store_by_domain(self, domain: str) -> Optional[Store]:
        row = self.conn.execute(
            "SELECT * FROM stores WHERE domain = ?", (domain,)
        ).fetchone()
        return self._row_to_store(row) if row else None

    def get_unverified_stores(self) -> list[Store]:
        rows = self.conn.execute(
            "SELECT * FROM stores WHERE is_verified = 0"
        ).fetchall()
        return [self._row_to_store(r) for r in rows]

    def get_stores_by_source(self, source: str) -> list[Store]:
        rows = self.conn.execute(
            "SELECT * FROM stores WHERE source = ?", (source,)
        ).fetchall()
        return [self._row_to_store(r) for r in rows]

    def get_count(self, verified_only: bool = True) -> int:
        query = "SELECT COUNT(*) FROM stores"
        params: tuple = ()
        if verified_only:
            query += " WHERE is_verified = 1"
        row = self.conn.execute(query, params).fetchone()
        return row[0]

    def get_counts_by_source(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT source, COUNT(*) as cnt FROM stores "
            "WHERE is_verified = 1 GROUP BY source"
        ).fetchall()
        return {
            (row["source"] or "unknown"): row["cnt"] for row in rows
        }

    def start_run(self, strategy: str) -> int:
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            "INSERT INTO scrape_runs (strategy, started_at) VALUES (?, ?)",
            (strategy, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        domains_checked: int,
        new_found: int,
        errors: int,
    ) -> None:
        now = datetime.now().isoformat()
        self.conn.execute(
            """UPDATE scrape_runs
               SET finished_at = ?, domains_checked = ?,
                   new_found = ?, errors = ?
               WHERE id = ?""",
            (now, domains_checked, new_found, errors, run_id),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_store(row: sqlite3.Row) -> Store:
        return Store(
            domain=row["domain"],
            store_name=row["store_name"],
            merchant_name=row["merchant_name"],
            currency=row["currency"],
            locale=row["locale"],
            email=row["email"],
            phone=row["phone"],
            description=row["description"],
            category=row["category"],
            myshopify_domain=row["myshopify_domain"],
            is_verified=bool(row["is_verified"]),
            needs_domain_resolution=bool(row["needs_domain_resolution"]),
            source=row["source"],
            custom_domain=row["custom_domain"],
            discovered_by=row["discovered_by"],
            first_seen=(
                datetime.fromisoformat(row["first_seen"])
                if row["first_seen"]
                else None
            ),
            last_verified=(
                datetime.fromisoformat(row["last_verified"])
                if row["last_verified"]
                else None
            ),
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
