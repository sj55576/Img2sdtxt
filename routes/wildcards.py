"""Wildcard file management and dynamic prompt expansion endpoints."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

import dynamic_prompts as dp
from models import CreateWildcardRequest, ExpandPromptRequest, UpdateWildcardRequest

logger = logging.getLogger("img2sdtxt.wildcards")

router = APIRouter(prefix="/api/wildcards", tags=["wildcards"])

WILDCARDS_DIR = Path(__file__).parent.parent / "data" / "wildcards"

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _wildcard_path(name: str) -> Path:
    if not _NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail="Invalid wildcard name.")
    return WILDCARDS_DIR / f"{name}.txt"


def _read_entries(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _write_entries(path: Path, entries: list[str]) -> None:
    WILDCARDS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    dp._wildcard_cache.clear()


@router.get("/")
def list_wildcards():
    WILDCARDS_DIR.mkdir(parents=True, exist_ok=True)
    wildcards = []
    for path in sorted(WILDCARDS_DIR.glob("*.txt")):
        try:
            entries = _read_entries(path)
        except Exception:
            logger.warning("Failed to read wildcard file %s", path, exc_info=True)
            continue
        wildcards.append({"name": path.stem, "count": len(entries), "preview": entries[:5]})
    return {"wildcards": wildcards}


@router.get("/{name}")
def get_wildcard(name: str):
    path = _wildcard_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Wildcard '{name}' not found.")
    return {"name": name, "entries": _read_entries(path)}


@router.post("/")
def create_wildcard(request: CreateWildcardRequest):
    path = _wildcard_path(request.name)
    if path.exists():
        raise HTTPException(status_code=400, detail=f"Wildcard '{request.name}' already exists.")
    _write_entries(path, request.entries)
    return {"name": request.name, "entries": request.entries}


@router.put("/{name}")
def update_wildcard(name: str, request: UpdateWildcardRequest):
    path = _wildcard_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Wildcard '{name}' not found.")
    _write_entries(path, request.entries)
    return {"name": name, "entries": request.entries}


@router.delete("/{name}")
def delete_wildcard(name: str):
    path = _wildcard_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Wildcard '{name}' not found.")
    path.unlink()
    dp._wildcard_cache.clear()
    return {"success": True}


@router.post("/expand")
def expand_dynamic_prompt(request: ExpandPromptRequest):
    try:
        if request.mode == "random":
            expanded = [dp.expand_prompt(request.template, WILDCARDS_DIR, seed=request.seed)]
        elif request.mode == "preview":
            expanded = dp.preview_expansion(request.template, WILDCARDS_DIR, count=request.count, seed=request.seed)
        else:
            expanded = dp.expand_prompt_combinatorial(
                request.template, WILDCARDS_DIR, max_combinations=request.max_combinations
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    combination_count = dp.count_combinations(request.template, WILDCARDS_DIR)
    return {"expanded": expanded, "combination_count": combination_count}
