import hashlib
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("img2sdtxt.cache")


class LLMCache:
    def __init__(self, ttl_seconds: int = 3600, enabled: bool = True):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds
        self.enabled = enabled
        self.hits = 0
        self.misses = 0

    def _make_key(self, image_bytes: Optional[bytes], text_input: Optional[str], style: str, tone: str, quality: str) -> str:
        h = hashlib.sha256()
        if image_bytes:
            h.update(image_bytes)
        if text_input:
            h.update(text_input.encode())
        h.update(f"{style}:{tone}:{quality}".encode())
        return h.hexdigest()

    def get(self, image_bytes: Optional[bytes], text_input: Optional[str], style: str, tone: str, quality: str) -> Optional[Dict]:
        if not self.enabled:
            return None
        key = self._make_key(image_bytes, text_input, style, tone, quality)
        entry = self._cache.get(key)
        if entry is not None:
            if time.time() - entry["timestamp"] < self.ttl:
                self.hits += 1
                logger.debug("Cache HIT key=%.16s", key)
                return entry["result"]
            del self._cache[key]
        self.misses += 1
        logger.debug("Cache MISS key=%.16s", key)
        return None

    def set(self, image_bytes: Optional[bytes], text_input: Optional[str], style: str, tone: str, quality: str, result: Dict):
        if not self.enabled:
            return
        key = self._make_key(image_bytes, text_input, style, tone, quality)
        self._cache[key] = {"result": result, "timestamp": time.time()}
        logger.debug("Cache SET key=%.16s size=%d", key, len(self._cache))

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        self.hits = 0
        self.misses = 0
        return count

    def stats(self) -> Dict:
        total = self.hits + self.misses
        return {
            "enabled": self.enabled,
            "size": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_pct": round(self.hits / total * 100, 1) if total > 0 else 0.0,
            "ttl_seconds": self.ttl,
        }


_instance: Optional[LLMCache] = None


def get_cache() -> LLMCache:
    global _instance
    if _instance is None:
        _instance = LLMCache()
    return _instance
