import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("img2sdtxt.cache")

DB_PATH = Path(__file__).parent / "data" / "llm_cache.db"


class LLMCache:
    def __init__(self, ttl_seconds: int = 3600, enabled: bool = True):
        self.ttl = ttl_seconds
        self.enabled = enabled
        DB_PATH.parent.mkdir(exist_ok=True)
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_stats (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    hits INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0
                )
            """)
            conn.execute("INSERT OR IGNORE INTO cache_stats (id, hits, misses) VALUES (1, 0, 0)")
            conn.execute("DELETE FROM cache_entries WHERE ? - created_at >= ?", (time.time(), self.ttl))
            conn.commit()

    def _make_key(
        self,
        image_bytes: Optional[bytes],
        text_input: Optional[str],
        style: str,
        tone: str,
        quality: str,
        provider: str = "",
        model: str = "",
    ) -> str:
        h = hashlib.sha256()
        if image_bytes:
            h.update(image_bytes)
        if text_input:
            h.update(text_input.encode())
        h.update(f"{style}:{tone}:{quality}".encode())
        h.update(provider.encode("utf-8"))
        h.update(model.encode("utf-8"))
        return h.hexdigest()

    def get(
        self,
        image_bytes: Optional[bytes],
        text_input: Optional[str],
        style: str,
        tone: str,
        quality: str,
        provider: str = "",
        model: str = "",
    ) -> Optional[Dict]:
        if not self.enabled:
            return None
        key = self._make_key(image_bytes, text_input, style, tone, quality, provider, model)
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            row = conn.execute("SELECT value, created_at FROM cache_entries WHERE key = ?", (key,)).fetchone()
            if row is not None:
                if time.time() - row[1] < self.ttl:
                    conn.execute("UPDATE cache_stats SET hits = hits + 1 WHERE id = 1")
                    conn.commit()
                    logger.debug("Cache HIT key=%.16s", key)
                    return json.loads(row[0])
                conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            conn.execute("UPDATE cache_stats SET misses = misses + 1 WHERE id = 1")
            conn.commit()
        logger.debug("Cache MISS key=%.16s", key)
        return None

    def set(
        self,
        image_bytes: Optional[bytes],
        text_input: Optional[str],
        style: str,
        tone: str,
        quality: str,
        result: Dict,
        provider: str = "",
        model: str = "",
    ):
        if not self.enabled:
            return
        key = self._make_key(image_bytes, text_input, style, tone, quality, provider, model)
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache_entries (key, value, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(result), time.time()),
            )
            conn.commit()
            size = conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0]
        logger.debug("Cache SET key=%.16s size=%d", key, size)

    def clear(self) -> int:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            count = conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0]
            conn.execute("DELETE FROM cache_entries")
            conn.execute("UPDATE cache_stats SET hits = 0, misses = 0 WHERE id = 1")
            conn.commit()
        return count

    def stats(self) -> Dict:
        with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
            size = conn.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0]
            row = conn.execute("SELECT hits, misses FROM cache_stats WHERE id = 1").fetchone()
        hits = row[0] if row else 0
        misses = row[1] if row else 0
        total = hits + misses
        return {
            "enabled": self.enabled,
            "size": size,
            "hits": hits,
            "misses": misses,
            "hit_rate_pct": round(hits / total * 100, 1) if total > 0 else 0.0,
            "ttl_seconds": self.ttl,
        }


_instance: Optional[LLMCache] = None


def get_cache() -> LLMCache:
    global _instance
    if _instance is None:
        _instance = LLMCache()
    return _instance
