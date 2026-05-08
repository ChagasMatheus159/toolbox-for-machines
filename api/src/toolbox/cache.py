"""SQLite cache with TTL for toolbox responses."""

import hashlib
import json
import sqlite3
import time
from typing import Any

from toolbox.config import settings


class Cache:
    """Simple SQLite key-value cache with per-entry TTL."""

    def __init__(self, db_path: str | None = None):
        self.enabled = settings.cache_enabled
        self.db_path = db_path or settings.cache_db_path
        if self.enabled:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    ttl_seconds INTEGER NOT NULL
                )
            """)
            self._conn.commit()

    @staticmethod
    def make_key(endpoint: str, params: dict) -> str:
        """Create a deterministic cache key from endpoint + params."""
        raw = json.dumps({"e": endpoint, "p": params}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get cached response if exists and not expired."""
        if not self.enabled:
            return None
        cur = self._conn.execute(
            "SELECT response, created_at, ttl_seconds FROM cache WHERE key = ?",
            (key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        response, created_at, ttl = row
        if time.time() - created_at > ttl:
            # Expired — delete and return miss
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(response)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store a response in the cache."""
        if not self.enabled:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, response, created_at, ttl_seconds) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value), int(time.time()), ttl_seconds),
        )
        self._conn.commit()

    def cleanup(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        if not self.enabled:
            return 0
        cur = self._conn.execute(
            "DELETE FROM cache WHERE (created_at + ttl_seconds) < ?",
            (int(time.time()),),
        )
        self._conn.commit()
        return cur.rowcount


# Singleton instance
cache = Cache()
