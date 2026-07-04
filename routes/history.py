"""History CRUD and tags endpoints."""

import csv
import io as _io
import json

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

import history as hist

router = APIRouter(prefix="/api", tags=["history"])


# ------------------------------------------------------------------ #
# History
# ------------------------------------------------------------------ #


@router.get("/history")
def get_history(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    style: str = "",
    quality: str = "",
    favorites_only: bool = False,
    tag: str = "",
):
    items = hist.get_history(
        limit=limit, offset=offset, search=search, style=style, quality=quality, favorites_only=favorites_only, tag=tag
    )
    total = hist.get_history_count(search=search, style=style, quality=quality, favorites_only=favorites_only, tag=tag)
    return {"success": True, "items": items, "total": total}


def _xlsx_cell_value(value):
    """openpyxl only accepts scalar values — coerce lists/dicts/None to strings."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _build_history_workbook(items: list) -> bytes:
    """Build an xlsx workbook from history items and return its bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "History"

    if items:
        fieldnames = list(items[0].keys())
        ws.append(fieldnames)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for item in items:
            ws.append([_xlsx_cell_value(item.get(key)) for key in fieldnames])

    buffer = _io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@router.get("/history/export")
async def export_history(format: str = "json"):
    """Download all history as JSON, CSV, or XLSX."""
    items = await run_in_threadpool(hist.get_history, limit=None, offset=0)

    if format == "csv":
        output = _io.StringIO()
        if items:
            fieldnames = list(items[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(items)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="prompt_history.csv"'},
        )
    elif format == "xlsx":
        content = await run_in_threadpool(_build_history_workbook, items)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="prompt_history.xlsx"'},
        )
    else:
        return Response(
            content=json.dumps(items, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="prompt_history.json"'},
        )


@router.get("/history/diff")
def get_diff(id_a: int, id_b: int):
    diff = hist.get_version_diff(id_a, id_b)
    if diff is None:
        raise HTTPException(status_code=404, detail="One or both items not found.")
    return {"success": True, "diff": diff}


@router.get("/history/{item_id}/versions")
def get_versions(item_id: int):
    item = hist.get_history_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found.")
    versions = hist.get_version_tree(item_id)
    return {"success": True, "versions": versions}


@router.post("/history/{item_id}/rollback")
def rollback_version(item_id: int, body: dict):
    target_id = body.get("target_id")
    if target_id is None:
        raise HTTPException(status_code=400, detail="target_id is required.")
    result = hist.rollback_to_version(item_id, target_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source or target item not found.")
    return {"success": True, "item": result}


@router.put("/history/{item_id}/favorite")
def toggle_history_favorite(item_id: int):
    updated = hist.toggle_favorite(item_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History item not found.")
    return {"success": True, "item": updated}


@router.delete("/history/{item_id}")
def delete_history(item_id: int):
    deleted = hist.delete_history_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History item not found.")
    return {"success": True}


@router.delete("/history")
def clear_history():
    count = hist.clear_all_history()
    return {"success": True, "deleted": count}


# ------------------------------------------------------------------ #
# History Tags
# ------------------------------------------------------------------ #


@router.get("/tags")
def list_all_tags():
    tags = hist.get_all_tags()
    return {"success": True, "tags": tags}


@router.post("/history/{item_id}/tags")
def add_history_tags(item_id: int, request_data: dict):
    tags = request_data.get("tags", [])
    if not tags or not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="'tags' must be a non-empty list of strings.")
    if any(not isinstance(t, str) or not t.strip() for t in tags):
        raise HTTPException(status_code=400, detail="Each tag must be a non-empty string.")
    item = hist.get_history_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found.")
    result_tags = hist.add_tags(item_id, tags)
    return {"success": True, "tags": result_tags}


@router.delete("/history/{item_id}/tags/{tag}")
def remove_history_tag(item_id: int, tag: str):
    item = hist.get_history_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found.")
    result_tags = hist.remove_tag(item_id, tag)
    return {"success": True, "tags": result_tags}
