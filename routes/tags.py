"""Tag autocomplete suggestion endpoints."""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger("img2sdtxt.tags")

router = APIRouter(prefix="/api", tags=["tags"])

_TAGS_FILE = Path(__file__).parent.parent / "static" / "data" / "tags.json"

# Module-level cache populated lazily on first request.
_tags_cache: Optional[list[dict]] = None


def _load_tags() -> list[dict]:
    """Load tags from the JSON data file, caching the result in-process."""
    global _tags_cache
    if _tags_cache is not None:
        return _tags_cache

    if not _TAGS_FILE.exists():
        logger.warning("Tags file not found at %s; returning empty tag list.", _TAGS_FILE)
        _tags_cache = []
        return _tags_cache

    try:
        data = json.loads(_TAGS_FILE.read_text(encoding="utf-8"))
        _tags_cache = data.get("tags", [])
    except Exception:
        logger.warning("Failed to load tags file at %s; returning empty tag list.", _TAGS_FILE, exc_info=True)
        _tags_cache = []

    return _tags_cache


def _score_tag(tag: dict, query_lower: str) -> int:
    """Return a match score for tag against query_lower, or 0 if no match."""
    priority = tag.get("p", 0)
    name = tag.get("name", "")
    name_lower = name.lower()
    aliases = tag.get("a") or []
    aliases_lower = [a.lower() for a in aliases]

    if name_lower == query_lower:
        return 10000 + priority
    if name_lower.startswith(query_lower):
        return 5000 + priority
    if any(alias.startswith(query_lower) for alias in aliases_lower):
        return 3000 + priority
    if query_lower in name_lower:
        return 1000 + priority
    if any(query_lower in alias for alias in aliases_lower):
        return 500 + priority

    return 0


@router.get("/tags/suggest")
def suggest_tags(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    category: Optional[str] = Query(None),
):
    """Return tag suggestions matching the query, ranked by relevance."""
    tags = _load_tags()
    query_lower = q.lower()

    candidates = tags
    if category:
        candidates = [tag for tag in candidates if tag.get("cat") == category]

    scored: list[tuple[int, dict]] = []
    for tag in candidates:
        score = _score_tag(tag, query_lower)
        if score > 0:
            scored.append((score, tag))

    scored.sort(key=lambda item: item[0], reverse=True)

    results = [tag for _score, tag in scored[:limit]]

    return {"success": True, "tags": results}


@router.get("/tags/categories")
def list_tag_categories():
    """Return all distinct categories present in the loaded tag data."""
    tags = _load_tags()
    cat_set: set[str] = {tag["cat"] for tag in tags if isinstance(tag.get("cat"), str)}
    categories = sorted(cat_set)

    return {"success": True, "categories": categories}
